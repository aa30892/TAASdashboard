# TAAS Fleet View Dashboard — Material group analysis month-to-month
# Co-authored with CoCo
import io
import os
import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Fleet View", layout="wide")
st.title("General Fleet View Dashboard")

MONTH_ORDER = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Get the directory where this script is running
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# The three independent fleet-type exports this app understands (matches the
# FLEET_TYPE_GROUP filter in export_taas_data.sql: TAAS / PPK / PAYGO).
FLEET_TYPE_CATEGORIES = ["TAAS", "PPK", "PAYGO"]

# Sidebar for data loading configuration
with st.sidebar:
    st.header("Data Source Configuration")
    data_source = st.radio(
        "Select Data Source",
        [
            "Upload Single File",
            "Upload by Fleet Category (3 files)",
            "Use Server File (Local)",
            "Use Server Files by Category (Local)",
        ],
        index=0,
        key="data_source_selection"
    )

    uploaded_file = None
    local_file_path = None
    fleet_files = {}
    local_fleet_paths = {}

    if data_source == "Upload Single File":
        uploaded_file = st.file_uploader("Upload PO data (CSV or Parquet)", type=["csv", "parquet"])
    elif data_source == "Upload by Fleet Category (3 files)":
        st.markdown(
            "Upload one file per fleet category (TAAS / PPK / PAYGO). Each is tagged with its "
            "category automatically if the file doesn't already carry one. You don't need all "
            "three — any combination of one, two, or three files works."
        )
        for category in FLEET_TYPE_CATEGORIES:
            fleet_files[category] = st.file_uploader(
                f"{category} file (CSV or Parquet)", type=["csv", "parquet"], key=f"upload_{category.lower()}"
            )
    elif data_source == "Use Server File (Local)":
        # Scan for CSV files in the script's folder
        available_files = [f for f in os.listdir(SCRIPT_DIR) if f.endswith(".csv")]
        if available_files:
            selected_filename = st.selectbox("Select a file from server", sorted(available_files))
            local_file_path = os.path.join(SCRIPT_DIR, selected_filename)
        else:
            st.error("No `.csv` files found in the script directory on the server.")
    else:  # "Use Server Files by Category (Local)"
        st.markdown(
            "Pick one server-side file per fleet category (TAAS / PPK / PAYGO). Files whose "
            "name contains the category are pre-selected automatically when possible."
        )
        available_files = sorted(
            f for f in os.listdir(SCRIPT_DIR) if f.lower().endswith((".csv", ".parquet"))
        )
        if not available_files:
            st.error("No `.csv` or `.parquet` files found in the script directory on the server.")
        else:
            options = ["(none)"] + available_files
            for category in FLEET_TYPE_CATEGORIES:
                auto_match = next((f for f in available_files if category.lower() in f.lower()), None)
                default_idx = options.index(auto_match) if auto_match in options else 0
                choice = st.selectbox(
                    f"{category} file", options, index=default_idx, key=f"local_cat_{category.lower()}"
                )
                local_fleet_paths[category] = None if choice == "(none)" else os.path.join(SCRIPT_DIR, choice)

# Halting mechanism if no data source is prepared
if data_source == "Upload Single File" and uploaded_file is None:
    st.info("Please upload PO data file (CSV or Parquet) to proceed. Use the export query in `export_taas_data.sql` to generate the file.")
    st.stop()
elif data_source == "Upload by Fleet Category (3 files)":
    uploaded_cats = {k: v for k, v in fleet_files.items() if v is not None}
    if len(uploaded_cats) == 0:
        st.info("Please upload at least one of the TAAS, PPK, or PAYGO files to proceed.")
        st.stop()
elif data_source == "Use Server File (Local)" and local_file_path is None:
    st.warning("Please make sure a compatible CSV file is uploaded to the server directory.")
    st.stop()
elif data_source == "Use Server Files by Category (Local)":
    selected_local_cats = {k: v for k, v in local_fleet_paths.items() if v is not None}
    if len(selected_local_cats) == 0:
        st.info("Please select at least one of the TAAS, PPK, or PAYGO files to proceed.")
        st.stop()

# --- Memory-optimization helpers -------------------------------------------
# Raw SQL-export columns the app never reads anywhere (verified by grep across
# the whole file) — dropped as early as possible so they never take up memory,
# and so st.cache_data's per-access deep copy has less to copy.
UNUSED_RAW_COLUMNS = [
    "CUSTOMER_NAME", "FOS_CONTRACT_ID", "MATERIAL_ID", "MATERIAL_GROUP_DESC",
    "VEHICLE_ID", "JOB_NOTIFICATION_ID", "JOB_TYPE_CODE",
]

# Low/medium-cardinality text columns worth storing as pandas `category` dtype
# (each distinct value stored once + a small integer code per row, instead of
# a duplicated Python string per row). Safe to combine with groupby() because
# every .groupby(...) call in this app now passes observed=True, so filtering
# never cross-joins in unused categories.
CATEGORY_DTYPE_COLUMNS = [
    "CUSTOMER_GROUP", "MATERIAL_GROUP", "MATERIAL_DESC", "FLEET_CATEGORY",
    "FLEET_TYPE_GROUP", "FLEET_TYPE", "VENDOR_NAME", "LICENCE_PLATE",
]

