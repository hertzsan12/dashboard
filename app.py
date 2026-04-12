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

    qty_signed = -qty if action == "withdraw" else qty

    sheet.append_row([
        timestamp,
        action,
        item,
        qty_signed,
        uom,
        person,
        mdr if action == "deliver" else "",
        equipment
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

    return inventory, uoms

# =========================
# LOG TRANSACTION
# =========================
def log_transaction(action, item, qty, person, mdr, equipment, uom):
    client = connect_gsheet()
    sheet = client.open_by_key(SHEET_ID).worksheet("transactions_log")

    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    qty_signed = -qty if action == "withdraw" else qty

    sheet.append_row([
        timestamp,
        action,
        item,
        qty_signed,
        uom,
        person,
        mdr if action == "deliver" else "",
        equipment
    ])

# =========================
# UI
# =========================
st.set_page_config(layout="wide")

st.sidebar.title("David Hertz Monitoring")
menu = ["Inventory", "Equipment", "Withdraw/Deliver", "Transactions"]
choice = st.sidebar.radio("Go to", menu)

is_admin = True

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

        if st.button("Add Equipment"):
            append_equipment_stock(eq_name, "", 0, "")
            st.success("Added")
            st.rerun()

    if eq_name:
        items = equipment_items.get(eq_name, {})
    
        df = pd.DataFrame([
            {"Item": k, "Quantity": v["qty"], "UOM": v["uom"]}
            for k, v in items.items()
        ])
    
        df = pd.concat([df, pd.DataFrame([{"Item": "", "Quantity": 0, "UOM": "pcs"}])])
    
        # ✅ editor variable = edited
        edited = st.data_editor(df, key=f"edit_{eq_name}", num_rows="dynamic")
    
        if st.button("Save Equipment Items", key=f"save_items_{eq_name}"):
    
            if edited is None or not isinstance(edited, pd.DataFrame):
                st.error("No data to save.")
                st.stop()
    
            # 🔥 CLEAN COLUMNS
            edited.columns = [str(col).strip().title() for col in list(edited.columns)]
    
            if "Item" not in edited.columns:
                st.error("Column 'Item' not found.")
                st.write("Columns detected:", edited.columns)
                st.stop()
    
            # 🔥 CLEAN DATA
            edited = edited.dropna(subset=["Item"])
            edited = edited[edited["Item"] != ""]
    
            updated_items = {}
    
            for _, row in edited.iterrows():
                item = normalize_item_name(row["Item"])
                qty = int(row["Quantity"]) if pd.notna(row["Quantity"]) else 0
                uom = row["UOM"] if pd.notna(row["UOM"]) else "pcs"
    
                updated_items[item] = {"qty": qty, "uom": uom}
    
            # 🔥 REVERSE OLD
            old_items = equipment_items.get(eq_name, {})
            for item, data in old_items.items():
                append_equipment_stock(eq_name, item, -data["qty"], data["uom"])
    
            # 🔥 ADD NEW
            for item, data in updated_items.items():
                append_equipment_stock(eq_name, item, data["qty"], data["uom"])
    
            st.success("Updated successfully")
            st.rerun()

# =========================
# WITHDRAW / DELIVER
# =========================
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

        # 🔥 STOCK INFO
        st.write(f"Total Stock: {total_qty} {uom}")
        st.write(f"Equipment Stock: {current_qty} {uom}")

        if current_qty == 0:
            if total_qty > 0:
                st.warning("⚠️ Withdraw stocks from other equipment")
            else:
                st.error("🔴 Follow up Purchase / MR")

        # 🔥 INPUTS
        action = st.radio("Action", ["Withdraw", "Deliver"])
        qty = st.number_input("Quantity", min_value=0)

        person = st.text_input("Person in Charge")

        # ✅ MDR only for Deliver
        mdr = None
        if action == "Deliver":
            mdr = st.text_input("MDR Number", placeholder="Enter MDR reference...")

        # 🔥 DISABLE LOGIC
        disable_submit = (
            not person.strip() or
            (action == "Deliver" and not mdr) or
            (action == "Withdraw" and qty > current_qty) or
            qty == 0
        )

        # 🔥 SUBMIT
        if st.button("Submit", key="submit_tx", disabled=disable_submit):

            if not person.strip():
                st.warning("Please enter person in charge.")

            elif action == "Deliver" and not mdr:
                st.warning("⚠️ MDR Number is required for delivery.")

            elif action == "Withdraw" and qty > current_qty:
                st.error("❌ Cannot withdraw more than available stock.")

            else:
                if action == "Withdraw":
                    append_equipment_stock(equipment, item, -qty, uom)
                else:
                    append_equipment_stock(equipment, item, qty, uom)

                log_transaction(action, item, qty, person, mdr, equipment, uom)

                st.success("✅ Transaction recorded.")
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

            # 🔥 mark as canceled in transaction log
            sheet.append_row([
                datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "undo",
                last["Item"],
                -int(last["Qty"]),
                last["UOM"],
                "system",
                "CANCELED",
                last["Equipment"]
        ])

            st.success("Reversed last transaction")
            st.rerun()
