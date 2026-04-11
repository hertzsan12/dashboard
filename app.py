import streamlit as st
import pandas as pd
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# =========================
# CONFIG
# =========================
SHEET_ID = "1Z-DPnZlZqZsAGWdAT8S-a2RUN9tqR0rnOMs3519VbBg"

LOW_STOCK_THRESHOLD = 5
MAX_STOCK_THRESHOLD = 20

# =========================
# NORMALIZE ITEM NAMES
# =========================
def normalize_item_name(name):
    if not name:
        return ""

    name = name.upper().strip()
    name = name.replace(",", ", ")
    name = " ".join(name.split())

    return name

# =========================
# GOOGLE SHEETS CONNECTION
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
# APPEND STOCK (CORE ENGINE)
# =========================
def append_equipment_stock(equipment, item, qty, uom="pcs"):
    client = connect_gsheet()
    sheet = client.open_by_key(SHEET_ID).worksheet("equipment_stock")

    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    sheet.append_row([
        timestamp,
        equipment,
        item,
        qty,
        uom
    ])

# =========================
# READ EQUIPMENT ITEMS
# =========================
def read_equipment_items():
    client = connect_gsheet()
    sheet = client.open_by_key(SHEET_ID).worksheet("equipment_stock")

    df = pd.DataFrame(sheet.get_all_records())

    equipment_dict = {}

    for _, row in df.iterrows():
        eq = row.get("Equipment")
        item = row.get("Item")
        qty = int(row.get("Qty", 0))
        uom = row.get("UOM", "pcs")

        if not eq:
            continue

        if eq not in equipment_dict:
            equipment_dict[eq] = {}

        # RESET LOGIC
        if item == "__RESET__":
            equipment_dict[eq] = {}
            continue

        item = normalize_item_name(item)

        if not item:
            continue

        if item not in equipment_dict[eq]:
            equipment_dict[eq][item] = {"qty": 0, "uom": uom}

        equipment_dict[eq][item]["qty"] += qty

    return equipment_dict

# =========================
# READ INVENTORY (GLOBAL)
# =========================
def read_inventory():
    client = connect_gsheet()
    sheet = client.open_by_key(SHEET_ID).worksheet("equipment_stock")

    df = pd.DataFrame(sheet.get_all_records())

    inventory = {}
    uoms = {}

    for _, row in df.iterrows():
        item = normalize_item_name(row.get("Item"))
        qty = int(row.get("Qty", 0))
        uom = row.get("UOM", "pcs")

        if item == "__RESET__" or not item:
            continue

        inventory[item] = inventory.get(item, 0) + qty
        uoms[item] = uom

    return inventory, uoms

# =========================
# LOG TRANSACTION
# =========================
def log_transaction(action, item, quantity, person, mdr_number, equipment, uom):
    client = connect_gsheet()
    sheet = client.open_by_key(SHEET_ID).worksheet("transactions_log")

    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    sheet.append_row([
        timestamp,
        action,
        item,
        quantity,
        uom,
        person,
        mdr_number,
        equipment
    ])

# =========================
# UI
# =========================
st.set_page_config(layout="wide")

menu = ["Inventory", "Equipment", "Withdraw/Deliver", "Transactions"]
choice = st.sidebar.radio("Go to", menu)

is_admin = True  # simplify for now

# =========================
# INVENTORY PAGE
# =========================
if choice == "Inventory":
    st.title("Inventory Overview")

    inventory, uoms = read_inventory()

    data = []
    for item in inventory:
        qty = inventory[item]
        uom = uoms.get(item, "pcs")

        if qty == 0:
            status = "🔴 No Stock"
        elif qty <= LOW_STOCK_THRESHOLD:
            status = "🟡 Low Stock"
        else:
            status = "🟢 OK"

        data.append({
            "Item": item,
            "Quantity": qty,
            "UOM": uom,
            "Status": status
        })

    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True)

# =========================
# EQUIPMENT PAGE
# =========================
elif choice == "Equipment":
    st.title("Equipment Inventory")

    equipment_items = read_equipment_items()
    equipment_list = sorted(equipment_items.keys())
    options = ["-- New Equipment --"] + equipment_list

    selected_eq = st.selectbox("Select Equipment", options)
    is_new = selected_eq == "-- New Equipment --"

    eq_name = st.text_input(
        "Equipment Name",
        value="" if is_new else selected_eq
    )

    if st.button("Save Equipment Name", key="save_eq"):
        if eq_name.strip():
            append_equipment_stock(eq_name, "", 0, "")
            st.success("Equipment saved")
            st.rerun()

    if eq_name:
        items = equipment_items.get(eq_name, {})

        df_items = pd.DataFrame([
            {"Item": k, "Quantity": v["qty"], "UOM": v["uom"]}
            for k, v in items.items()
        ])

        df_items = pd.concat([
            df_items,
            pd.DataFrame([{"Item": "", "Quantity": 0, "UOM": "pcs"}])
        ], ignore_index=True)

        st.markdown("### Edit Item Quantities and UOM")

        edited_df = st.data_editor(
            df_items,
            num_rows="dynamic",
            key=f"editor_{eq_name}"
        )

        if st.button("Save Equipment Items", key=f"save_items_{eq_name}"):

            edited_df = edited_df.dropna(subset=["Item"])
            edited_df = edited_df[edited_df["Item"] != ""]

            append_equipment_stock(eq_name, "__RESET__", 0, "")

            for _, row in edited_df.iterrows():
                item = normalize_item_name(row["Item"])
                qty = int(row["Quantity"])
                uom = row["UOM"]

                append_equipment_stock(eq_name, item, qty, uom)

            st.success("Saved!")
            st.rerun()

# =========================
# WITHDRAW / DELIVER
# =========================
elif choice == "Withdraw/Deliver":
    st.title("Withdraw / Deliver")

    equipment_items = read_equipment_items()
    equipment_selected = st.selectbox("Equipment", list(equipment_items.keys()))

    if equipment_selected:
        items = equipment_items[equipment_selected]

        item_selected = st.selectbox("Item", list(items.keys()))
        uom = items[item_selected]["uom"]
        current_qty = items[item_selected]["qty"]

        st.write(f"Current: {current_qty} {uom}")

        action = st.radio("Action", ["Withdraw", "Deliver"])
        qty = st.number_input("Quantity", min_value=0)

        person = st.text_input("Person")
        mdr = st.text_input("MDR Number")

        if st.button("Submit", key="submit_tx"):
            if action == "Withdraw":
                append_equipment_stock(equipment_selected, item_selected, -qty, uom)
            else:
                append_equipment_stock(equipment_selected, item_selected, qty, uom)

            log_transaction(action, item_selected, qty, person, mdr, equipment_selected, uom)

            st.success("Transaction recorded")
            st.rerun()

# =========================
# TRANSACTIONS
# =========================
elif choice == "Transactions":
    st.title("Transactions")

    client = connect_gsheet()
    sheet = client.open_by_key(SHEET_ID).worksheet("transactions_log")

    df = pd.DataFrame(sheet.get_all_records())

    if not df.empty:
        df["Timestamp"] = pd.to_datetime(df["Timestamp"])
        df = df.sort_values(by="Timestamp", ascending=False)

        st.dataframe(df, use_container_width=True)
    else:
        st.info("No transactions yet")