def _prepare_dataframe(df_in):
    """One-time cleanup + memory optimization for a freshly loaded/combined
    DataFrame. Called ONLY from inside the @st.cache_data-decorated loaders
    below, so this work runs once per unique cached input instead of on every
    rerun of the script."""
    df_in = df_in.copy()
    df_in.columns = df_in.columns.str.upper().str.strip()

    cols_to_drop = [c for c in UNUSED_RAW_COLUMNS if c in df_in.columns]
    if cols_to_drop:
        df_in = df_in.drop(columns=cols_to_drop)

    # Derive month from the full date, then drop the (bulkier) date column —
    # nothing downstream in the app uses PO_POSTING_DATE once the month exists.
    if "PO_POSTING_DATE" in df_in.columns:
        df_in["PO_POSTING_DATE"] = pd.to_datetime(df_in["PO_POSTING_DATE"], errors="coerce")
        if "PO_POSTING_MONTH" not in df_in.columns:
            df_in["PO_POSTING_MONTH"] = df_in["PO_POSTING_DATE"].dt.month
        df_in = df_in.drop(columns=["PO_POSTING_DATE"])

    # Default-fill classification columns that aren't part of REQUIRED_COLUMNS
    # (MATERIAL_GROUP is intentionally left alone here — it's required, and
    # should still trigger the missing-column error below if truly absent).
    if "CUSTOMER_GROUP" not in df_in.columns:
        df_in["CUSTOMER_GROUP"] = "Other"
    if "FLEET_CATEGORY" not in df_in.columns:
        df_in["FLEET_CATEGORY"] = "Other"
    if "FLEET_TYPE_GROUP" not in df_in.columns:
        df_in["FLEET_TYPE_GROUP"] = "Other"

    # Numeric downcasting — smaller dtypes where the value range allows it.
    if "PO_QTY" in df_in.columns:
        df_in["PO_QTY"] = pd.to_numeric(df_in["PO_QTY"], downcast="integer")
    if "NET_PRICE_EURO" in df_in.columns:
        df_in["NET_PRICE_EURO"] = pd.to_numeric(df_in["NET_PRICE_EURO"], downcast="float")
    if "PO_POSTING_MONTH" in df_in.columns:
        df_in["PO_POSTING_MONTH"] = pd.to_numeric(df_in["PO_POSTING_MONTH"], downcast="integer")

    for col in CATEGORY_DTYPE_COLUMNS:
        if col in df_in.columns:
            df_in[col] = df_in[col].astype("category")

    return df_in

# Load Data based on selection
@st.cache_data
def load_data(source_type, upload_obj=None, path_str=None):
    if source_type == "Upload Single File" and upload_obj is not None:
        buf = io.BytesIO(upload_obj.getvalue())
        if upload_obj.name.endswith(".parquet"):
            df_loaded = pd.read_parquet(buf)
        else:
            df_loaded = pd.read_csv(buf)
    elif source_type == "Use Server File (Local)" and path_str is not None:
        df_loaded = pd.read_csv(path_str)
    else:
        return pd.DataFrame()
    return _prepare_dataframe(df_loaded)

def _read_any_source(source):
    """Read a CSV/Parquet source into a DataFrame, whether it's an uploaded
    file object (has getvalue()/name) or a local file path string."""
    if hasattr(source, "getvalue"):
        name = source.name
        buf = io.BytesIO(source.getvalue())
        if name.lower().endswith(".parquet"):
            return pd.read_parquet(buf)
        return pd.read_csv(buf)
    path_str = str(source)
    if path_str.lower().endswith(".parquet"):
        return pd.read_parquet(path_str)
    return pd.read_csv(path_str)

@st.cache_data
def load_fleet_category_sources(source_dict):
    """source_dict: {category_name: uploaded_file_or_local_path_or_None}.
    Returns (combined_df, list_of_categories_actually_loaded)."""
    frames = []
    loaded_categories = []
    for category, source in source_dict.items():
        if source is None:
            continue
        part = _read_any_source(source)
        part.columns = part.columns.str.upper().str.strip()
        if "FLEET_CATEGORY" not in part.columns:
            part["FLEET_CATEGORY"] = category
        if "FLEET_TYPE_GROUP" not in part.columns:
            part["FLEET_TYPE_GROUP"] = category
        frames.append(part)
        loaded_categories.append(category)
    if not frames:
        return pd.DataFrame(), loaded_categories
    combined = pd.concat(frames, ignore_index=True, sort=False)
    return _prepare_dataframe(combined), loaded_categories

loaded_categories = None  # only meaningful for the two by-category data sources
if data_source == "Upload by Fleet Category (3 files)":
    df, loaded_categories = load_fleet_category_sources({k: v for k, v in fleet_files.items() if v is not None})
elif data_source == "Use Server Files by Category (Local)":
    df, loaded_categories = load_fleet_category_sources({k: v for k, v in local_fleet_paths.items() if v is not None})
else:
    df = load_data(data_source, upload_obj=uploaded_file, path_str=local_file_path)

if df.empty:
    st.warning("No data returned. Check filters or file content.")
    st.stop()

# Let the user see, at a glance, which of the three fleet-type files are loaded.
if loaded_categories is not None:
    missing_categories = [c for c in FLEET_TYPE_CATEGORIES if c not in loaded_categories]
    status_msg = f"Loaded: {', '.join(loaded_categories)}"
    if missing_categories:
        status_msg += f"  •  Not loaded: {', '.join(missing_categories)}"
    st.sidebar.success(status_msg)

# Validate required columns exist
REQUIRED_COLUMNS = {"PO_QTY", "NET_PRICE_EURO", "PO_POSTING_MONTH", "MATERIAL_GROUP"}
missing = REQUIRED_COLUMNS - set(df.columns)
if missing:
    st.error(
        f"Missing required column(s): **{', '.join(sorted(missing))}**. "
        f"Available columns: {', '.join(sorted(df.columns))}. "
        "Please ensure the data was exported using `export_taas_data.sql`."
    )
    st.stop()

# MATERIAL_GROUP is required above; still default-fill it here in case a
# caller ever adds it to the non-required list, matching the pre-existing
# behavior of the other classification columns.
if "MATERIAL_GROUP" not in df.columns:
    df["MATERIAL_GROUP"] = "Other"
elif df["MATERIAL_GROUP"].dtype.name != "category":
    df["MATERIAL_GROUP"] = df["MATERIAL_GROUP"].astype("category")

