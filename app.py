import streamlit as st
import pandas as pd
import datetime
import os
import hashlib
from openpyxl import Workbook, load_workbook

st.title("TEST APP LOADED")
st.write("App started successfully")

# ---------- File Paths ----------
BASE_DIR = r"C:\Streamlit"
TRANSACTIONS_FILE = os.path.join(BASE_DIR, 'transactions_log.xlsx')
EQUIPMENT_FILE = os.path.join(BASE_DIR, 'equipment_stock.xlsx')
AUDIT_FILE = os.path.join(BASE_DIR, 'registration_audit.xlsx')
CREDENTIALS_FILE = os.path.join(BASE_DIR, 'user_credentials.xlsx')

LOW_STOCK_THRESHOLD = 5
MAX_STOCK_THRESHOLD = 20  # Example max stock threshold (can be adjusted or read from file)

# ---------- Authentication ----------
def ensure_workbook(file, headers):
    return  # Disable file creation in cloud

def load_user_credentials():
    ensure_workbook(CREDENTIALS_FILE, ['Username', 'Password', 'Role'])
    wb = load_workbook(CREDENTIALS_FILE)
    ws = wb.active
    credentials = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        username, password_hash, role = row
        if username and password_hash:
            credentials[username.upper()] = {"password": password_hash, "role": role}
    return credentials

def save_user_credentials(username, password, role="viewer"):
    ensure_workbook(CREDENTIALS_FILE, ['Username', 'Password', 'Role'])
    wb = load_workbook(CREDENTIALS_FILE)
    ws = wb.active
    hashed_pw = hashlib.sha256(password.encode()).hexdigest()
    ws.append([username.upper(), hashed_pw, role])
    wb.save(CREDENTIALS_FILE)

def register_user(username, password):
    username = username.upper()
    creds = load_user_credentials()
    if username in creds:
        return False
    save_user_credentials(username, password)
    log_registration(username)
    return True

def authenticate(username, password):
    creds = load_user_credentials()
    user = creds.get(username.upper())
    if user:
        return hashlib.sha256(password.encode()).hexdigest() == user["password"]
    return False

def get_user_role(username):
    return "admin"

# ---------- Excel Utilities ----------
def read_inventory():
    ensure_workbook(EQUIPMENT_FILE, ['Timestamp', 'Equipment', 'Item', 'Qty', 'UOM'])
    wb = load_workbook(EQUIPMENT_FILE)
    ws = wb.active
    inventory = {}
    uoms = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row and row[2] and row[3] is not None:
            item = row[2]
            qty = int(row[3]) if isinstance(row[3], int) else 0
            uom = row[4] if len(row) > 4 and row[4] else "pcs"
            inventory[item] = inventory.get(item, 0) + qty
            uoms[item] = uom
    return inventory, uoms

def read_equipment_items():
    ensure_workbook(EQUIPMENT_FILE, ['Timestamp', 'Equipment', 'Item', 'Qty', 'UOM'])
    wb = load_workbook(EQUIPMENT_FILE)
    ws = wb.active
    equipment_dict = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        eq, item, qty = row[1], row[2], row[3]
        uom = row[4] if len(row) > 4 and row[4] else "pcs"
        if not eq or item is None:
            continue
        qty = int(qty) if isinstance(qty, int) else 0
        equipment_dict.setdefault(eq, {}).setdefault(item, {'qty': 0, 'uom': uom})
        equipment_dict[eq][item]['qty'] += qty
        equipment_dict[eq][item]['uom'] = uom
    return equipment_dict

def write_equipment_items(equipment_dict):
    wb = Workbook()
    ws = wb.active
    ws.append(['Timestamp', 'Equipment', 'Item', 'Qty', 'UOM'])
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for eq, items in equipment_dict.items():
        for item, data in items.items():
            ws.append([timestamp, eq, item, data['qty'], data['uom']])
    wb.save(EQUIPMENT_FILE)

def append_equipment_stock(equipment, item, qty, uom="pcs"):
    ensure_workbook(EQUIPMENT_FILE, ['Timestamp', 'Equipment', 'Item', 'Qty', 'UOM'])
    wb = load_workbook(EQUIPMENT_FILE)
    ws = wb.active
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ws.append([timestamp, equipment, item, qty, uom])
    wb.save(EQUIPMENT_FILE)

def log_transaction(action, item, quantity, person, mdr_number=None, equipment=None, uom="pcs"):
    ensure_workbook(TRANSACTIONS_FILE, ['Timestamp', 'Action', 'Item', 'Qty', 'UOM', 'Person', 'MDR No.', 'Equipment'])
    wb = load_workbook(TRANSACTIONS_FILE)
    ws = wb.active
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    qty_to_log = -quantity if action == "withdraw" else quantity
    ws.append([
        timestamp,
        action,
        item,
        qty_to_log,
        uom,
        person,
        mdr_number if action == "deliver" else "",  # ✅ fix: was "delivery", should be "deliver"
        equipment
    ])
    wb.save(TRANSACTIONS_FILE)
