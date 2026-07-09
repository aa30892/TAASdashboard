# TAAS Fleet View Dashboard — Material group analysis month-to-month
# Co-authored with CoCo
import os
import io
import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="TAAS Fleet View", layout="wide")
st.title("TAAS — General Fleet View Dashboard")

# Material description grouping rules
MATERIAL_GROUPS = {
    "Call Out": ["call out", "callout"],
    "Casing": ["casing"],
    "Geometry": ["geometry"],
    "Halo": ["halo"],
    "Handling Fee": ["handling fee", "handling"],
    "Inspection": ["inspection"],
    "Misc Services": ["misc", "miscellaneous"],
    "Mounting": ["mounting"],
    "Mounting New Tire": ["mounting new tire", "mounting new"],
    "Mounting Reuse": ["mounting reuse", "reuse"],
    "Tire": ["tire"],
    "Regroove": ["regroove"],
    "Repair": ["repair"],
    "Rim": ["rim"],
    "Small Material": ["small material"],
    "TPMS": ["tpms"],
    "Travel": ["travel"],
    "Truck Tire": ["truck tire"],
}

TAAS_CUSTOMERS = [
    "Transalliance", "Garnier", "Veolia", "Taldea",
    "ID Logistics", "Eychenne", "Chatel",
]


def classify_material(desc):
    if not isinstance(desc, str):
        return "Other"
    desc_lower = desc.lower().strip()
    # Check specific multi-word groups first (longer matches first)
    for group, keywords in sorted(MATERIAL_GROUPS.items(), key=lambda x: -max(len(k) for k in x[1])):
        for kw in keywords:
            if kw in desc_lower:
                return group
    return "Other"


def load_from_snowflake():
    conn = st.connection("snowflake", ttl=os.getenv("SNOWFLAKE_CONNECTION_TTL"))
    query = """
    SELECT
        CUSTOMER_NAME, PO_POSTING_DATE, PO_POSTING_MONTH,
        MATERIAL_ID, MATERIAL_DESC, MATERIAL_GROUP_DESC,
        VEHICLE_ID, LICENCE_PLATE, VENDOR_NAME,
        JOB_NOTIFICATION_ID, JOB_TYPE_CODE, FLEET_TYPE,
        PO_QTY, NET_PRICE_EURO
    FROM PROD.EU_INSIGHT.FOS_PURCHASE_ORDER_DATA
    WHERE PO_POSTING_YEAR = 2026
      AND PO_POSTING_MONTH BETWEEN 1 AND 6
      AND CUSTOMER_NAME ILIKE ANY ('%Transalliance%', '%Garnier%', '%Veolia%',
                                    '%Taldea%', '%ID Logistics%', '%Eychenne%', '%Chatel%')
    """
    return conn.query(query)


with st.sidebar:
    st.header("Data Source")
    data_source = st.radio(
        "Load data from:",
        ["Snowflake (Live)", "Upload File (CSV/Parquet)"],
        key="data_source",
    )

    if data_source == "Upload File (CSV/Parquet)":
        uploaded_file = st.file_uploader("Upload PO data", type=["csv", "parquet"])
    else:
        uploaded_file = None

if data_source == "Snowflake (Live)":
    with st.spinner("Loading data from Snowflake..."):
        df = load_from_snowflake()
elif uploaded_file is not None:
    buf = io.BytesIO(uploaded_file.getvalue())
    if uploaded_file.name.endswith(".parquet"):
        df = pd.read_parquet(buf)
    else:
        df = pd.read_csv(buf)
    del buf
    df.columns = df.columns.str.upper().str.strip()
else:
    st.info("Please select a data source or upload a file.")
    st.stop()

if df.empty:
    st.warning("No data returned. Check filters or file content.")
    st.stop()

# Ensure date columns
if "PO_POSTING_DATE" in df.columns:
    df["PO_POSTING_DATE"] = pd.to_datetime(df["PO_POSTING_DATE"], errors="coerce")
if "PO_POSTING_MONTH" not in df.columns and "PO_POSTING_DATE" in df.columns:
    df["PO_POSTING_MONTH"] = df["PO_POSTING_DATE"].dt.month

# Classify materials
df["MATERIAL_GROUP"] = df["MATERIAL_DESC"].apply(classify_material)

# Sidebar filters
with st.sidebar:
    st.header("Filters")
    customers = sorted([x for x in df["CUSTOMER_NAME"].dropna().unique() if isinstance(x, str) and x.strip()])
    selected_customers = st.multiselect("Customer", customers, key="cust_filter")

    material_groups = sorted(df["MATERIAL_GROUP"].dropna().unique().tolist())
    selected_groups = st.multiselect("Material Group", material_groups, key="group_filter")