# Sidebar filters
with st.sidebar:
    st.header("Filters")
    customer_groups = sorted([x for x in df["CUSTOMER_GROUP"].unique() if isinstance(x, str) and x != "Other"])
    if "Other" in df["CUSTOMER_GROUP"].unique():
        customer_groups.append("Other")
    selected_customers = st.multiselect("Customer Group", customer_groups, key="cust_filter")

    material_groups = sorted(df["MATERIAL_GROUP"].dropna().unique().tolist())
    selected_groups = st.multiselect("Material Group", material_groups, key="group_filter")

    if "FLEET_CATEGORY" in df.columns:
        fleet_categories = sorted([x for x in df["FLEET_CATEGORY"].unique() if isinstance(x, str) and x != "Other"])
        if "Other" in df["FLEET_CATEGORY"].unique():
            fleet_categories.append("Other")
        selected_fleet_cats = st.multiselect("Fleet Category", fleet_categories, key="fleet_cat_filter")
    else:
        selected_fleet_cats = []

    if "FLEET_TYPE" in df.columns:
        fleet_types = sorted([x for x in df["FLEET_TYPE"].unique() if isinstance(x, str) and x != "Other"])
        if "Other" in df["FLEET_TYPE"].unique():
            fleet_types.append("Other")
        selected_fleet_types = st.multiselect("Fleet Type", fleet_types, key="fleet_type_filter")
    else:
        selected_fleet_types = []

    if "FLEET_TYPE_GROUP" in df.columns:
        fleet_type_groups = sorted([x for x in df["FLEET_TYPE_GROUP"].unique() if isinstance(x, str) and x != "Other"])
        if "Other" in df["FLEET_TYPE_GROUP"].unique():
            fleet_type_groups.append("Other")
        selected_fleet_type_groups = st.multiselect(
            "Fleet Type Group (TAAS / PPK / PAYGO)", fleet_type_groups, key="fleet_type_group_filter"
        )
    else:
        selected_fleet_type_groups = []

# Apply filters
filtered = df  # boolean-mask filtering below always returns a new object, never a view
if selected_customers:
    filtered = filtered[filtered["CUSTOMER_GROUP"].isin(selected_customers)]
if selected_groups:
    filtered = filtered[filtered["MATERIAL_GROUP"].isin(selected_groups)]
if selected_fleet_cats:
    filtered = filtered[filtered["FLEET_CATEGORY"].isin(selected_fleet_cats)]
if selected_fleet_types:
    filtered = filtered[filtered["FLEET_TYPE"].isin(selected_fleet_types)]
if selected_fleet_type_groups:
    filtered = filtered[filtered["FLEET_TYPE_GROUP"].isin(selected_fleet_type_groups)]

st.metric("Total Records", f"{len(filtered):,}", border=True)

month_names = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
               7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}

PAGES = ["General Fleet View", "Service Provider Level", "Vehicle Level", "Fleet Benchmark", "AI Insights"]
# A page selector (instead of st.tabs) means only the SELECTED page's code
# below actually runs on each rerun — st.tabs executes every tab's body on
# every rerun regardless of which one is visible, which was the single
# biggest memory/CPU cost in this app for larger datasets.
page = st.radio("Navigate to", PAGES, horizontal=True, key="page_selector", label_visibility="collapsed")

