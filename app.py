import streamlit as st
import pandas as pd
import datetime
import gspread
import time
from oauth2client.service_account import ServiceAccountCredentials

SHEET_ID = "1Z-DPnZlZqZsAGWdAT8S-a2RUN9tqR0rnOMs3519VbBg"
LOW_STOCK_THRESHOLD = 5

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
# SAFE READ (WITH RETRY)
# =========================
def safe_read_sheet(sheet):
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

    data = safe_read_sheet(sheet)
    df = pd.DataFrame(data)

    equipment_dict = {}

    for _, row in df.iterrows():
        eq = row.get("Equipment")
        item = normalize_item_name(row.get("Item"))

        qty_raw = row.get("Qty", 0)
        try:
            qty = int(qty_raw)
        except:
            qty = 0

        uom = row.get("UOM", "pcs")

        if not eq or not item:
            continue

        if eq not in equipment_dict:
            equipment_dict[eq] = {}

        if item not in equipment_dict[eq]:
            equipment_dict[eq][item] = {"qty": 0, "uom": uom}

        equipment_dict[eq][item]["qty"] += qty

    # remove zero/negative
    for eq in list(equipment_dict.keys()):
        for item in list(equipment_dict[eq].keys()):
            if equipment_dict[eq][item]["qty"] <= 0:
                del equipment_dict[eq][item]

    return equipment_dict

# =========================
# READ INVENTORY
# =========================
def read_inventory():
    client = connect_gsheet()
    sheet = client.open_by_key(SHEET_ID).worksheet("equipment_stock")

    data = safe_read_sheet(sheet)
    df = pd.DataFrame(data)

    inventory = {}
    uoms = {}

    for _, row in df.iterrows():
        item = normalize_item_name(row.get("Item"))

        qty_raw = row.get("Qty", 0)
        try:
            qty = int(qty_raw)
        except:
            qty = 0

        uom = row.get("UOM", "pcs")

        if not item:
            continue

        inventory[item] = inventory.get(item, 0) + qty
        uoms[item] = uom

    for item in list(inventory.keys()):
        if inventory[item] <= 0:
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
        mdr if action == "Deliver" else "",
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
        if qty <= LOW_STOCK_THRESHOLD:
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

        df = pd.concat([df, pd.DataFrame([{"Item":"", "Quantity":0, "UOM":"pcs"}])])

        edited = st.data_editor(df, key=f"edit_{eq_name}", num_rows="dynamic")

        if st.button("Save Equipment Items"):

            for _, row in edited.iterrows():
                item = normalize_item_name(row.get("Item"))
                if not item:
                    continue

                qty = int(row.get("Quantity", 0))

                # 🔥 FIX: skip zero
                if qty <= 0:
                    continue

                uom = row.get("UOM", "pcs")

                append_equipment_stock(eq_name, item, qty, uom)

            st.success("Saved successfully")
            st.rerun()

# =========================
# WITHDRAW / DELIVER
# =========================
elif choice == "Withdraw/Deliver":
    st.title("Withdraw / Deliver")

    equipment_items = read_equipment_items()
    equipment = st.selectbox("Equipment", list(equipment_items.keys()))

    if equipment:
        items = equipment_items[equipment]
        item = st.selectbox("Item", list(items.keys()))

        current_qty = items[item]["qty"]
        uom = items[item]["uom"]

        action = st.radio("Action", ["Withdraw", "Deliver"])
        qty = st.number_input("Qty", min_value=0)
        person = st.text_input("Person")

        mdr = st.text_input("MDR") if action == "Deliver" else None

        if st.button("Submit") and qty > 0:
            append_equipment_stock(
                equipment,
                item,
                -qty if action == "Withdraw" else qty,
                uom
            )

            log_transaction(action, item, qty, person, mdr, equipment, uom)

            st.success("Done")
            st.rerun()

# =========================
# TRANSACTIONS
# =========================
elif choice == "Transactions":
    st.title("Transactions")

    client = connect_gsheet()
    sheet = client.open_by_key(SHEET_ID).worksheet("transactions_log")
    data = safe_read_sheet(sheet)
    df = pd.DataFrame(data)

    if not df.empty:
        df["Timestamp"] = pd.to_datetime(df["Timestamp"])
        st.dataframe(df.sort_values(by="Timestamp", ascending=False))
