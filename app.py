import streamlit as st
import pandas as pd
import datetime
import gspread
import time
import re
from oauth2client.service_account import ServiceAccountCredentials

SHEET_ID = "1Z-DPnZlZqZsAGWdAT8S-a2RUN9tqR0rnOMs3519VbBg"
LOW_STOCK_THRESHOLD = 5
KILL_QTY = -999999

# =========================
# CACHE
# =========================
@st.cache_data(ttl=5)
def get_sheet_data():
    client = connect_gsheet()
    sheet = client.open_by_key(SHEET_ID).worksheet("equipment_stock")
    return pd.DataFrame(safe_read(sheet))

# =========================
# NORMALIZE
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
# GET ALL ITEMS (for suggestion)
# =========================
def get_all_items():
    df = get_sheet_data()
    items = df["Item"].dropna().unique().tolist()
    return sorted([normalize_item_name(i) for i in items if i])

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
    df = get_sheet_data()
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

    return equipment_dict

# =========================
# READ INVENTORY (FIXED)
# =========================
def read_inventory():
    df = get_sheet_data()

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

    return inventory, uoms

# =========================
# UI
# =========================
st.set_page_config(layout="wide")
menu = ["Inventory", "Equipment"]
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

        data.append({
            "Item": item,
            "Quantity": qty,
            "UOM": uom,
            "Status": status
        })

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

        # ===== ITEM INPUT (SUGGESTION) =====
        all_items = get_all_items()

        col1, col2 = st.columns([2, 1])

        with col1:
            item_input = st.text_input("Item (type or select)")

        with col2:
            suggestion = st.selectbox("Suggestions", [""] + all_items)

        item = normalize_item_name(item_input if item_input else suggestion)

        # ===== DELETE ITEM =====
        st.subheader("Delete Item")

        delete_item = st.selectbox(
            "Select item to delete",
            [""] + list(items.keys())
        )

        confirm_delete = st.checkbox("Confirm delete")

        if delete_item and confirm_delete:
            if st.button("Delete Item"):
                data = items.get(delete_item)

                append_equipment_stock(eq_name, delete_item, -data["qty"])
                append_equipment_stock(eq_name, delete_item, KILL_QTY)

                st.success("Item deleted")
                st.rerun()

        # ===== RENAME EQUIPMENT =====
        st.subheader("Rename Equipment")

        new_eq_name = st.text_input("New Equipment Name", value=eq_name)

        if new_eq_name and new_eq_name != eq_name:
            confirm = st.checkbox("Confirm rename")

            if confirm:
                if st.button("Rename Equipment"):

                    for item_name, data in items.items():
                        append_equipment_stock(eq_name, item_name, -data["qty"])
                        append_equipment_stock(eq_name, item_name, KILL_QTY)
                        append_equipment_stock(new_eq_name, item_name, data["qty"])

                    st.success("Renamed successfully")
                    st.rerun()

        # ===== DELETE EQUIPMENT =====
        st.subheader("Delete Equipment")

        if st.checkbox("Enable delete equipment"):
            if st.button("Delete Equipment"):

                for item_name, data in items.items():
                    append_equipment_stock(eq_name, item_name, -data["qty"])
                    append_equipment_stock(eq_name, item_name, KILL_QTY)

                st.success("Equipment deleted")
                st.rerun()
