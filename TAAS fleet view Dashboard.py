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

tab_material, tab_vendor, tab_vehicle, tab_ai = st.tabs(["General Fleet View", "Service Provider Level", "Vehicle Level", "AI Insights"])

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

# =============================================================================
# TAB 4: AI Insights — Cost Reduction & Service Provider Misbehaviour Detection
# =============================================================================
with tab_ai:
    st.subheader("AI Insights — Unnecessary Costs & Service Provider Anomalies")
    st.markdown(
        """Statistical analysis to identify **cost reduction opportunities** and
**service provider misbehaviour** (overcharging, unusual volumes, outlier pricing).

- **Vendor Price Outliers** — Flags vendors whose avg unit price per material group is >1.5 standard deviations and >20% above the group median. Shows potential savings if repriced at median.
- **Unusual Volume Spikes** — Detects vendor-month combinations where quantity exceeds 2× their own average (possible unnecessary services or billing anomalies).
- **High-Cost Vehicles** — Identifies vehicles above the 95th percentile spend within their customer group (potential over-servicing).
- **Vendor Concentration Risk** — Material groups where one vendor captures >70% of spend (dependency risk, limited competitive pricing)."""
    )

    # --- 1. Vendor Price Outliers per Material Group ---
    st.subheader("1. Vendor Price Outliers per Material Group")
    st.caption("Vendors whose average unit price deviates significantly from the group median.")

    vendor_pricing = (
        filtered.groupby(["VENDOR_NAME", "MATERIAL_GROUP"])
        .agg(
            AVG_UNIT_PRICE=("NET_PRICE_EURO", lambda x: x.sum() / max(filtered.loc[x.index, "PO_QTY"].sum(), 1)),
            TOTAL_EURO=("NET_PRICE_EURO", "sum"),
            TOTAL_QTY=("PO_QTY", "sum"),
            LINE_COUNT=("PO_QTY", "count"),
        )
        .reset_index()
    )

    # Compute group median and std
    group_stats = vendor_pricing.groupby("MATERIAL_GROUP")["AVG_UNIT_PRICE"].agg(["median", "std"]).reset_index()
    group_stats.columns = ["MATERIAL_GROUP", "GROUP_MEDIAN_PRICE", "GROUP_STD_PRICE"]
    vendor_pricing = vendor_pricing.merge(group_stats, on="MATERIAL_GROUP", how="left")
    vendor_pricing["GROUP_STD_PRICE"] = vendor_pricing["GROUP_STD_PRICE"].fillna(0)

    # Z-score
    vendor_pricing["Z_SCORE"] = np.where(
        vendor_pricing["GROUP_STD_PRICE"] > 0,
        (vendor_pricing["AVG_UNIT_PRICE"] - vendor_pricing["GROUP_MEDIAN_PRICE"]) / vendor_pricing["GROUP_STD_PRICE"],
        0,
    )
    vendor_pricing["PCT_ABOVE_MEDIAN"] = np.where(
        vendor_pricing["GROUP_MEDIAN_PRICE"] > 0,
        ((vendor_pricing["AVG_UNIT_PRICE"] - vendor_pricing["GROUP_MEDIAN_PRICE"]) / vendor_pricing["GROUP_MEDIAN_PRICE"]) * 100,
        0,
    )

    # Flag outliers (z > 1.5 and at least 20% above median)
    price_outliers = vendor_pricing[
        (vendor_pricing["Z_SCORE"] > 1.5) & (vendor_pricing["PCT_ABOVE_MEDIAN"] > 20)
    ].sort_values("TOTAL_EURO", ascending=False)

    if not price_outliers.empty:
        st.warning(f"⚠ {len(price_outliers)} vendor-material combinations with above-normal pricing detected.")
        st.dataframe(
            price_outliers[["VENDOR_NAME", "MATERIAL_GROUP", "AVG_UNIT_PRICE", "GROUP_MEDIAN_PRICE",
                            "PCT_ABOVE_MEDIAN", "TOTAL_EURO", "TOTAL_QTY"]].rename(columns={
                "VENDOR_NAME": "Vendor",
                "MATERIAL_GROUP": "Material Group",
                "AVG_UNIT_PRICE": "Avg Unit Price (€)",
                "GROUP_MEDIAN_PRICE": "Group Median (€)",
                "PCT_ABOVE_MEDIAN": "% Above Median",
                "TOTAL_EURO": "Total € Spend",
                "TOTAL_QTY": "Total Qty",
            }),
            hide_index=True,
            use_container_width=True,
        )
        potential_savings = (price_outliers["TOTAL_EURO"] - (price_outliers["GROUP_MEDIAN_PRICE"] * price_outliers["TOTAL_QTY"])).clip(lower=0).sum()
        st.metric("Potential Savings (if priced at median)", f"€{potential_savings:,.2f}", border=True)
    else:
        st.success("No significant pricing outliers detected.")

    # --- 2. Unusual Volume Spikes per Vendor ---
    st.subheader("2. Unusual Volume Spikes per Vendor")
    st.caption("Vendors with monthly quantity spikes >2x their own average.")

    vendor_monthly = (
        filtered.groupby(["VENDOR_NAME", "PO_POSTING_MONTH"])
        .agg(MONTHLY_QTY=("PO_QTY", "sum"), MONTHLY_EURO=("NET_PRICE_EURO", "sum"))
        .reset_index()
    )
    vendor_avg = vendor_monthly.groupby("VENDOR_NAME")["MONTHLY_QTY"].agg(["mean", "std"]).reset_index()
    vendor_avg.columns = ["VENDOR_NAME", "AVG_MONTHLY_QTY", "STD_MONTHLY_QTY"]
    vendor_monthly = vendor_monthly.merge(vendor_avg, on="VENDOR_NAME", how="left")
    vendor_monthly["SPIKE_RATIO"] = np.where(
        vendor_monthly["AVG_MONTHLY_QTY"] > 0,
        vendor_monthly["MONTHLY_QTY"] / vendor_monthly["AVG_MONTHLY_QTY"],
        0,
    )

    volume_spikes = vendor_monthly[vendor_monthly["SPIKE_RATIO"] > 2.0].sort_values("MONTHLY_EURO", ascending=False)

    if not volume_spikes.empty:
        volume_spikes["MONTH"] = volume_spikes["PO_POSTING_MONTH"].map(month_names)
        st.warning(f"⚠ {len(volume_spikes)} vendor-month combinations with volume spikes (>2x average).")
        st.dataframe(
            volume_spikes[["VENDOR_NAME", "MONTH", "MONTHLY_QTY", "AVG_MONTHLY_QTY", "SPIKE_RATIO", "MONTHLY_EURO"]].rename(columns={
                "VENDOR_NAME": "Vendor",
                "MONTH": "Month",
                "MONTHLY_QTY": "Month Qty",
                "AVG_MONTHLY_QTY": "Avg Monthly Qty",
                "SPIKE_RATIO": "Spike Ratio (×)",
                "MONTHLY_EURO": "Month € Spend",
            }),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.success("No unusual volume spikes detected.")

    # --- 3. High-Cost Vehicles (potential over-servicing) ---
    st.subheader("3. High-Cost Vehicles (Potential Over-Servicing)")
    st.caption("Vehicles whose total spend exceeds the 95th percentile for their customer group.")

    vehicle_costs = (
        filtered.groupby(["LICENCE_PLATE", "CUSTOMER_GROUP"])
        .agg(TOTAL_EURO=("NET_PRICE_EURO", "sum"), TOTAL_QTY=("PO_QTY", "sum"), PO_LINES=("PO_QTY", "count"))
        .reset_index()
    )
    p95 = vehicle_costs.groupby("CUSTOMER_GROUP")["TOTAL_EURO"].quantile(0.95).reset_index()
    p95.columns = ["CUSTOMER_GROUP", "P95_EURO"]
    vehicle_costs = vehicle_costs.merge(p95, on="CUSTOMER_GROUP", how="left")

    high_cost_vehicles = vehicle_costs[vehicle_costs["TOTAL_EURO"] > vehicle_costs["P95_EURO"]].sort_values("TOTAL_EURO", ascending=False)

    if not high_cost_vehicles.empty:
        st.warning(f"⚠ {len(high_cost_vehicles)} vehicles above 95th percentile spend for their customer group.")
        st.dataframe(
            high_cost_vehicles[["LICENCE_PLATE", "CUSTOMER_GROUP", "TOTAL_EURO", "P95_EURO", "TOTAL_QTY", "PO_LINES"]].rename(columns={
                "LICENCE_PLATE": "Licence Plate",
                "CUSTOMER_GROUP": "Customer Group",
                "TOTAL_EURO": "Total € Spend",
                "P95_EURO": "95th Percentile (€)",
                "TOTAL_QTY": "Total Qty",
                "PO_LINES": "PO Lines",
            }),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.success("No high-cost vehicle outliers detected.")

    # --- 4. Material Groups with Disproportionate Vendor Concentration ---
    st.subheader("4. Vendor Concentration Risk")
    st.caption("Material groups where a single vendor captures >70% of total spend — potential dependency or lack of competitive pricing.")

    vendor_share = (
        filtered.groupby(["MATERIAL_GROUP", "VENDOR_NAME"])
        .agg(VENDOR_EURO=("NET_PRICE_EURO", "sum"))
        .reset_index()
    )
    group_total = filtered.groupby("MATERIAL_GROUP")["NET_PRICE_EURO"].sum().reset_index()
    group_total.columns = ["MATERIAL_GROUP", "GROUP_TOTAL_EURO"]
    vendor_share = vendor_share.merge(group_total, on="MATERIAL_GROUP", how="left")
    vendor_share["SHARE_PCT"] = (vendor_share["VENDOR_EURO"] / vendor_share["GROUP_TOTAL_EURO"]) * 100

    concentrated = vendor_share[vendor_share["SHARE_PCT"] > 70].sort_values("VENDOR_EURO", ascending=False)

    if not concentrated.empty:
        st.warning(f"⚠ {len(concentrated)} vendor-material combinations with >70% spend concentration.")
        st.dataframe(
            concentrated[["MATERIAL_GROUP", "VENDOR_NAME", "VENDOR_EURO", "GROUP_TOTAL_EURO", "SHARE_PCT"]].rename(columns={
                "MATERIAL_GROUP": "Material Group",
                "VENDOR_NAME": "Vendor",
                "VENDOR_EURO": "Vendor € Spend",
                "GROUP_TOTAL_EURO": "Group Total €",
                "SHARE_PCT": "Vendor Share (%)",
            }),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.success("No excessive vendor concentration detected.")

    # --- 5. Summary Metrics ---
    st.subheader("5. Summary")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Price Outliers", len(price_outliers) if not price_outliers.empty else 0, border=True)
    with col2:
        st.metric("Volume Spikes", len(volume_spikes) if not volume_spikes.empty else 0, border=True)
    with col3:
        st.metric("High-Cost Vehicles", len(high_cost_vehicles) if not high_cost_vehicles.empty else 0, border=True)
    with col4:
        st.metric("Concentrated Vendors", len(concentrated) if not concentrated.empty else 0, border=True)
