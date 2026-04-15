import streamlit as st
import pandas as pd
import datetime
import gspread
import time
from oauth2client.service_account import ServiceAccountCredentials

SHEET_ID = "1Z-DPnZlZqZsAGWdAT8S-a2RUN9tqR0rnOMs3519VbBg"
LOW_STOCK_THRESHOLD = 5
KILL_QTY = -999999  # 🔥 kill signal

# =========================
# NORMALIZE ITEM
# =========================
def normalize_item_name(name):
    if not name:
        return ""
    name = name.upper().strip()
    name = name.replace(",", ", ")
    name = " ".join(name.split())
    return name

def clean_compare(name):
    return normalize_item_name(name).replace(",", "").replace(" ", "")

# =========================
# CONNECT GSHEET
# =========================
def connect_gsheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["gcp_credentials"], scope
    )
    return gspread.authorize(creds)

# =========================
# SAFE READ
# =========================
def safe_read(sheet):
    for _ in range(3):
        try:
            return sheet.get_all_records()
        except:
            time.sleep(1)
    return []

# =========================
# APPEND STOCK
# =========================
def append_equipment_stock(equipment, item, qty, uom="pcs"):
    client = connect_gsheet()
    sheet = client.open_by_key(SHEET_ID).worksheet("equipment_stock")

    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    sheet.append_row([timestamp, equipment, item, qty, uom])

# =========================
# READ EQUIPMENT
# =========================
def read_equipment_items():
    client = connect_gsheet()
    sheet = client.open_by_key(SHEET_ID).worksheet("equipment_stock")

    df = pd.DataFrame(safe_read(sheet))
    equipment_dict = {}

    killed_items = set()

    for _, row in df.iterrows():
        eq = row.get("Equipment")
        item = normalize_item_name(row.get("Item"))

        try:
            qty = int(row.get("Qty", 0))
        except:
            qty = 0

        if qty <= KILL_QTY:
            killed_items.add((eq, item))

    for _, row in df.iterrows():
        eq = row.get("Equipment")
        item = normalize_item_name(row.get("Item"))

        try:
            qty = int(row.get("Qty", 0))
        except:
            qty = 0

        uom = row.get("UOM", "pcs")

        if not eq or not item:
            continue

        if (eq, item) in killed_items:
            continue

        if eq not in equipment_dict:
            equipment_dict[eq] = {}

        if item not in equipment_dict[eq]:
            equipment_dict[eq][item] = {"qty": 0, "uom": uom}

        equipment_dict[eq][item]["qty"] += qty

    for eq in list(equipment_dict.keys()):
        for item in list(equipment_dict[eq].keys()):
            if equipment_dict[eq][item]["qty"] < 0:
                del equipment_dict[eq][item]

    return equipment_dict

# =========================
# READ INVENTORY (FIXED)
# =========================
def read_inventory():
    client = connect_gsheet()
    sheet = client.open_by_key(SHEET_ID).worksheet("equipment_stock")

    df = pd.DataFrame(safe_read(sheet))

    inventory = {}
    uoms = {}

    killed_items = set()
    for _, row in df.iterrows():
        item = normalize_item_name(row.get("Item"))
        eq = row.get("Equipment")

        try:
            qty = int(row.get("Qty", 0))
        except:
            qty = 0

        if qty <= KILL_QTY:
            killed_items.add((eq, item))

    for _, row in df.iterrows():
        item = normalize_item_name(row.get("Item"))
        eq = row.get("Equipment")

        try:
            qty = int(row.get("Qty", 0))
        except:
            qty = 0

        uom = row.get("UOM", "pcs")

        if not item:
            continue

        if (eq, item) in killed_items:
            continue

        inventory[item] = inventory.get(item, 0) + qty
        uoms[item] = uom

    for item in list(inventory.keys()):
        if inventory[item] < 0:
            del inventory[item]

    return inventory, uoms

# =========================
# LOG TRANSACTION
# =========================
def log_transaction(action, item, qty, person, mdr, equipment, uom):
    client = connect_gsheet()
    sheet = client.open_by_key(SHEET_ID).worksheet("transactions_log")

    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    qty_signed = -qty if action == "Withdraw" else qty

    sheet.append_row([
        timestamp,
        action,
        item,
        qty_signed,
        uom,
        person,
        mdr,
        equipment
    ])

# =========================
# UI
# =========================
st.set_page_config(layout="wide")
menu = ["Inventory", "Equipment", "Withdraw/Deliver", "Transactions"]
choice = st.sidebar.radio("Go to", menu)

# =========================
# INVENTORY
# =========================
if choice == "Inventory":
    st.title("Inventory Overview")

    inventory, uoms = read_inventory()

    data = []
    for item in inventory:
        qty = inventory[item]
        uom = uoms.get(item, "pcs")

        status = "🟢 OK"

        if qty == 0:
            status = "🔴 No Stock"
        elif qty <= LOW_STOCK_THRESHOLD:
            status = "🟡 Low Stock"

        data.append({"Item": item, "Quantity": qty, "UOM": uom, "Status": status})

    st.dataframe(pd.DataFrame(data))

# =========================
# EQUIPMENT
# =========================
elif choice == "Equipment":
    st.title("Equipment Inventory")

    equipment_items = read_equipment_items()
    equipment_list = sorted(equipment_items.keys())

    eq_name = st.selectbox("Equipment", ["-- New --"] + equipment_list)

    if eq_name == "-- New --":
        eq_name = st.text_input("New Equipment Name")

    if eq_name:
        items = equipment_items.get(eq_name, {})

        df = pd.DataFrame([
            {"Item": k, "Quantity": v["qty"], "UOM": v["uom"]}
            for k, v in items.items()
        ])

        df = pd.concat([df, pd.DataFrame([{"Item": "", "Quantity": 0, "UOM": "pcs"}])])

        edited = st.data_editor(df, key=f"edit_{eq_name}", num_rows="dynamic")

        if st.button("Save Equipment Items"):

            old_items = equipment_items.get(eq_name, {})
            processed_items = set()

            # 🔥 gather all existing items
            all_items = [i for eq in equipment_items.values() for i in eq.keys()]

            for _, row in edited.iterrows():
                raw_item = row.get("Item")
                new_item = normalize_item_name(raw_item)

                if not new_item:
                    continue

                # 🔥 smart match
                for existing in all_items:
                    if clean_compare(existing) == clean_compare(new_item):
                        new_item = existing
                        break

                new_qty = int(row.get("Quantity", 0))
                uom = row.get("UOM", "pcs")

                matched_old = None
                for old_item in old_items:
                    if clean_compare(old_item) == clean_compare(new_item):
                        matched_old = old_item
                        break

                old_qty = old_items.get(matched_old, {}).get("qty", 0) if matched_old else 0

                if matched_old and matched_old != new_item:
                    append_equipment_stock(eq_name, matched_old, -old_qty, uom)
                    append_equipment_stock(eq_name, matched_old, KILL_QTY, uom)

                diff = new_qty - old_qty

                if diff != 0:
                    append_equipment_stock(eq_name, new_item, diff, uom)

                processed_items.add(new_item)

            for old_item, data in old_items.items():
                if old_item not in processed_items:
                    append_equipment_stock(eq_name, old_item, -data["qty"], data["uom"])
                    append_equipment_stock(eq_name, old_item, KILL_QTY, data["uom"])

            st.success("Saved successfully")
            st.rerun()