# =============================================================================
# TAB 1: Material Group Analysis
# =============================================================================
if page == "General Fleet View":
    st.subheader("Material Group Totals — Month to Month")

    month_group = (
        filtered.groupby(["PO_POSTING_MONTH", "MATERIAL_GROUP"], observed=True)
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
        filtered.groupby("MATERIAL_GROUP", observed=True)
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
        filtered.groupby(["CUSTOMER_GROUP", "MATERIAL_GROUP"], observed=True)
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
if page == "Service Provider Level":
    st.subheader("Vendor Totals — Month to Month")

    # Vendor-level filters
    all_vendors = sorted(filtered["VENDOR_NAME"].dropna().unique().tolist()) if "VENDOR_NAME" in filtered.columns else []
    DEFAULT_EXCLUDE = ["EBTS France", "AXA assitance france", "Service24"]
    existing_exclude = [v for v in DEFAULT_EXCLUDE if v in all_vendors]

    vcol1, vcol2 = st.columns(2)
    with vcol1:
        selected_vendors = st.multiselect("Filter by Vendor", all_vendors, key="vendor_tab_filter")
    with vcol2:
        excluded_vendors = st.multiselect(
            "Exclude Vendors from Analysis",
            all_vendors,
            default=existing_exclude,
            key="vendor_tab_exclude",
        )

    vendor_filtered = filtered  # boolean-mask filtering below always returns a new object
    if selected_vendors:
        vendor_filtered = vendor_filtered[vendor_filtered["VENDOR_NAME"].isin(selected_vendors)]
    if excluded_vendors:
        vendor_filtered = vendor_filtered[~vendor_filtered["VENDOR_NAME"].isin(excluded_vendors)]

    month_vendor = (
        vendor_filtered.groupby(["PO_POSTING_MONTH", "VENDOR_NAME"], observed=True)
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
        vendor_filtered.groupby("VENDOR_NAME", observed=True)
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
        vendor_filtered.groupby(["CUSTOMER_GROUP", "VENDOR_NAME"], observed=True)
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

    available_months_v = sorted(vendor_filtered["PO_POSTING_MONTH"].dropna().unique().tolist())
    month_options_v = {month_names[int(m)]: int(m) for m in available_months_v if int(m) in month_names}
    selected_months_v = st.multiselect(
        "Filter by Month", options=list(month_options_v.keys()), default=list(month_options_v.keys()), key="vendor_qty_month_filter"
    )
    qty_filtered_v = vendor_filtered[vendor_filtered["PO_POSTING_MONTH"].isin([month_options_v[m] for m in selected_months_v])]

    vendor_mat_qty = (
        qty_filtered_v.groupby(["VENDOR_NAME", "MATERIAL_GROUP"], observed=True)
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
if page == "Vehicle Level":
    st.subheader("Vehicle Totals — Month to Month")

    month_vehicle = (
        filtered.groupby(["PO_POSTING_MONTH", "LICENCE_PLATE", "CUSTOMER_GROUP"], observed=True)
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
            pivot_euro_veh = month_vehicle.groupby(["MONTH_NUM", "MONTH_NAME", "CUSTOMER_GROUP"], observed=True).agg(
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
            veh_count = month_vehicle.groupby(["MONTH_NUM", "MONTH_NAME", "CUSTOMER_GROUP"], observed=True).agg(
                VEHICLE_COUNT=("LICENCE_PLATE", "nunique")
            ).reset_index().pivot_table(
                index=["MONTH_NUM", "MONTH_NAME"], columns="CUSTOMER_GROUP", values="VEHICLE_COUNT", fill_value=0
            )
            veh_count = veh_count.sort_index(level="MONTH_NUM")
            veh_count = veh_count.droplevel("MONTH_NUM")
            st.bar_chart(veh_count)

    st.subheader("Summary by Vehicle (Licence Plate)")

    vehicle_summary = (
        filtered.groupby(["LICENCE_PLATE", "CUSTOMER_GROUP"], observed=True)
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
        filtered.groupby(["CUSTOMER_GROUP", "PO_POSTING_MONTH"], observed=True)
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
        filtered.groupby(["CUSTOMER_GROUP", "PO_POSTING_MONTH"], observed=True)
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
        qty_filtered_veh.groupby(["CUSTOMER_GROUP", "MATERIAL_GROUP"], observed=True)
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
# TAB 4: Fleet Benchmark — TAAS vs Best/Worst PPK vs Best/Worst PAYGO
# =============================================================================
if page == "Fleet Benchmark":
    st.subheader("Fleet Benchmark — TAAS vs PPK vs PAYGO")
    st.markdown(
        """This tab benchmarks **TAAS fleets** (Transalliance, Chatel, Taldea, Garnier, Eychenne, ID Logistics, Veolia)
against four comparison groups drawn from Pay-Per-Kilometre (PPK) and Pay-As-You-Go (PAYGO) contracts:

| Category | What it contains | Why it matters |
|---|---|---|
| **TAAS** | Our core mileage-based fleets | The baseline — all comparisons are relative to this group |
| **Best PPK** | Amazon, Iceland Foods, Ludwig Meyer, DHL, DPD, Booker, Suez, Tesco, WM Morrison | Top-performing PPK fleets — target benchmark for cost efficiency |
| **Worst PPK** | GCA, Stef, XPO, Culina, Transdev, Geodis, Medtruck, Fertrans, SBG | Underperforming PPK fleets — shows the cost gap to avoid |
| **Best PAYGO** | Amazon PAYGO, ECM, Contract Vehicles, Bertschi, ECS Corporate, Abbey Logistics, Raben, Duvenbeck, Hoyer, BPA Lactalis | Top-performing PAYGO fleets |
| **Worst PAYGO** | TIP, PNO, Coquelle, Marcotran, Voyage Emile Weber, Schenker, Blondel, Ttes. Agustin Fuentes, Delgo, Trans Italia | Underperforming PAYGO fleets |

**How to read the sections below:**
1. **KPIs** — headline metrics per category; compare Avg € / Unit and Avg € / Vehicle across columns
2. **Avg € per Unit by Material Group** — where TAAS is cheaper or more expensive than each group, broken down by service type
3. **Total € Spend** — absolute spend volume per material group; shows where the money goes
4. **Volume Mix** — percentage split of quantity; reveals different service usage patterns between fleet types
5. **Monthly Trends** — spot seasonal patterns or divergence over time
6. **Avg € per Vehicle by Month** — normalised efficiency trend (removes fleet-size bias)
7. **Conclusion — TAAS vs PPK vs PAYGO (Global)** — Best + Worst PPK rolled into one PPK benchmark, Best + Worst PAYGO rolled into one PAYGO benchmark: the direct answer to "are TAAS material costs higher, lower, or normal?"
"""
    )

    if "FLEET_CATEGORY" not in filtered.columns:
        st.warning(
            "**FLEET_CATEGORY** column not found in the data. "
            "Re-export using the latest `export_taas_data.sql` which includes this column."
        )
    else:
        # Preferred display order for the granular categories the SQL export produces,
        # plus the broad TAAS/PPK/PAYGO labels used as a fallback when a file was loaded
        # via "Upload/Use Server Files by Category" without its own FLEET_CATEGORY column.
        # This list is only used for ORDERING — the tab works fine with any subset of it
        # (one, two, or all categories present), so loading e.g. only TAAS + PPK is fine.
        PREFERRED_CATEGORY_ORDER = [
            "TAAS", "Best PPK", "Worst PPK", "PPK", "Best PAYGO", "Worst PAYGO", "PAYGO"
        ]
        cats_in_data = [x for x in filtered["FLEET_CATEGORY"].dropna().unique() if x != "Other"]
        CATEGORIES = [c for c in PREFERRED_CATEGORY_ORDER if c in cats_in_data]
        # Keep any other non-standard category labels too, appended at the end, so a
        # differently-tagged file still shows up instead of being silently dropped.
        CATEGORIES += sorted(c for c in cats_in_data if c not in PREFERRED_CATEGORY_ORDER)

        bench_df = filtered[filtered["FLEET_CATEGORY"].isin(CATEGORIES)]  # boolean-mask indexing already returns a new object

        if bench_df.empty:
            st.warning("No data for the recognized fleet categories (TAAS / PPK / PAYGO) in the current filters.")
        else:
            present_cats = [c for c in CATEGORIES if c in bench_df["FLEET_CATEGORY"].unique()]

            # --- 1. High-Level KPI Comparison ---
            st.subheader("1. High-Level KPIs by Fleet Category")
            kpi = (
                bench_df.groupby("FLEET_CATEGORY", observed=True)
                .agg(
                    TOTAL_EURO=("NET_PRICE_EURO", "sum"),
                    TOTAL_QTY=("PO_QTY", "sum"),
                    LINE_COUNT=("PO_QTY", "count"),
                    UNIQUE_VEHICLES=("LICENCE_PLATE", "nunique"),
                    UNIQUE_CUSTOMERS=("CUSTOMER_GROUP", "nunique"),
                )
                .reindex(present_cats)
                .reset_index()
            )
            kpi["AVG_EURO_PER_UNIT"] = kpi["TOTAL_EURO"] / kpi["TOTAL_QTY"].replace(0, 1)
            kpi["AVG_EURO_PER_VEHICLE"] = kpi["TOTAL_EURO"] / kpi["UNIQUE_VEHICLES"].replace(0, 1)
            kpi["AVG_LINES_PER_VEHICLE"] = kpi["LINE_COUNT"] / kpi["UNIQUE_VEHICLES"].replace(0, 1)

            cols = st.columns(len(present_cats))
            for idx, row in kpi.iterrows():
                with cols[idx]:
                    st.markdown(f"**{row['FLEET_CATEGORY']}**")
                    st.metric("Total € Spend", f"€{row['TOTAL_EURO']:,.0f}", border=True)
                    st.metric("Total Qty", f"{row['TOTAL_QTY']:,.0f}", border=True)
                    st.metric("Vehicles", f"{row['UNIQUE_VEHICLES']:,}", border=True)
                    st.metric("Avg € / Unit", f"€{row['AVG_EURO_PER_UNIT']:,.2f}", border=True)
                    st.metric("Avg € / Vehicle", f"€{row['AVG_EURO_PER_VEHICLE']:,.0f}", border=True)
                    st.metric("Lines / Vehicle", f"{row['AVG_LINES_PER_VEHICLE']:,.1f}", border=True)

            # --- 2. Cost per Unit by Material Group ---
            st.subheader("2. Avg € per Unit by Material Group")
            st.caption("Side-by-side average unit cost (NET_PRICE_EURO / PO_QTY) for each fleet category.")

            mat_bench = (
                bench_df.groupby(["FLEET_CATEGORY", "MATERIAL_GROUP"], observed=True)
                .agg(TOTAL_EURO=("NET_PRICE_EURO", "sum"), TOTAL_QTY=("PO_QTY", "sum"))
                .reset_index()
            )
            mat_bench["AVG_UNIT_PRICE"] = mat_bench["TOTAL_EURO"] / mat_bench["TOTAL_QTY"].replace(0, 1)

            pivot_cpu = mat_bench.pivot_table(
                index="MATERIAL_GROUP", columns="FLEET_CATEGORY", values="AVG_UNIT_PRICE", fill_value=0
            )
            pivot_cpu = pivot_cpu.reindex(columns=[c for c in present_cats if c in pivot_cpu.columns])
            pivot_cpu.index.name = "Material Group"
            st.dataframe(pivot_cpu.style.format("€{:,.2f}"), use_container_width=True)

            with st.container(border=True):
                st.markdown("**Avg € / Unit by Material Group (Chart)**")
                st.bar_chart(pivot_cpu)

            # --- 3. Total € Spend by Material Group ---
            st.subheader("3. Total € Spend by Material Group")
            pivot_spend = mat_bench.pivot_table(
                index="MATERIAL_GROUP", columns="FLEET_CATEGORY", values="TOTAL_EURO", fill_value=0
            )
            pivot_spend = pivot_spend.reindex(columns=[c for c in present_cats if c in pivot_spend.columns])
            pivot_spend["Total"] = pivot_spend.sum(axis=1)
            pivot_spend = pivot_spend.sort_values("Total", ascending=False)
            pivot_spend.index.name = "Material Group"
            st.dataframe(pivot_spend.style.format("€{:,.0f}"), use_container_width=True)

            # --- 4. Volume Mix (% of Qty) ---
            st.subheader("4. Volume Mix — % of Quantity by Material Group")
            st.caption("Each column sums to 100% — shows how each fleet category allocates its volume across material groups.")

            vol_mix = (
                bench_df.groupby(["FLEET_CATEGORY", "MATERIAL_GROUP"], observed=True)
                .agg(TOTAL_QTY=("PO_QTY", "sum"))
                .reset_index()
            )
            vol_totals = vol_mix.groupby("FLEET_CATEGORY", observed=True)["TOTAL_QTY"].transform("sum")
            vol_mix["QTY_SHARE_PCT"] = (vol_mix["TOTAL_QTY"] / vol_totals.replace(0, 1)) * 100

            pivot_vol = vol_mix.pivot_table(
                index="MATERIAL_GROUP", columns="FLEET_CATEGORY", values="QTY_SHARE_PCT", fill_value=0
            )
            pivot_vol = pivot_vol.reindex(columns=[c for c in present_cats if c in pivot_vol.columns])
            pivot_vol.index.name = "Material Group"
            st.dataframe(pivot_vol.style.format("{:.1f}%"), use_container_width=True)

            # --- 5. Monthly Spend Trend ---
            st.subheader("5. Monthly € Spend Trend")
            monthly = (
                bench_df.groupby(["FLEET_CATEGORY", "PO_POSTING_MONTH"], observed=True)
                .agg(TOTAL_EURO=("NET_PRICE_EURO", "sum"))
                .reset_index()
            )
            monthly["MONTH_NAME"] = monthly["PO_POSTING_MONTH"].map(month_names)
            pivot_monthly = monthly.pivot_table(
                index=["PO_POSTING_MONTH", "MONTH_NAME"], columns="FLEET_CATEGORY", values="TOTAL_EURO", fill_value=0
            )
            pivot_monthly = pivot_monthly.reindex(columns=[c for c in present_cats if c in pivot_monthly.columns])
            pivot_monthly = pivot_monthly.sort_index(level="PO_POSTING_MONTH")
            pivot_monthly = pivot_monthly.droplevel("PO_POSTING_MONTH")
            with st.container(border=True):
                st.markdown("**€ Spend by Month**")
                st.bar_chart(pivot_monthly)

            # --- 6. Avg € per Vehicle by Month ---
            st.subheader("6. Avg € per Vehicle by Month")
            monthly_veh = (
                bench_df.groupby(["FLEET_CATEGORY", "PO_POSTING_MONTH"], observed=True)
                .agg(TOTAL_EURO=("NET_PRICE_EURO", "sum"), UNIQUE_VEHICLES=("LICENCE_PLATE", "nunique"))
                .reset_index()
            )
            monthly_veh["AVG_EURO_PER_VEH"] = monthly_veh["TOTAL_EURO"] / monthly_veh["UNIQUE_VEHICLES"].replace(0, 1)
            monthly_veh["MONTH_NAME"] = monthly_veh["PO_POSTING_MONTH"].map(month_names)
            pivot_avg_veh = monthly_veh.pivot_table(
                index=["PO_POSTING_MONTH", "MONTH_NAME"], columns="FLEET_CATEGORY", values="AVG_EURO_PER_VEH", fill_value=0
            )
            pivot_avg_veh = pivot_avg_veh.reindex(columns=[c for c in present_cats if c in pivot_avg_veh.columns])
            pivot_avg_veh = pivot_avg_veh.sort_index(level="PO_POSTING_MONTH")
            pivot_avg_veh = pivot_avg_veh.droplevel("PO_POSTING_MONTH")
            with st.container(border=True):
                st.markdown("**Avg € per Vehicle by Month**")
                st.bar_chart(pivot_avg_veh)

            # --- 7. Conclusion — TAAS vs PPK vs PAYGO (Global) ---
            st.divider()
            st.subheader("7. Conclusion — TAAS vs PPK vs PAYGO (Global)")
            st.markdown(
                "Rolls **Best + Worst PPK** into one PPK benchmark and **Best + Worst PAYGO** into "
                "one PAYGO benchmark, then answers the core question directly: overall, are **TAAS** "
                "material costs **higher, lower, or normal** compared to PPK and PAYGO fleets?"
            )

            NORMAL_BAND_PCT = 5.0  # within +/- this % of the benchmark counts as "Normal / comparable"

            def _broad_fleet_group(cat):
                if cat == "TAAS":
                    return "TAAS"
                if "PPK" in cat:
                    return "PPK"
                if "PAYGO" in cat:
                    return "PAYGO"
                return None

            conclusion_df = bench_df.copy()
            conclusion_df["BROAD_GROUP"] = conclusion_df["FLEET_CATEGORY"].apply(_broad_fleet_group)
            conclusion_df = conclusion_df[conclusion_df["BROAD_GROUP"].notna()]

            if "TAAS" not in conclusion_df["BROAD_GROUP"].unique():
                st.info("TAAS data not available for the global conclusion.")
            else:
                broad_totals = (
                    conclusion_df.groupby("BROAD_GROUP", observed=True)
                    .agg(
                        TOTAL_EURO=("NET_PRICE_EURO", "sum"),
                        UNIQUE_VEHICLES=("LICENCE_PLATE", "nunique"),
                    )
                )
                broad_totals["AVG_EURO_PER_VEHICLE"] = (
                    broad_totals["TOTAL_EURO"] / broad_totals["UNIQUE_VEHICLES"].replace(0, 1)
                )
                taas_avg_per_vehicle = broad_totals.loc["TAAS", "AVG_EURO_PER_VEHICLE"]
                taas_vehicles = broad_totals.loc["TAAS", "UNIQUE_VEHICLES"]

                other_broad_groups = [g for g in ["PPK", "PAYGO"] if g in broad_totals.index]

                if not other_broad_groups:
                    st.info("No PPK or PAYGO data available to compare against TAAS.")
                else:
                    def _verdict(pct):
                        if pct > NORMAL_BAND_PCT:
                            return "HIGHER", "error"
                        elif pct < -NORMAL_BAND_PCT:
                            return "LOWER", "success"
                        return "NORMAL", "info"

                    # --- Headline verdict ---
                    st.markdown("**Headline verdict**")
                    st.caption(
                        "Compares avg €/vehicle, normalised for fleet size — fleet size for each group "
                        "is shown for context, since a category with far more (or fewer) vehicles "
                        "changes what per-vehicle figures mean."
                    )
                    headline_verdicts = {}
                    headline_cols = st.columns(len(other_broad_groups))
                    for col, group in zip(headline_cols, other_broad_groups):
                        other_avg_veh = broad_totals.loc[group, "AVG_EURO_PER_VEHICLE"]
                        other_vehicles = broad_totals.loc[group, "UNIQUE_VEHICLES"]

                        pct_diff_veh = (
                            (taas_avg_per_vehicle - other_avg_veh) / other_avg_veh * 100
                        ) if other_avg_veh else 0.0

                        veh_verdict, veh_tone = _verdict(pct_diff_veh)
                        headline_verdicts[group] = (veh_verdict, pct_diff_veh)

                        with col:
                            st.markdown(f"**TAAS vs {group}**")
                            st.caption(
                                f"Fleet size — TAAS: {taas_vehicles:,.0f} vehicles · "
                                f"{group}: {other_vehicles:,.0f} vehicles"
                            )
                            if taas_vehicles and other_vehicles:
                                size_ratio = max(taas_vehicles, other_vehicles) / min(taas_vehicles, other_vehicles)
                                if size_ratio >= 5:
                                    larger = "TAAS" if taas_vehicles > other_vehicles else group
                                    st.caption(
                                        f"⚠ {larger} has {size_ratio:.0f}× more vehicles — per-vehicle "
                                        "figures reflect very different operating scales."
                                    )
                            st.metric(
                                "Avg € / Vehicle",
                                f"€{taas_avg_per_vehicle:,.0f}",
                                delta=f"{pct_diff_veh:+.1f}% vs {group} (€{other_avg_veh:,.0f})",
                                delta_color="inverse",
                                border=True,
                            )
                            getattr(st, veh_tone)(
                                f"Per-vehicle cost: TAAS is **{veh_verdict}** than {group} ({pct_diff_veh:+.1f}%)."
                            )

                    # --- Material-group level breakdown, per comparison ---
                    st.markdown("**Material Group Breakdown**")
                    st.caption(
                        "Per material group: TAAS's own avg €/unit vs each benchmark's avg €/unit, the % "
                        "difference, a Higher/Lower/Normal verdict (±{:.0f}% band), and the € impact at "
                        "TAAS's own volume (positive = TAAS spent more than it would have at the "
                        "benchmark's rate; negative = TAAS spent less).".format(NORMAL_BAND_PCT)
                    )

                    mg_totals = (
                        conclusion_df.groupby(["BROAD_GROUP", "MATERIAL_GROUP"], observed=True)
                        .agg(TOTAL_EURO=("NET_PRICE_EURO", "sum"), TOTAL_QTY=("PO_QTY", "sum"))
                        .reset_index()
                    )
                    mg_totals["AVG_UNIT_PRICE"] = mg_totals["TOTAL_EURO"] / mg_totals["TOTAL_QTY"].replace(0, 1)
                    taas_mg = mg_totals[mg_totals["BROAD_GROUP"] == "TAAS"].set_index("MATERIAL_GROUP")

                    verdict_rows = []
                    for group in other_broad_groups:
                        other_mg = mg_totals[mg_totals["BROAD_GROUP"] == group].set_index("MATERIAL_GROUP")
                        for mg in taas_mg.index.intersection(other_mg.index):
                            taas_price = taas_mg.loc[mg, "AVG_UNIT_PRICE"]
                            other_price = other_mg.loc[mg, "AVG_UNIT_PRICE"]
                            taas_qty = taas_mg.loc[mg, "TOTAL_QTY"]
                            pct = ((taas_price - other_price) / other_price * 100) if other_price else 0.0
                            if pct > NORMAL_BAND_PCT:
                                mg_verdict = "▲ Higher"
                            elif pct < -NORMAL_BAND_PCT:
                                mg_verdict = "▼ Lower"
                            else:
                                mg_verdict = "≈ Normal"
                            verdict_rows.append({
                                "Comparison": group,
                                "Material Group": mg,
                                "TAAS Avg €/Unit": taas_price,
                                "Benchmark Avg €/Unit": other_price,
                                "Diff (%)": pct,
                                "Verdict": mg_verdict,
                                "€ Impact (at TAAS Volume)": (taas_price - other_price) * taas_qty,
                            })

                    if not verdict_rows:
                        st.info("No overlapping material groups between TAAS and the PPK/PAYGO benchmarks.")
                    else:
                        verdict_df = pd.DataFrame(verdict_rows)

                        for group in other_broad_groups:
                            group_df = verdict_df[verdict_df["Comparison"] == group].sort_values(
                                "€ Impact (at TAAS Volume)", ascending=False
                            )
                            with st.container(border=True):
                                st.markdown(f"**TAAS vs {group} — by Material Group**")
                                counts = group_df["Verdict"].value_counts()
                                summary_cols = st.columns(4)
                                summary_cols[0].metric("Material Groups Compared", len(group_df), border=True)
                                summary_cols[1].metric("Higher (TAAS costs more)", int(counts.get("▲ Higher", 0)), border=True)
                                summary_cols[2].metric("Normal / Comparable", int(counts.get("≈ Normal", 0)), border=True)
                                summary_cols[3].metric("Lower (TAAS costs less)", int(counts.get("▼ Lower", 0)), border=True)

                                total_impact = group_df["€ Impact (at TAAS Volume)"].sum()
                                impact_msg = (
                                    f"Net € impact vs {group} at TAAS's own volume: "
                                    f"**€{total_impact:+,.0f}** "
                                    f"({'TAAS spends more overall' if total_impact > 0 else 'TAAS spends less overall' if total_impact < 0 else 'net neutral'})."
                                )
                                if taas_vehicles:
                                    impact_per_vehicle = total_impact / taas_vehicles
                                    impact_msg += (
                                        f" That's **€{impact_per_vehicle:+,.0f} per TAAS vehicle** "
                                        f"(across {taas_vehicles:,.0f} vehicles) if TAAS had been priced at {group} rates."
                                    )
                                st.markdown(impact_msg)

                                st.dataframe(
                                    group_df.drop(columns=["Comparison"]).style.format({
                                        "TAAS Avg €/Unit": "€{:,.2f}",
                                        "Benchmark Avg €/Unit": "€{:,.2f}",
                                        "Diff (%)": "{:+.1f}%",
                                        "€ Impact (at TAAS Volume)": "€{:+,.0f}",
                                    }),
                                    hide_index=True,
                                    use_container_width=True,
                                )

                                top_driver = group_df.iloc[0] if not group_df.empty else None
                                top_saver = group_df.iloc[-1] if not group_df.empty else None
                                if top_driver is not None and top_driver["€ Impact (at TAAS Volume)"] > 0:
                                    st.caption(
                                        f"Biggest cost driver vs {group}: **{top_driver['Material Group']}** "
                                        f"({top_driver['Diff (%)']:+.1f}%, €{top_driver['€ Impact (at TAAS Volume)']:+,.0f})."
                                    )
                                if top_saver is not None and top_saver["€ Impact (at TAAS Volume)"] < 0:
                                    st.caption(
                                        f"Biggest saving vs {group}: **{top_saver['Material Group']}** "
                                        f"({top_saver['Diff (%)']:+.1f}%, €{top_saver['€ Impact (at TAAS Volume)']:+,.0f})."
                                    )

# =============================================================================
# TAB 5: AI Insights — Cost Reduction & Service Provider Misbehaviour Detection
# =============================================================================
if page == "AI Insights":
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

    # Compute unit prices safely
    vendor_pricing = (
        filtered.groupby(["VENDOR_NAME", "MATERIAL_GROUP"], observed=True)
        .agg(
            TOTAL_EURO=("NET_PRICE_EURO", "sum"),
            TOTAL_QTY=("PO_QTY", "sum"),
            LINE_COUNT=("PO_QTY", "count"),
        )
        .reset_index()
    )
    vendor_pricing["AVG_UNIT_PRICE"] = vendor_pricing["TOTAL_EURO"] / vendor_pricing["TOTAL_QTY"].replace(0, 1)

    # Compute group median and std
    group_stats = vendor_pricing.groupby("MATERIAL_GROUP", observed=True)["AVG_UNIT_PRICE"].agg(["median", "std"]).reset_index()
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
        filtered.groupby(["VENDOR_NAME", "PO_POSTING_MONTH"], observed=True)
        .agg(MONTHLY_QTY=("PO_QTY", "sum"), MONTHLY_EURO=("NET_PRICE_EURO", "sum"))
        .reset_index()
    )
    vendor_avg = vendor_monthly.groupby("VENDOR_NAME", observed=True)["MONTHLY_QTY"].agg(["mean", "std"]).reset_index()
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
        filtered.groupby(["LICENCE_PLATE", "CUSTOMER_GROUP"], observed=True)
        .agg(TOTAL_EURO=("NET_PRICE_EURO", "sum"), TOTAL_QTY=("PO_QTY", "sum"), PO_LINES=("PO_QTY", "count"))
        .reset_index()
    )
    p95 = vehicle_costs.groupby("CUSTOMER_GROUP", observed=True)["TOTAL_EURO"].quantile(0.95).reset_index()
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
        filtered.groupby(["MATERIAL_GROUP", "VENDOR_NAME"], observed=True)
        .agg(VENDOR_EURO=("NET_PRICE_EURO", "sum"))
        .reset_index()
    )
    group_total = filtered.groupby("MATERIAL_GROUP", observed=True)["NET_PRICE_EURO"].sum().reset_index()
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

    # --- 6. Most Expensive Vehicles by Month ---
    st.subheader("6. Most Expensive Vehicles by Month")
    st.caption("Top 10 vehicles by total € spend for each month — highlights consistently high-cost vehicles and potential over-servicing patterns.")

    if "LICENCE_PLATE" in filtered.columns and "PO_POSTING_MONTH" in filtered.columns:
        veh_monthly = (
            filtered.groupby(["PO_POSTING_MONTH", "LICENCE_PLATE", "CUSTOMER_GROUP"], observed=True)
            .agg(
                TOTAL_EURO=("NET_PRICE_EURO", "sum"),
                TOTAL_QTY=("PO_QTY", "sum"),
                PO_LINES=("PO_QTY", "count"),
            )
            .reset_index()
        )
        veh_monthly["MONTH_NAME"] = veh_monthly["PO_POSTING_MONTH"].map(month_names)

        top_n = st.slider("Top N vehicles per month", min_value=5, max_value=50, value=10, key="expensive_veh_topn")

        available_months = sorted(veh_monthly["PO_POSTING_MONTH"].unique())
        selected_month_exp = st.selectbox(
            "Select Month",
            options=available_months,
            format_func=lambda m: month_names.get(m, str(m)),
            key="expensive_veh_month",
        )

        month_data = (
            veh_monthly[veh_monthly["PO_POSTING_MONTH"] == selected_month_exp]
            .sort_values("TOTAL_EURO", ascending=False)
            .head(top_n)
        )

        if not month_data.empty:
            st.markdown(f"**Top {top_n} most expensive vehicles in {month_names.get(selected_month_exp, selected_month_exp)}**")
            st.dataframe(
                month_data[["LICENCE_PLATE", "CUSTOMER_GROUP", "MONTH_NAME", "TOTAL_EURO", "TOTAL_QTY", "PO_LINES"]].rename(columns={
                    "LICENCE_PLATE": "Licence Plate",
                    "CUSTOMER_GROUP": "Customer Group",
                    "MONTH_NAME": "Month",
                    "TOTAL_EURO": "Total € Spend",
                    "TOTAL_QTY": "Total Qty",
                    "PO_LINES": "PO Lines",
                }),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("No vehicle data for the selected month.")

        # Repeat offenders: vehicles appearing in top N across multiple months
        st.markdown("**Repeat High-Cost Vehicles**")
        st.caption(f"Vehicles that appear in the top {top_n} most expensive list across multiple months.")
        top_per_month = (
            veh_monthly.sort_values(["PO_POSTING_MONTH", "TOTAL_EURO"], ascending=[True, False])
            .groupby("PO_POSTING_MONTH", observed=True)
            .head(top_n)
        )
        repeat_counts = top_per_month.groupby(["LICENCE_PLATE", "CUSTOMER_GROUP"], observed=True).agg(
            MONTHS_IN_TOP=("PO_POSTING_MONTH", "count"),
            TOTAL_EURO=("TOTAL_EURO", "sum"),
            TOTAL_QTY=("TOTAL_QTY", "sum"),
        ).reset_index()
        repeats = repeat_counts[repeat_counts["MONTHS_IN_TOP"] > 1].sort_values("TOTAL_EURO", ascending=False)

        if not repeats.empty:
            st.warning(f"⚠ {len(repeats)} vehicles appear in the top {top_n} in more than one month.")
            st.dataframe(
                repeats.rename(columns={
                    "LICENCE_PLATE": "Licence Plate",
                    "CUSTOMER_GROUP": "Customer Group",
                    "MONTHS_IN_TOP": "Months in Top N",
                    "TOTAL_EURO": "Total € Spend (all top months)",
                    "TOTAL_QTY": "Total Qty (all top months)",
                }),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.success(f"No vehicles appear in the top {top_n} across multiple months.")