# ---------- Streamlit App ----------
def force_rerun():
    st.session_state['rerun_counter'] = st.session_state.get('rerun_counter', 0) + 1

st.set_page_config(page_title="Plant Inventory Monitoring", layout="wide")

st.session_state.authenticated = True
st.session_state.username = "admin"

st.write("Before auth check")

if not st.session_state.authenticated:
    st.title("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if authenticate(username, password):
            st.session_state.authenticated = True
            st.session_state.username = username
            st.success("Login successful")
            force_rerun()
        else:
            st.error("Invalid credentials")

    st.write("Don't have an account?")
    new_user = st.text_input("New Username")
    new_pass = st.text_input("New Password", type="password")
    if st.button("Register"):
        if register_user(new_user, new_pass):
            st.success("User registered successfully")
        else:
            st.warning("Username already exists")

else:
    username = st.session_state.username
    user_role = get_user_role(username)
    is_admin = (user_role == "admin")

    st.sidebar.title("Navigation")
    choice = st.sidebar.radio("Go to", ["Inventory", "Equipment", "Withdraw/Deliver", "Transactions", "Logout"])

    if choice == "Logout":
        st.session_state.authenticated = False
        st.session_state.username = ""
        force_rerun()

    elif choice == "Inventory":
        st.title("Inventory Overview")
        inventory, uoms = read_inventory()
        data = []
        for item in inventory:
            qty = inventory[item]
            uom = uoms.get(item, "pcs")

            # Stock status logic:
            if qty == 0:
                status = "🔴 No Stock: Purchase?"
            elif qty <= LOW_STOCK_THRESHOLD:
                status = "🟡 Running out of Stock"
            elif qty <= MAX_STOCK_THRESHOLD:
                status = "🟢 Stock OK"
            else:
                status = "🟢 Stock OK"

            data.append({"Item": item, "Quantity": qty, "UOM": uom, "Status": status})

        df = pd.DataFrame(data, columns=["Item", "Quantity", "UOM", "Status"])
        st.dataframe(df, use_container_width=True)

    elif choice == "Equipment":
        st.title("Equipment Inventory")
        equipment_items = read_equipment_items()
        equipment_list = sorted(equipment_items.keys())
        options = ["-- New Equipment --"] + equipment_list

        selected_eq = st.selectbox("Select Equipment", options)
        is_new = selected_eq == "-- New Equipment --"

        eq_name = ""
        if is_new:
            eq_name = st.text_input("Enter new equipment name")
        else:
            eq_name = st.text_input("Edit equipment name", value=selected_eq)

        if st.button("Save Equipment Name"):
            if not is_admin:
                st.warning("Only admins can add or rename equipment.")
            elif not eq_name.strip():
                st.warning("Equipment name cannot be empty.")
            elif is_new and eq_name in equipment_items:
                st.warning("Equipment already exists.")
            elif is_new:
                equipment_items[eq_name] = {}
                write_equipment_items(equipment_items)
                st.success(f"Equipment '{eq_name}' added.")
                force_rerun()
            elif eq_name != selected_eq:
                wb = load_workbook(EQUIPMENT_FILE)
                ws = wb.active
                for row in ws.iter_rows(min_row=2):
                    if row[1].value == selected_eq:
                        row[1].value = eq_name
                wb.save(EQUIPMENT_FILE)
                st.success(f"Renamed '{selected_eq}' to '{eq_name}'")
                force_rerun()

        if not is_new and st.button("Delete Equipment"):
            if not is_admin:
                st.warning("Only admins can delete equipment.")
            else:
                if eq_name in equipment_items:
                    del equipment_items[eq_name]
                    write_equipment_items(equipment_items)
                    st.success(f"Equipment '{eq_name}' deleted.")
                    force_rerun()

        if eq_name:
            items = equipment_items.get(eq_name, {})
            df_items = pd.DataFrame(
                [{"Item": item, "Quantity": data["qty"], "UOM": data["uom"]} for item, data in items.items()]
            )

            df_items = pd.concat([df_items, pd.DataFrame([{"Item": "", "Quantity": 0, "UOM": "pcs"}])], ignore_index=True)

            st.markdown("### Edit Item Quantities and UOM")
            edited_df = st.data_editor(df_items, num_rows="dynamic", use_container_width=True, key="equip_edit")

            if st.button("Save Equipment Items"):
                if not is_admin:
                    st.warning("Only admins can edit equipment items.")
                else:
                    # Remove empty rows
                    edited_df = edited_df.dropna(subset=['Item'])
                    edited_df = edited_df[edited_df['Item'] != ""]
                    # Build new equipment dict
                    equipment_items[eq_name] = {}
                    # Build new equipment dict
                    updated_items = {}
                    for _, row in edited_df.iterrows():
                        item = row['Item']
                        qty = int(row['Quantity']) if pd.notna(row['Quantity']) else 0
                        uom = row['UOM'] if pd.notna(row['UOM']) else "pcs"
                        updated_items[item] = {"qty": qty, "uom": uom}

                    # Update the main dictionary and write back to Excel
                    equipment_items[eq_name] = updated_items
                    write_equipment_items(equipment_items)
                    st.success("Equipment items updated successfully.")
                    force_rerun()

    elif choice == "Withdraw/Deliver":
        st.title("Withdraw or Deliver Items")
        if not is_admin:
            st.warning("Only admins can withdraw or deliver items.")
        else:
            equipment_items = read_equipment_items()
            equipment_list = sorted(equipment_items.keys())
            equipment_selected = st.selectbox("Select Equipment", equipment_list)

            if equipment_selected:
                items = equipment_items.get(equipment_selected, {})
                if not items:
                    st.info("No items available for this equipment.")
                else:
                    item_list = list(items.keys())
                    item_selected = st.selectbox("Select Item", item_list)

                    inventory, uoms = read_inventory()
                    total_qty = inventory.get(item_selected, 0)
                    uom = uoms.get(item_selected, "pcs")

                    st.write(f"Current Stock (Total): {total_qty} {uom}")

                    current_qty = items[item_selected]['qty']
                    st.write(f"Current Stock in '{equipment_selected}': {current_qty} {uom}")

                    if current_qty == 0:
                        if total_qty > 0:
                            st.warning("Withdraw Stocks from other Equipment")
                        else:
                            st.error("Follow up Purchase / MR")

                    action = st.radio("Action", ["Withdraw", "Deliver"])

                    if action == "Withdraw":
                        st.write(f"Maximum Withdrawal = {current_qty} {uom}")
                        qty = st.number_input("Quantity", min_value=0, max_value=current_qty, step=1)
                    else:
                        qty = st.number_input("Quantity", min_value=0, step=1)

                    person = st.text_input("Person in Charge")
                    mdr_number = None
                    if action == "Deliver":
                        mdr_number = st.text_input("MDR Number")
                    elif action == "Deliver" and not mdr_number.strip():
                        st.warning("Please enter MDR Number.")

                    # Disable submit button logic
                    disable_submit = (
                        (action == "Withdraw" and current_qty == 0) or
                        (action == "Withdraw" and qty == 0) or
                        (action == "Deliver" and qty == 0)
)

                    if disable_submit:
                        if current_qty == 0 and total_qty == 0:
                            st.error("Follow up Purchase / MR")
                        elif current_qty == 0 and total_qty > 0:
                            st.warning("Withdraw Stocks from other Equipment")

                    if st.button("Submit Transaction"):
                        if not person.strip():
                            st.warning("Please enter the person in charge.")
                        elif action == "Withdraw" and qty > current_qty:
                            st.warning(f"Cannot withdraw more than available quantity ({current_qty}).")
                        else:
                            if action == "Withdraw":
                                items[item_selected]['qty'] -= qty
                            else:
                                items[item_selected]['qty'] += qty

                            # Update Excel
                            write_equipment_items(equipment_items)

                            # Log the transaction
                            log_transaction(
                                action=action.lower(),
                                item=item_selected,
                                quantity=qty,
                                person=person,
                                mdr_number=mdr_number,
                                equipment=equipment_selected,
                                uom=uom
                            )

                            st.success(f"{action} successful.")
                            force_rerun()

    elif choice == "Transactions":
        st.title("Transaction Log")
        ensure_workbook(TRANSACTIONS_FILE, ['Timestamp', 'Action', 'Item', 'Qty', 'UOM', 'Person', 'MDR No.',      'Equipment'])
        wb = load_workbook(TRANSACTIONS_FILE)
        ws = wb.active
        rows = list(ws.iter_rows(min_row=2, values_only=True))
        if rows:
            df_log = pd.DataFrame(rows, columns=['Timestamp', 'Action', 'Item', 'Qty', 'UOM', 'Person', 'MDR No.', 'Equipment'])
            df_log['Timestamp'] = pd.to_datetime(df_log['Timestamp'])  # convert to datetime
            df_log = df_log.sort_values(by='Timestamp', ascending=False).reset_index(drop=True)
            st.dataframe(df_log.head(30), use_container_width=True)

        if is_admin and not df_log.empty:
            if st.button("Undo Last Transaction"):
                last_row = df_log.iloc[0]
                action = last_row['Action'].lower()
                item = last_row['Item']
                qty = int(last_row['Qty'])
                equipment = last_row['Equipment']
                inventory, _ = read_inventory()
                equipment_items = read_equipment_items()

                if equipment in equipment_items and item in equipment_items[equipment]:
                    if action == "withdraw":
                        equipment_items[equipment][item]['qty'] += abs(qty)
                    elif action == "deliver":
                        equipment_items[equipment][item]['qty'] -= abs(qty)

                    write_equipment_items(equipment_items)

                    # Remove from log
                    df_log = df_log.iloc[1:]
                    df_log.to_excel(TRANSACTIONS_FILE, index=False)

                    st.success("Last transaction undone.")
                    force_rerun()
        else:
            st.info("No transactions logged yet.")
