# TAAS Fleet View Dashboard — Material group analysis month-to-month
# Co-authored with CoCo
import io
import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="TAAS Fleet View", layout="wide")
st.title("TAAS — General Fleet View Dashboard")

# Material description grouping rules
MATERIAL_GROUPS = {
    "Call Out": [
        "day-time call-out",
        "breakdown call handling fee",
        "extended day-time call-out",
        "fr highway ext day-time call-out",
        "fr highway \u2013 day time call out",
        "fr highway â\u20ac\u201c day time call out",
        "breakdown call handling",
        "night-time call-out",
        "stop&go call management fee",
        "weekend day-time call-out",
        "fr highway \u2013 night time call out",
        "fr highway â\u20ac\u201c night time call out",
        "weekend night-time call-out",
        "call-out",
        "call out",
        "callout",
    ],
    "Casing": ["casing"],
    "Geometry": ["geometry"],
    "Halo": ["halo", "ATIS (HALO) TIRE CHANGE", "ATIS (HALO) INITIAL INSTALLATION", "ATIS (HALO) RETORQUE"],
    "Handling Fee": [
        "handling fee pwt",
        "ejob handling fee",
        "ejob handling fee pwt",
        "handling fee - bs",
        "handling fee pwt - bs",
        "ejob handling fee pwt - bs",
        "ejob handling fee \u2013 bs",
        "ejob handling fee â\u20ac\u201c bs",
        "handling fee",
    ],
    "Inspection": ["night inspection supplement", "visual inspection with tread depth meass", "inspection"],
    "Misc Services": ["fos sp financial adjustment for services", "breakdown - extra cost service", "misc", "miscellaneous"],
    "Mounting": ["mounting"],
    "Mounting New Tire": ["taking tire off/on wheel (new tire) - bs", "taking tire off/on wheel (new tire)", "mounting new tire", "mounting new"],
    "Mounting Reuse": ["taking tire off/on wheel(reused tire)-bs", "taking tire off/on wheel (reused tire)", "mounting reuse", "reuse"],
    "Tire": ["tire"],
    "Regroove": ["regrooving block add cost", "regrooving â\u20ac\u201c bs", "regrooving \u2013 bs", "regrooving", "regroove"],
    "Repair": [
        "minor repair - bs",
        "puncture repair",
        "repair 1h/20km b/f balance repair-bs",
        "minor repair",
        "repair 2h/100km b/f balance repair-bs",
        "fix.6-8am/6-10pm balance repair-bs",
        "repair 1h15/40km b/f balance repair-bs",
        "fix.12-2pm balance/repair-bs",
        "repair 1h30/60km b/f balance repair-bs",
        "repair 2h30/120km b/f balance repair-bs",
        "fix.10pm-6am balance repair-bs",
        "major repair",
        "repair",
    ],
    "Rim": [
        "turn on rim â\u20ac\u201c bs",
        "turn on rim \u2013 bs",
        "turn on rim",
        "wheel rim steel",
        "wheel rim â\u20ac\u201c extra cost",
        "wheel rim \u2013 extra cost",
        "wheel rim",
        "rim 1175 - 22.5 alloy",
        "rim 1175 - 22.5 steel",
        "rim",
    ],
    "Small Material": ["small material"],
    "TPMS": ["tpms sensor allocation", "tpms sensor fitment", "strapping + tpms sensor initialization", "fitment of ps tpms sensor", "tpms"],
    "Travel": ["travel variable bs", "travel (variable)", "travel"],
    "DrivePoint": ["drivepoint valve tpms sensor", "on-valve sensor fitted (drivepoint"],
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
    for group, keywords in sorted(MATERIAL_GROUPS.items(), key=lambda x: -max(len(k) for k in x[1])):
        for kw in keywords:
            if kw in desc_lower:
                return group
    return "Other"


with st.sidebar:
    st.header("Upload Data")
    uploaded_file = st.file_uploader("Upload PO data (CSV or Parquet)", type=["csv", "parquet"])

if uploaded_file is None:
    st.info("Please upload PO data file (CSV or Parquet) to proceed. Use the export query in `export_taas_data.sql` to generate the file.")
    st.stop()

buf = io.BytesIO(uploaded_file.getvalue())
if uploaded_file.name.endswith(".parquet"):
    df = pd.read_parquet(buf)
else:
    df = pd.read_csv(buf)
del buf
df.columns = df.columns.str.upper().str.strip()

if df.empty:
    st.warning("No data returned. Check filters or file content.")
    st.stop()

# Ensure date columns
if "PO_POSTING_DATE" in df.columns:
    df["PO_POSTING_DATE"] = pd.to_datetime(df["PO_POSTING_DATE"], errors="coerce")
if "PO_POSTING_MONTH" not in df.columns and "PO_POSTING_DATE" in df.columns:
    df["PO_POSTING_MONTH"] = df["PO_POSTING_DATE"].dt.month

# Group customers by TAAS parent name
CUSTOMER_GROUP_KEYWORDS = ["Transalliance", "Garnier", "Veolia", "Taldea", "ID Logistics", "Eychenne", "Chatel"]

# Explicit mapping for customers whose names don't contain the group keyword
CUSTOMER_EXPLICIT_MAP = {
    "TRANSPORTS DUJEU": "Chatel",
    "TRANSPORTS LAPERCHE": "Chatel",
    "TRANSPORTS NICOLLE": "Chatel",
    "LETNA": "Chatel",
    "SOLETRANS": "Chatel",
    "TRANSPORTS JEAN DEVAY": "Chatel",
    "TRANSPORTS BESNARD": "Chatel",
    "CONSEILS ET INNOVATION SOLUTIONS": "Chatel",
    "LATASTE TRANSPORTS": "Taldea",
    "BL SOLUTIONS": "Taldea",
    "SARRATIA": "Taldea",
    "LES TRANSPORTS ROBERT": "Taldea",
    "TRANSPORTS DUMARTIN": "Taldea",
    "TRANSPORTS FOIX": "Taldea",
    "SODITRANS": "Taldea",
    "TRANSPORTS PEBROCQ": "Taldea",
    "BS SERVICES": "Taldea",
    "ELTRANS": "Garnier",
    "GLT": "Garnier",
    "TMG": "Garnier",
    "SOCIETE NOUVELLE COMATA": "Garnier",
    "TRANSPORTS DANIEL ET DEMONT": "Garnier",
    "VTB": "Garnier",
    "TRANSPORTS BONAFINI": "Garnier",
}


def assign_customer_group(name):
    if not isinstance(name, str):
        return "Other"
    name_upper = name.upper().strip()
    for key, group in CUSTOMER_EXPLICIT_MAP.items():
        if key in name_upper:
            return group
    name_lower = name.lower()
    for group in CUSTOMER_GROUP_KEYWORDS:
        if group.lower() in name_lower:
            return group
    return "Other"


df["CUSTOMER_GROUP"] = df["CUSTOMER_NAME"].apply(assign_customer_group)

# Classify materials
df["MATERIAL_GROUP"] = df["MATERIAL_DESC"].apply(classify_material)

# Sidebar filters
with st.sidebar:
    st.header("Filters")
    customer_groups = sorted([x for x in df["CUSTOMER_GROUP"].unique() if isinstance(x, str) and x != "Other"])
    if "Other" in df["CUSTOMER_GROUP"].unique():
        customer_groups.append("Other")
    selected_customers = st.multiselect("Customer Group", customer_groups, key="cust_filter")

    material_groups = sorted(df["MATERIAL_GROUP"].dropna().unique().tolist())
    selected_groups = st.multiselect("Material Group", material_groups, key="group_filter")

# Apply filters
filtered = df.copy()
if selected_customers:
    filtered = filtered[filtered["CUSTOMER_GROUP"].isin(selected_customers)]
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

pivot_monthly = month_group.pivot_table(
    index="MATERIAL_GROUP", columns="MONTH_NAME", values="TOTAL_EURO", fill_value=0
)
month_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
pivot_monthly = pivot_monthly[[m for m in month_order if m in pivot_monthly.columns]]
pivot_monthly["Total"] = pivot_monthly.sum(axis=1)
pivot_monthly = pivot_monthly.sort_values("Total", ascending=False)
pivot_monthly.index.name = "Material Group"

st.dataframe(pivot_monthly, use_container_width=True)

# Per-customer group breakdown
st.subheader("Customer Group × Material Group")

cust_group = (
    filtered.groupby(["CUSTOMER_GROUP", "MATERIAL_GROUP"])
    .agg(
        TOTAL_EURO=("NET_PRICE_EURO", "sum"),
        LINE_COUNT=("PO_QTY", "count"),
    )
    .reset_index()
    .sort_values("TOTAL_EURO", ascending=False)
)

with st.container(border=True):
    st.markdown("**€ Spend by Customer Group and Material Group**")
    pivot_cust = cust_group.pivot_table(
        index="CUSTOMER_GROUP", columns="MATERIAL_GROUP", values="TOTAL_EURO", fill_value=0
    )
    pivot_cust["Total"] = pivot_cust.sum(axis=1)
    pivot_cust = pivot_cust.sort_values("Total", ascending=False)
    st.dataframe(pivot_cust, use_container_width=True)
