import streamlit as st
import pandas as pd

# PAGE CONFIG
st.set_page_config(page_title="Shutdown Dashboard", layout="wide")

# LOAD DATA
df = pd.read_excel("data.xlsx")

# Clean column names
df.columns = df.columns.str.strip().str.lower()

# Debug: show column names
st.write("Columns:", df.columns)

# SIDEBAR FILTER
st.sidebar.title("Filters")

status_options = df["Status"].dropna().unique()
selected_status = st.sidebar.multiselect(
    "Select Status",
    options=status_options,
    default=status_options
)

filtered_df = df[df["Status"].isin(selected_status)]

# =========================
# 🎨 STYLING (MODERN UI)
# =========================
st.markdown("""
<style>
body {
    background-color: #0e1117;
}
[data-testid="stMetric"] {
    background-color: #1c1f26;
    padding: 15px;
    border-radius: 12px;
    text-align: center;
}
h1, h2, h3 {
    color: white;
}
</style>
""", unsafe_allow_html=True)

# =========================
# 🧾 TITLE
# =========================
st.title("⚡ Shutdown Monitoring Dashboard")

# =========================
# 🔢 KPI CARDS
# =========================
total = len(filtered_df)
completed = len(filtered_df[filtered_df["Status"] == "Completed"])
in_progress = len(filtered_df[filtered_df["Status"] == "In Progress"])
scheduled = len(filtered_df[filtered_df["Status"] == "Scheduled"])

col1, col2, col3, col4 = st.columns(4)

col1.metric("Total Shutdowns", total)
col2.metric("Completed", completed)
col3.metric("In Progress", in_progress)
col4.metric("Scheduled", scheduled)

# =========================
# 📊 CHART
# =========================
st.subheader("Shutdown Status Overview")

status_counts = filtered_df["Status"].value_counts()
st.bar_chart(status_counts)

# =========================
# 📅 OPTIONAL: DATE VIEW
# =========================
if "Sched. Start Date" in filtered_df.columns:
    st.subheader("Schedule Timeline")
    st.line_chart(filtered_df["Sched. Start Date"].value_counts().sort_index())

# =========================
# 📋 TABLE
# =========================
st.subheader("Work Orders")

st.dataframe(filtered_df, use_container_width=True)
