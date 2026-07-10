# TAAS Fleet View Dashboard — Material group analysis month-to-month
# Co-authored with CoCo
import io
import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="TAAS Fleet View", layout="wide")
st.title("TAAS — General Fleet View Dashboard")

MONTH_ORDER = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]

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

# Use CUSTOMER_GROUP and MATERIAL_GROUP from the SQL export directly
if "CUSTOMER_GROUP" not in df.columns:
    df["CUSTOMER_GROUP"] = "Other"
if "MATERIAL_GROUP" not in df.columns:
    df["MATERIAL_GROUP"] = "Other"

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

month_names = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
               7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}

tab_material, tab_vendor, tab_vehicle = st.tabs(["General Fleet View", "By Vendor", "Vehicle Level"])

# =============================================================================
# TAB 1: Material Group Analysis
# =============================================================================
with tab_material:
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
    month_group["MONTH_NAME"] = month_group["PO_POSTING_MONTH"].map(month_names)
    month_group["MONTH_NUM"] = month_group["PO_POSTING_MONTH"]

    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.markdown("**€ Total per Material Group by Month**")
            pivot_euro = month_group.pivot_table(
                index=["MONTH_NUM", "MONTH_NAME"], columns="MATERIAL_GROUP", values="TOTAL_EURO", fill_value=0
            )
            pivot_euro = pivot_euro.sort_index(level="MONTH_NUM")
            pivot_euro = pivot_euro.droplevel("MONTH_NUM")
            st.bar_chart(pivot_euro)

    with col2:
        with st.container(border=True):
            st.markdown("**Line Count per Material Group by Month**")
            pivot_count = month_group.pivot_table(
                index=["MONTH_NUM", "MONTH_NAME"], columns="MATERIAL_GROUP", values="LINE_COUNT", fill_value=0
            )
            pivot_count = pivot_count.sort_index(level="MONTH_NUM")
            pivot_count = pivot_count.droplevel("MONTH_NUM")
            st.bar_chart(pivot_count)

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

    st.subheader("Monthly Breakdown")

    pivot_monthly = month_group.pivot_table(
        index="MATERIAL_GROUP", columns="MONTH_NUM", values="TOTAL_EURO", fill_value=0
    )
    pivot_monthly = pivot_monthly.sort_index(axis=1)
    pivot_monthly.columns = [month_names[m] for m in pivot_monthly.columns]
    pivot_monthly["Total"] = pivot_monthly.sum(axis=1)
    pivot_monthly = pivot_monthly.sort_values("Total", ascending=False)
    pivot_monthly.index.name = "Material Group"
    st.dataframe(pivot_monthly, use_container_width=True)

    st.subheader("Monthly Quantity Breakdown")

    pivot_qty = month_group.pivot_table(
        index="MATERIAL_GROUP", columns="MONTH_NUM", values="TOTAL_QTY", fill_value=0
    )
    pivot_qty = pivot_qty.sort_index(axis=1)
    pivot_qty.columns = [month_names[m] for m in pivot_qty.columns]
    pivot_qty["Total"] = pivot_qty.sum(axis=1)
    pivot_qty = pivot_qty.sort_values("Total", ascending=False)
    pivot_qty.index.name = "Material Group"
    st.dataframe(pivot_qty, use_container_width=True)

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

