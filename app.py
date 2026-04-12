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
# APPEND STOCK
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
# READ EQUIPMENT
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

        item = normalize_item_name(item)

        if not item:
            continue

        if item not in equipment_dict[eq]:
            equipment_dict[eq][item] = {"qty": 0, "uom": uom}

        equipment_dict[eq][item]["qty"] += qty

    # remove zero items
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

    df = pd.DataFrame(sheet.get_all_records())
    inventory = {}
    uoms = {}

    for _, row in df.iterrows():
        item = normalize_item_name(row.get("Item"))
        qty = int(row.get("Qty", 0))
        uom = row.get("UOM", "pcs")

        if not item:
            continue

        inventory[item] = inventory.get(item, 0) + qty
        uoms[item] = uom

    # remove zero items
    for item in list(inventory.keys()):
        if inventory[item] <= 0:
            del inventory[item]

    return inventory, uoms

# =========================
# GET ALL ITEMS
# =========================
def get_all_items():
    inventory, _ = read_inventory()
    return sorted(inventory.keys())

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
st.sidebar.title("David Hertz Monitoring")

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

    st.dataframe(pd.DataFrame(data), use_container_width=True)

# =========================
# EQUIPMENT
# =========================
elif choice == "Equipment":
    st.title("Equipment Inventory")

    equipment_items = read_equipment_items()
    equipment_list = sorted(equipment_items.keys())

    eq_name = st.selectbox("Select Equipment", ["-- New --"] + equipment_list)

    if eq_name == "-- New --":
        eq_name = st.text_input("New Equipment Name")

    if eq_name:
        items = equipment_items.get(eq_name, {})

        df = pd.DataFrame([
            {"Item": k, "Quantity": v["qty"], "UOM": v["uom"]}
            for k, v in items.items()
        ])

        df = pd.concat([df, pd.DataFrame([{"Item":"", "Quantity":0, "UOM":"pcs"}])])

        edited = st.data_editor(
            df,
            key=f"edit_{eq_name}",
            num_rows="dynamic",
            column_config={
                "Item": st.column_config.TextColumn("Item")
            }
        )

        if st.button("Save Equipment Items", key=f"save_items_{eq_name}"):

            if st.session_state.get(f"saved_{eq_name}", False):
                st.warning("Already saved.")
                st.stop()

            st.session_state[f"saved_{eq_name}"] = True

            edited.columns = [str(col).strip().upper() for col in edited.columns]

            edited = edited.dropna(subset=["ITEM"])
            edited = edited[edited["ITEM"] != ""]

            updated_items = {}
            all_items = get_all_items()

            for _, row in edited.iterrows():
                item_input = normalize_item_name(row.get("ITEM"))

                if not item_input:
                    continue

                matched_item = next(
                    (i for i in all_items if normalize_item_name(i).replace(" ", "") == item_input.replace(" ", "")),
                    item_input
                )

                qty = int(row.get("QUANTITY", 0)) if pd.notna(row.get("QUANTITY")) else 0
                uom = row.get("UOM", "pcs") or "pcs"

                updated_items[matched_item] = {"qty": qty, "uom": uom}

            old_items = equipment_items.get(eq_name, {})

            if updated_items == old_items:
                st.info("No changes detected.")
                st.session_state[f"saved_{eq_name}"] = False
                st.stop()

            # FIXED: correct reset
            for item, data in old_items.items():
                append_equipment_stock(eq_name, item, -data["qty"], data["uom"])

            # FIXED: correct add
            for item, data in updated_items.items():
                append_equipment_stock(eq_name, item, data["qty"], data["uom"])

            st.success("Updated successfully")

            st.session_state[f"saved_{eq_name}"] = False
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

        inventory, _ = read_inventory()
        total_qty = inventory.get(item, 0)

        st.write(f"Total Stock: {total_qty} {uom}")
        st.write(f"Equipment Stock: {current_qty} {uom}")

        action = st.radio("Action", ["Withdraw", "Deliver"])
        qty = st.number_input("Quantity", min_value=0)
        person = st.text_input("Person")

        mdr = None
        if action == "Deliver":
            mdr = st.text_input("MDR Number")

        if st.button("Submit"):

            if action == "Withdraw":
                append_equipment_stock(equipment, item, -qty, uom)
            else:
                append_equipment_stock(equipment, item, qty, uom)

            log_transaction(action, item, qty, person, mdr, equipment, uom)

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

        if st.button("Undo Last Transaction"):
            last = df.iloc[0]

            append_equipment_stock(
                last["Equipment"],
                last["Item"],
                -int(last["Qty"]),
                last["UOM"]
            )

            st.success("Reversed last transaction")
            st.rerun()
