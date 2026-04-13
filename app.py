import streamlit as st
import pandas as pd
import datetime
import gspread
import time
from oauth2client.service_account import ServiceAccountCredentials

SHEET_ID = "1Z-DPnZlZqZsAGWdAT8S-a2RUN9tqR0rnOMs3519VbBg"
LOW_STOCK_THRESHOLD = 5
KILL_QTY = -999999

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
# GSHEET
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

def safe_read(sheet):
    for _ in range(3):
        try:
            return sheet.get_all_records()
        except:
            time.sleep(1)
    return []

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

    killed = set()
    for _, r in df.iterrows():
        eq = r.get("Equipment")
        item = normalize_item_name(r.get("Item"))
        try: qty = int(r.get("Qty", 0))
        except: qty = 0
        if qty <= KILL_QTY:
            killed.add((eq, item))

    for _, r in df.iterrows():
        eq = r.get("Equipment")
        item = normalize_item_name(r.get("Item"))
        try: qty = int(r.get("Qty", 0))
        except: qty = 0
        uom = r.get("UOM", "pcs")

        if not eq or not item: continue
        if (eq, item) in killed: continue

        equipment_dict.setdefault(eq, {})
        equipment_dict[eq].setdefault(item, {"qty": 0, "uom": uom})
        equipment_dict[eq][item]["qty"] += qty

    return equipment_dict

# =========================
# READ INVENTORY
# =========================
def read_inventory():
    client = connect_gsheet()
    sheet = client.open_by_key(SHEET_ID).worksheet("equipment_stock")

    df = pd.DataFrame(safe_read(sheet))
    inventory, uoms = {}, {}

    killed = set()
    for _, r in df.iterrows():
        item = normalize_item_name(r.get("Item"))
        try: qty = int(r.get("Qty", 0))
        except: qty = 0
        if qty <= KILL_QTY:
            killed.add(item)

    for _, r in df.iterrows():
        item = normalize_item_name(r.get("Item"))
        try: qty = int(r.get("Qty", 0))
        except: qty = 0
        uom = r.get("UOM", "pcs")

        if not item or item in killed: continue
        inventory[item] = inventory.get(item, 0) + qty
        uoms[item] = uom

    return inventory, uoms

# =========================
# LOG
# =========================
def log_transaction(action, item, qty, person, mdr, equipment, uom):
    client = connect_gsheet()
    sheet = client.open_by_key(SHEET_ID).worksheet("transactions_log")

    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    qty_signed = -qty if action == "Withdraw" else qty

    sheet.append_row([
        timestamp, action, item, qty_signed, uom, person, mdr, equipment
    ])

# =========================
# UI
# =========================
st.set_page_config(layout="wide")
menu = ["Inventory", "Equipment", "Withdraw/Deliver", "Transactions"]
choice = st.sidebar.radio("Go to", menu)

# =========================
# INVENTORY + DASHBOARD
# =========================
if choice == "Inventory":
    st.title("📦 Inventory Dashboard")

    inventory, uoms = read_inventory()

    data = []
    for item in inventory:
        qty = inventory[item]
        status = "🟢 OK" if qty > LOW_STOCK_THRESHOLD else "🟡 Low"
        data.append({"Item": item, "Qty": qty, "Status": status})

    df = pd.DataFrame(data)

    col1, col2 = st.columns(2)
    col1.metric("Total Items", len(df))
    col2.metric("Low Stock", len(df[df["Qty"] <= LOW_STOCK_THRESHOLD]))

    st.dataframe(df)