# Apply filters
filtered = df.copy()
if selected_customers:
    filtered = filtered[filtered["CUSTOMER_NAME"].isin(selected_customers)]
if selected_groups:
    filtered = filtered[filtered["MATERIAL_GROUP"].isin(selected_groups)]

st.metric("Total Records", f"{len(filtered):,}", border=True)

# Month-to-month analysis by material group
st.subheader("Material Group Totals — Month to Month")

month_group = (
    filtered.groupby(["PO_POSTING_MONTH", "MATERIAL_GROUP"])
    .agg(
        TOTAL_QTY=("PO_QTY", "sum"),
        TOTAL_EURO=("NET_PRICE_EURO", "sum"),
        LINE_COUNT=("PO_QTY", "count"),
    )
    .reset_index()
)

month_names = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
               7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}
month_group["MONTH_NAME"] = month_group["PO_POSTING_MONTH"].map(month_names)

# Pivot for chart: euros by group per month
col1, col2 = st.columns(2)

with col1:
    with st.container(border=True):
        st.markdown("**€ Total per Material Group by Month**")
        pivot_euro = month_group.pivot_table(
            index="MONTH_NAME", columns="MATERIAL_GROUP", values="TOTAL_EURO", fill_value=0
        )
        # Sort months
        month_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
        pivot_euro = pivot_euro.reindex([m for m in month_order if m in pivot_euro.index])
        st.bar_chart(pivot_euro)

with col2:
    with st.container(border=True):
        st.markdown("**Line Count per Material Group by Month**")
        pivot_count = month_group.pivot_table(
            index="MONTH_NAME", columns="MATERIAL_GROUP", values="LINE_COUNT", fill_value=0
        )
        pivot_count = pivot_count.reindex([m for m in month_order if m in pivot_count.index])
        st.bar_chart(pivot_count)

# Summary table
st.subheader("Summary by Material Group")

group_summary = (
    filtered.groupby("MATERIAL_GROUP")
    .agg(
        TOTAL_QTY=("PO_QTY", "sum"),
        TOTAL_EURO=("NET_PRICE_EURO", "sum"),
        LINE_COUNT=("PO_QTY", "count"),
        UNIQUE_MATERIALS=("MATERIAL_DESC", "nunique"),
    )
    .reset_index()
    .sort_values("TOTAL_EURO", ascending=False)
    .reset_index(drop=True)
)

with st.container(horizontal=True):
    st.metric("Material Groups", len(group_summary), border=True)
    st.metric("Total € Spend", f"{group_summary['TOTAL_EURO'].sum():,.2f}", border=True)
    st.metric("Total Qty", f"{group_summary['TOTAL_QTY'].sum():,.0f}", border=True)

st.dataframe(
    group_summary.rename(columns={
        "MATERIAL_GROUP": "Material Group",
        "TOTAL_QTY": "Total Qty",
        "TOTAL_EURO": "Total € (Net Price)",
        "LINE_COUNT": "PO Lines",
        "UNIQUE_MATERIALS": "Unique Materials",
    }),
    hide_index=True,
    use_container_width=True,
)

# Monthly detail table
st.subheader("Monthly Breakdown")

st.dataframe(
    month_group.rename(columns={
        "PO_POSTING_MONTH": "Month #",
        "MONTH_NAME": "Month",
        "MATERIAL_GROUP": "Material Group",
        "TOTAL_QTY": "Total Qty",
        "TOTAL_EURO": "Total € (Net Price)",
        "LINE_COUNT": "PO Lines",
    }).sort_values(["Month #", "Material Group"]),
    hide_index=True,
    use_container_width=True,
)

# Per-customer breakdown
st.subheader("Customer × Material Group")

cust_group = (
    filtered.groupby(["CUSTOMER_NAME", "MATERIAL_GROUP"])
    .agg(
        TOTAL_EURO=("NET_PRICE_EURO", "sum"),
        LINE_COUNT=("PO_QTY", "count"),
    )
    .reset_index()
    .sort_values("TOTAL_EURO", ascending=False)
)

with st.container(border=True):
    st.markdown("**€ Spend by Customer and Material Group**")
    pivot_cust = cust_group.pivot_table(
        index="CUSTOMER_NAME", columns="MATERIAL_GROUP", values="TOTAL_EURO", fill_value=0
    ).sort_values(by=list(cust_group["MATERIAL_GROUP"].unique())[:1] if not cust_group.empty else [], ascending=False)
    st.dataframe(pivot_cust, use_container_width=True)