# =============================================================================
# TAB 2: Vendor Analysis
# =============================================================================
with tab_vendor:
    st.subheader("Vendor Totals — Month to Month")

    month_vendor = (
        filtered.groupby(["PO_POSTING_MONTH", "VENDOR_NAME"])
        .agg(
            TOTAL_QTY=("PO_QTY", "sum"),
            TOTAL_EURO=("NET_PRICE_EURO", "sum"),
            LINE_COUNT=("PO_QTY", "count"),
        )
        .reset_index()
    )
    month_vendor["MONTH_NAME"] = month_vendor["PO_POSTING_MONTH"].map(month_names)
    month_vendor["MONTH_NUM"] = month_vendor["PO_POSTING_MONTH"]

    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.markdown("**€ Total per Vendor by Month**")
            pivot_euro_v = month_vendor.pivot_table(
                index=["MONTH_NUM", "MONTH_NAME"], columns="VENDOR_NAME", values="TOTAL_EURO", fill_value=0
            )
            pivot_euro_v = pivot_euro_v.sort_index(level="MONTH_NUM")
            pivot_euro_v = pivot_euro_v.droplevel("MONTH_NUM")
            st.bar_chart(pivot_euro_v)

    with col2:
        with st.container(border=True):
            st.markdown("**Line Count per Vendor by Month**")
            pivot_count_v = month_vendor.pivot_table(
                index=["MONTH_NUM", "MONTH_NAME"], columns="VENDOR_NAME", values="LINE_COUNT", fill_value=0
            )
            pivot_count_v = pivot_count_v.sort_index(level="MONTH_NUM")
            pivot_count_v = pivot_count_v.droplevel("MONTH_NUM")
            st.bar_chart(pivot_count_v)

    st.subheader("Summary by Vendor")

    vendor_summary = (
        filtered.groupby("VENDOR_NAME")
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
        st.metric("Vendors", len(vendor_summary), border=True)
        st.metric("Total € Spend", f"{vendor_summary['TOTAL_EURO'].sum():,.2f}", border=True)
        st.metric("Total Qty", f"{vendor_summary['TOTAL_QTY'].sum():,.0f}", border=True)

    st.dataframe(
        vendor_summary.rename(columns={
            "VENDOR_NAME": "Vendor",
            "TOTAL_QTY": "Total Qty",
            "TOTAL_EURO": "Total € (Net Price)",
            "LINE_COUNT": "PO Lines",
            "UNIQUE_MATERIALS": "Unique Materials",
        }),
        hide_index=True,
        use_container_width=True,
    )

    st.subheader("Monthly Breakdown")

    pivot_monthly_v = month_vendor.pivot_table(
        index="VENDOR_NAME", columns="MONTH_NUM", values="TOTAL_EURO", fill_value=0
    )
    pivot_monthly_v = pivot_monthly_v.sort_index(axis=1)
    pivot_monthly_v.columns = [month_names[m] for m in pivot_monthly_v.columns]
    pivot_monthly_v["Total"] = pivot_monthly_v.sum(axis=1)
    pivot_monthly_v = pivot_monthly_v.sort_values("Total", ascending=False)
    pivot_monthly_v.index.name = "Vendor"
    st.dataframe(pivot_monthly_v, use_container_width=True)

    st.subheader("Monthly Quantity Breakdown")

    pivot_qty_v = month_vendor.pivot_table(
        index="VENDOR_NAME", columns="MONTH_NUM", values="TOTAL_QTY", fill_value=0
    )
    pivot_qty_v = pivot_qty_v.sort_index(axis=1)
    pivot_qty_v.columns = [month_names[m] for m in pivot_qty_v.columns]
    pivot_qty_v["Total"] = pivot_qty_v.sum(axis=1)
    pivot_qty_v = pivot_qty_v.sort_values("Total", ascending=False)
    pivot_qty_v.index.name = "Vendor"
    st.dataframe(pivot_qty_v, use_container_width=True)

    st.subheader("Customer Group × Vendor")

    cust_vendor = (
        filtered.groupby(["CUSTOMER_GROUP", "VENDOR_NAME"])
        .agg(
            TOTAL_EURO=("NET_PRICE_EURO", "sum"),
            LINE_COUNT=("PO_QTY", "count"),
        )
        .reset_index()
        .sort_values("TOTAL_EURO", ascending=False)
    )

    with st.container(border=True):
        st.markdown("**€ Spend by Customer Group and Vendor**")
        pivot_cust_v = cust_vendor.pivot_table(
            index="CUSTOMER_GROUP", columns="VENDOR_NAME", values="TOTAL_EURO", fill_value=0
        )
        pivot_cust_v["Total"] = pivot_cust_v.sum(axis=1)
        pivot_cust_v = pivot_cust_v.sort_values("Total", ascending=False)
        st.dataframe(pivot_cust_v, use_container_width=True)

    # Material Group × Vendor Quantity
    st.subheader("Material Group × Vendor — Quantity")

    available_months_v = sorted(filtered["PO_POSTING_MONTH"].dropna().unique().tolist())
    month_options_v = {month_names[int(m)]: int(m) for m in available_months_v if int(m) in month_names}
    selected_months_v = st.multiselect(
        "Filter by Month", options=list(month_options_v.keys()), default=list(month_options_v.keys()), key="vendor_qty_month_filter"
    )
    qty_filtered_v = filtered[filtered["PO_POSTING_MONTH"].isin([month_options_v[m] for m in selected_months_v])]

    vendor_mat_qty = (
        qty_filtered_v.groupby(["VENDOR_NAME", "MATERIAL_GROUP"])
        .agg(TOTAL_QTY=("PO_QTY", "sum"))
        .reset_index()
    )

    with st.container(border=True):
        st.markdown("**Quantity by Vendor and Material Group**")
        pivot_vendor_mat = vendor_mat_qty.pivot_table(
            index="VENDOR_NAME", columns="MATERIAL_GROUP", values="TOTAL_QTY", fill_value=0
        )
        pivot_vendor_mat["Total"] = pivot_vendor_mat.sum(axis=1)
        pivot_vendor_mat = pivot_vendor_mat.sort_values("Total", ascending=False)
        st.dataframe(pivot_vendor_mat, use_container_width=True)

# =============================================================================
# TAB 3: Vehicle Level Analysis
# =============================================================================
with tab_vehicle:
    st.subheader("Vehicle Totals — Month to Month")

    month_vehicle = (
        filtered.groupby(["PO_POSTING_MONTH", "LICENCE_PLATE", "CUSTOMER_GROUP"])
        .agg(
            TOTAL_QTY=("PO_QTY", "sum"),
            TOTAL_EURO=("NET_PRICE_EURO", "sum"),
            LINE_COUNT=("PO_QTY", "count"),
        )
        .reset_index()
    )
    month_vehicle["MONTH_NAME"] = month_vehicle["PO_POSTING_MONTH"].map(month_names)
    month_vehicle["MONTH_NUM"] = month_vehicle["PO_POSTING_MONTH"]

    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.markdown("**€ Total per Customer Group by Month (Vehicle Level)**")
            pivot_euro_veh = month_vehicle.groupby(["MONTH_NUM", "MONTH_NAME", "CUSTOMER_GROUP"]).agg(
                TOTAL_EURO=("TOTAL_EURO", "sum")
            ).reset_index().pivot_table(
                index=["MONTH_NUM", "MONTH_NAME"], columns="CUSTOMER_GROUP", values="TOTAL_EURO", fill_value=0
            )
            pivot_euro_veh = pivot_euro_veh.sort_index(level="MONTH_NUM")
            pivot_euro_veh = pivot_euro_veh.droplevel("MONTH_NUM")
            st.bar_chart(pivot_euro_veh)

    with col2:
        with st.container(border=True):
            st.markdown("**Vehicle Count per Customer Group by Month**")
            veh_count = month_vehicle.groupby(["MONTH_NUM", "MONTH_NAME", "CUSTOMER_GROUP"]).agg(
                VEHICLE_COUNT=("LICENCE_PLATE", "nunique")
            ).reset_index().pivot_table(
                index=["MONTH_NUM", "MONTH_NAME"], columns="CUSTOMER_GROUP", values="VEHICLE_COUNT", fill_value=0
            )
            veh_count = veh_count.sort_index(level="MONTH_NUM")
            veh_count = veh_count.droplevel("MONTH_NUM")
            st.bar_chart(veh_count)

    st.subheader("Summary by Vehicle (Licence Plate)")

    vehicle_summary = (
        filtered.groupby(["LICENCE_PLATE", "CUSTOMER_GROUP"])
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
        st.metric("Unique Vehicles", filtered["LICENCE_PLATE"].nunique(), border=True)
        st.metric("Total € Spend", f"{vehicle_summary['TOTAL_EURO'].sum():,.2f}", border=True)
        st.metric("Total Qty", f"{vehicle_summary['TOTAL_QTY'].sum():,.0f}", border=True)

    st.dataframe(
        vehicle_summary.rename(columns={
            "LICENCE_PLATE": "Licence Plate",
            "CUSTOMER_GROUP": "Customer Group",
            "TOTAL_QTY": "Total Qty",
            "TOTAL_EURO": "Total € (Net Price)",
            "LINE_COUNT": "PO Lines",
            "UNIQUE_MATERIALS": "Unique Materials",
        }),
        hide_index=True,
        use_container_width=True,
    )

    st.subheader("Monthly € Breakdown by Customer Group")

    pivot_monthly_veh = (
        filtered.groupby(["CUSTOMER_GROUP", "PO_POSTING_MONTH"])
        .agg(TOTAL_EURO=("NET_PRICE_EURO", "sum"))
        .reset_index()
        .pivot_table(index="CUSTOMER_GROUP", columns="PO_POSTING_MONTH", values="TOTAL_EURO", fill_value=0)
    )
    pivot_monthly_veh = pivot_monthly_veh.sort_index(axis=1)
    pivot_monthly_veh.columns = [month_names[m] for m in pivot_monthly_veh.columns]
    pivot_monthly_veh["Total"] = pivot_monthly_veh.sum(axis=1)
    pivot_monthly_veh = pivot_monthly_veh.sort_values("Total", ascending=False)
    pivot_monthly_veh.index.name = "Customer Group"
    st.dataframe(pivot_monthly_veh, use_container_width=True)

    st.subheader("Monthly Quantity Breakdown by Customer Group")

    pivot_qty_veh = (
        filtered.groupby(["CUSTOMER_GROUP", "PO_POSTING_MONTH"])
        .agg(TOTAL_QTY=("PO_QTY", "sum"))
        .reset_index()
        .pivot_table(index="CUSTOMER_GROUP", columns="PO_POSTING_MONTH", values="TOTAL_QTY", fill_value=0)
    )
    pivot_qty_veh = pivot_qty_veh.sort_index(axis=1)
    pivot_qty_veh.columns = [month_names[m] for m in pivot_qty_veh.columns]
    pivot_qty_veh["Total"] = pivot_qty_veh.sum(axis=1)
    pivot_qty_veh = pivot_qty_veh.sort_values("Total", ascending=False)
    pivot_qty_veh.index.name = "Customer Group"
    st.dataframe(pivot_qty_veh, use_container_width=True)

    st.subheader("Customer Group × Material Group — Quantity (Vehicle Level)")

    available_months_veh = sorted(filtered["PO_POSTING_MONTH"].dropna().unique().tolist())
    month_options_veh = {month_names[int(m)]: int(m) for m in available_months_veh if int(m) in month_names}
    selected_months_veh = st.multiselect(
        "Filter by Month", options=list(month_options_veh.keys()), default=list(month_options_veh.keys()), key="vehicle_qty_month_filter"
    )
    qty_filtered_veh = filtered[filtered["PO_POSTING_MONTH"].isin([month_options_veh[m] for m in selected_months_veh])]

    veh_mat_qty = (
        qty_filtered_veh.groupby(["CUSTOMER_GROUP", "MATERIAL_GROUP"])
        .agg(
            TOTAL_QTY=("PO_QTY", "sum"),
            VEHICLE_COUNT=("LICENCE_PLATE", "nunique"),
        )
        .reset_index()
    )

    with st.container(border=True):
        st.markdown("**Quantity by Customer Group and Material Group**")
        pivot_veh_mat = veh_mat_qty.pivot_table(
            index="CUSTOMER_GROUP", columns="MATERIAL_GROUP", values="TOTAL_QTY", fill_value=0
        )
        pivot_veh_mat["Total"] = pivot_veh_mat.sum(axis=1)
        pivot_veh_mat = pivot_veh_mat.sort_values("Total", ascending=False)
        st.dataframe(pivot_veh_mat, use_container_width=True)

    with st.container(border=True):
        st.markdown("**Vehicle Count by Customer Group and Material Group**")
        pivot_veh_count = veh_mat_qty.pivot_table(
            index="CUSTOMER_GROUP", columns="MATERIAL_GROUP", values="VEHICLE_COUNT", fill_value=0
        )
        pivot_veh_count["Total"] = pivot_veh_count.sum(axis=1)
        pivot_veh_count = pivot_veh_count.sort_values("Total", ascending=False)
        st.dataframe(pivot_veh_count, use_container_width=True)