# =========================
# EQUIPMENT
# =========================
elif choice == "Equipment":
    st.title("Equipment Inventory")

    equipment_items = read_equipment_items()
    eq_name = st.selectbox("Equipment", ["-- New --"] + list(equipment_items.keys()))

    if eq_name == "-- New --":
        eq_name = st.text_input("New Equipment Name")

    if eq_name:
        items = equipment_items.get(eq_name, {})

        df = pd.DataFrame([
            {"Item": k, "Quantity": v["qty"], "UOM": v["uom"]}
            for k, v in items.items()
        ])

        edited = st.data_editor(df, num_rows="dynamic")

        if st.button("Save"):
            old_items = items
            processed = set()

            for _, row in edited.iterrows():
                new_item = normalize_item_name(row["Item"])
                if not new_item: continue

                new_qty = int(row["Quantity"])
                uom = row["UOM"]

                matched = None
                for old in old_items:
                    if clean_compare(old) == clean_compare(new_item):
                        matched = old

                old_qty = old_items.get(matched, {}).get("qty", 0)

                if matched and matched != new_item:
                    append_equipment_stock(eq_name, matched, -old_qty, uom)
                    append_equipment_stock(eq_name, matched, KILL_QTY, uom)

                diff = new_qty - old_qty
                if diff != 0:
                    append_equipment_stock(eq_name, new_item, diff, uom)

                processed.add(new_item)

            for old, data in old_items.items():
                if old not in processed:
                    append_equipment_stock(eq_name, old, -data["qty"], data["uom"])
                    append_equipment_stock(eq_name, old, KILL_QTY, data["uom"])

            st.success("Saved")
            st.rerun()

# =========================
# WITHDRAW / DELIVER / TRANSFER
# =========================
elif choice == "Withdraw/Deliver":
    st.title("Transactions")

    if "submitted" not in st.session_state:
        st.session_state.submitted = False

    equipment_items = read_equipment_items()
    equipment = st.selectbox("From Equipment", list(equipment_items.keys()))

    if equipment:
        items = equipment_items[equipment]
        item = st.selectbox("Item", list(items.keys()))

        current_qty = items[item]["qty"]
        uom = items[item]["uom"]

        inventory, _ = read_inventory()
        total_qty = inventory.get(item, 0)

        st.write(f"Total: {total_qty} | Equipment: {current_qty}")

        action = st.radio("Action", ["Withdraw", "Deliver", "Transfer"])
        qty = st.number_input("Qty", min_value=0)
        person = st.text_input("Person")

        if action == "Transfer":
            target = st.selectbox("To Equipment", [e for e in equipment_items if e != equipment])

        confirm = st.checkbox("Confirm")

        if st.session_state.submitted:
            st.success("Done")
            if st.button("New"):
                st.session_state.submitted = False
                st.rerun()

        else:
            if st.button("Submit"):

                if not confirm:
                    st.warning("Confirm first")
                    st.stop()

                if qty <= 0:
                    st.warning("Invalid qty")
                    st.stop()

                if not person:
                    st.warning("Enter name")
                    st.stop()

                if action == "Withdraw" and qty > current_qty:
                    st.error("Not enough stock")
                    st.stop()

                if action == "Transfer":
                    append_equipment_stock(equipment, item, -qty, uom)
                    append_equipment_stock(target, item, qty, uom)

                    log_transaction("Transfer OUT", item, qty, person, "", equipment, uom)
                    log_transaction("Transfer IN", item, qty, person, "", target, uom)

                else:
                    change = -qty if action == "Withdraw" else qty
                    append_equipment_stock(equipment, item, change, uom)
                    log_transaction(action, item, qty, person, "", equipment, uom)

                st.session_state.submitted = True

                st.success(f"{action} done by {person}")
                st.markdown("### Receipt")
                st.write(item, qty, equipment)

                st.rerun()

# =========================
# TRANSACTIONS
# =========================
elif choice == "Transactions":
    st.title("Logs")

    client = connect_gsheet()
    sheet = client.open_by_key(SHEET_ID).worksheet("transactions_log")

    df = pd.DataFrame(safe_read(sheet))

    if not df.empty:
        df["Timestamp"] = pd.to_datetime(df["Timestamp"])
        df = df.sort_values(by="Timestamp", ascending=False)

        st.dataframe(df)

        st.subheader("Top Used Items")
        top = df.groupby("Item")["Qty"].sum().abs().sort_values(ascending=False).head(10)
        st.bar_chart(top)
