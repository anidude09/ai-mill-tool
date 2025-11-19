import os
from pathlib import Path
import streamlit as st
import pandas as pd
import numpy as np
import re
import difflib
from io import StringIO
import altair as alt

# -----------------------
# Streamlit Config
# -----------------------
st.set_page_config(layout="wide", page_title="Freight Lane Analysis")

# -----------------------
# Utility Functions
# -----------------------
def read_tabular(uploaded, sample_text):
    if uploaded is not None:
        try:
            return pd.read_csv(uploaded, low_memory=False)
        except Exception:
            uploaded.seek(0)
            return pd.read_csv(uploaded, sep="\t", low_memory=False)
    else:
        return pd.read_csv(StringIO(sample_text), sep="\t", low_memory=False)

def safe_dt(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df

def safe_num(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")
    return df

def clean_key_series(s):
    s = s.astype(str).fillna("").str.strip()
    s = s.apply(lambda x: re.sub(r"\s+", "", x))
    s = s.apply(lambda x: re.sub(r"[^\x20-\x7E]", "", x))
    s = s.str.replace(".0$", "", regex=True)
    return s

BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLE_FACT_LOCATIONS = [
    BASE_DIR / "KP1" / "Dashboard" / "dash_inputs" / "fact_contract_loads.csv",
    BASE_DIR / "Anirudh_Dashboard copy" / "Dashboard" / "dash_inputs" / "fact_contract_loads.csv",
]
SUMMARY_TILE_LOCATIONS = [
    BASE_DIR / "KP1" / "Dashboard" / "dash_inputs" / "summary_tiles.csv",
    BASE_DIR / "Anirudh_Dashboard copy" / "Dashboard" / "dash_inputs" / "summary_tiles.csv",
]
ROUTE_SUMMARY_LOCATIONS = [
    BASE_DIR / "KP1" / "Dashboard" / "dash_inputs" / "route_summary.csv",
    BASE_DIR / "Anirudh_Dashboard copy" / "Dashboard" / "dash_inputs" / "route_summary.csv",
]
MILL_RANKINGS_LOCATIONS = [
    BASE_DIR / "KP1" / "Dashboard" / "dash_inputs" / "mill_rankings.csv",
    BASE_DIR / "Anirudh_Dashboard copy" / "Dashboard" / "dash_inputs" / "mill_rankings.csv",
]
RL_REFERENCE_LOCATIONS = [
    BASE_DIR / "KP1" / "Dashboard" / "dash_inputs" / "rl_reference_series.csv",
    BASE_DIR / "Anirudh_Dashboard copy" / "Dashboard" / "dash_inputs" / "rl_reference_series.csv",
]
TREND_DATASET_LOCATIONS = [
    BASE_DIR / "KP1" / "analysis_outputs" / "trend_dataset.csv",
]
RL_REFERENCE_LOCATIONS = [
    Path(__file__).resolve().parent.parent / "KP1" / "Dashboard" / "dash_inputs" / "rl_reference_series.csv",
    Path(__file__).resolve().parent.parent / "Anirudh_Dashboard copy" / "Dashboard" / "dash_inputs" / "rl_reference_series.csv",
]

def _first_existing_path(paths):
    for path in paths:
        if path.exists():
            return str(path)
    return None

@st.cache_data(show_spinner=False)
def load_fact_dataframe(uploaded_file, fallback_paths):
    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file, low_memory=False)
        source = "uploaded file"
    else:
        fallback = _first_existing_path(fallback_paths)
        if not fallback:
            return None, None
        df = pd.read_csv(fallback, low_memory=False)
        source = os.path.basename(fallback)

    df.columns = [c.strip() for c in df.columns]
    date_cols = [
        "call_ready_date",
        "ship_date",
        "delivered_date",
        "rl_date",
        "al_match_date",
    ]
    df = safe_dt(df, date_cols)
    df = safe_num(
        df,
        [
            "convbf",
            "delivered_cost_per_mbf",
            "sale_price_per_mbf",
            "rl_price_per_mbf",
            "days_ready_to_ship",
            "gross_margin_per_mbf",
            "index_relative_margin_per_mbf",
        ],
    )
    if "ship_date" in df.columns and "delivered_date" in df.columns:
        df["ship_date"] = df["ship_date"].fillna(df["delivered_date"])

    df["mill_region"] = (
        df.get("mill_region", "")
        .astype(str)
        .str.strip()
        .str.lower()
    )
    df["dest_location_type"] = (
        df.get("dest_location_type", "Customer")
        .fillna("Customer")
        .astype(str)
        .str.strip()
        .str.upper()
        .replace("", "CUSTOMER")
        .replace({"CUSTOMER": "Customer", "BLR": "BLR", "TLR": "TLR"})
    )
    df["po_type_norm"] = (
        df.get("po_type", "")
        .astype(str)
        .str.strip()
        .str.lower()
    )
    dimension_series = df.get("dimension", pd.Series("", index=df.index))
    grade_series = df.get("grade", pd.Series(pd.NA, index=df.index))
    length_series = df.get("length_ft", pd.Series("", index=df.index))
    df["product_key"] = (
        dimension_series.astype(str).str.strip().str.lower()
        + " | #"
        + grade_series.astype("Int64").astype(str).replace("<NA>", "")
        + " | "
        + length_series.astype(str).str.replace(".0", "", regex=False).str.strip()
        + "ft"
    )
    df["product_key"] = df["product_key"].str.replace(" | #nan | nanft", "", regex=False)
    return df, source

@st.cache_data(show_spinner=False)
def load_optional_dataframe(uploaded_file, fallback_paths):
    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file, low_memory=False)
        source = "uploaded file"
    else:
        fallback = _first_existing_path(fallback_paths)
        if not fallback:
            return None, None
        df = pd.read_csv(fallback, low_memory=False)
        source = os.path.basename(fallback)
    df.columns = [c.strip() for c in df.columns]
    return df, source

def apply_fact_filters(df, vendors=None, regions=None, products=None, dest_types=None, date_range=None):
    if df is None:
        return None
    mask = pd.Series(True, index=df.index)
    if vendors:
        mask &= df.get("vendor_cid").isin(vendors)
    if regions:
        mask &= df.get("mill_region").isin(regions)
    if products:
        mask &= df.get("product_key").isin(products)
    if dest_types:
        mask &= df.get("dest_location_type").isin(dest_types)
    if date_range and "ship_date" in df.columns:
        start, end = date_range
        if start:
            mask &= df["ship_date"] >= pd.to_datetime(start)
        if end:
            mask &= df["ship_date"] <= pd.to_datetime(end)
    return df.loc[mask].copy()

def compute_overall_metrics(df):
    if df is None or df.empty:
        return {}
    metrics = {}
    metrics["total_volume_bf"] = float(df.get("convbf", pd.Series(dtype=float)).sum())
    metrics["total_delivered_usd"] = float(df.get("delivered_total_usd", pd.Series(dtype=float)).sum())
    metrics["avg_delivered_cost_per_mbf"] = float(df.get("delivered_cost_per_mbf", pd.Series(dtype=float)).mean())
    metrics["avg_days_ready_to_ship"] = float(df.get("days_ready_to_ship", pd.Series(dtype=float)).mean())
    metrics["gross_margin_per_mbf_avg"] = float(df.get("gross_margin_per_mbf", pd.Series(dtype=float)).mean())
    metrics["index_relative_margin_per_mbf_avg"] = float(df.get("index_relative_margin_per_mbf", pd.Series(dtype=float)).mean())
    return metrics

def aggregate_kpis(df, group_cols):
    if df is None or df.empty:
        return pd.DataFrame()
    existing = [c for c in group_cols if c in df.columns]
    if not existing:
        return pd.DataFrame()
    agg = (
        df.groupby(existing, dropna=False)
        .agg(
            volume_bf=("convbf", "sum"),
            delivered_cost_per_mbf_avg=("delivered_cost_per_mbf", "mean"),
            rl_price_per_mbf_avg=("rl_price_per_mbf", "mean"),
            index_relative_margin_per_mbf_avg=("index_relative_margin_per_mbf", "mean"),
            avg_days_ready_to_ship=("days_ready_to_ship", "mean"),
        )
        .reset_index()
    )
    return agg.sort_values("delivered_cost_per_mbf_avg")

def compute_route_summary(df):
    if df is None or df.empty:
        return pd.DataFrame()
    cols = [
        "mill",
        "vendor_cid",
        "dest_location_type",
        "dest_city",
        "dest_st",
        "dimension",
        "grade",
        "length_ft",
    ]
    cols = [c for c in cols if c in df.columns]
    if not cols:
        return pd.DataFrame()
    route = (
        df.groupby(cols, dropna=False)
        .agg(
            volume_bf=("convbf", "sum"),
            delivered_cost_per_mbf_avg=("delivered_cost_per_mbf", "mean"),
            rl_price_per_mbf_avg=("rl_price_per_mbf", "mean"),
            index_relative_margin_per_mbf_avg=("index_relative_margin_per_mbf", "mean"),
        )
        .reset_index()
    )
    return route

def compute_trend_series(df, freq="W"):
    if df is None or df.empty or "ship_date" not in df.columns:
        return pd.DataFrame()
    subset = df.dropna(subset=["ship_date"]).copy()
    if subset.empty:
        return pd.DataFrame()
    period = subset["ship_date"].dt.to_period(freq).dt.start_time
    trend = (
        subset.assign(period=period)
        .groupby("period", as_index=False)
        .agg(
            avg_delivered=("delivered_cost_per_mbf", "mean"),
            avg_rl=("rl_price_per_mbf", "mean"),
            avg_index_margin=("index_relative_margin_per_mbf", "mean"),
            volume_bf=("convbf", "sum"),
        )
        .dropna(subset=["period"])
        .sort_values("period")
    )
    return trend

def recommend_routes(df, dest_type, min_volume=50):
    if df is None or df.empty:
        return pd.DataFrame()
    subset = df[df.get("dest_location_type") == dest_type].copy()
    if subset.empty:
        return pd.DataFrame()
    subset = subset[subset.get("convbf", 0) >= min_volume]
    if subset.empty:
        return pd.DataFrame()
    subset = subset[
        subset.get("index_relative_margin_per_mbf", 0).notna()
    ]
    subset = subset.sort_values(
        ["delivered_cost_per_mbf", "index_relative_margin_per_mbf"],
        ascending=[True, False],
    )
    return subset[
        [
            "mill",
            "vendor_cid",
            "dest_city",
            "dest_st",
            "dimension",
            "grade",
            "length_ft",
            "convbf",
            "delivered_cost_per_mbf",
            "rl_price_per_mbf",
            "index_relative_margin_per_mbf",
        ]
    ].head(15)

def format_number(value, precision=0, suffix=""):
    if value is None:
        return "—"
    try:
        if isinstance(value, float) and np.isnan(value):
            return "—"
    except TypeError:
        pass
    fmt = f"{{:,.{precision}f}}"
    try:
        return f"{fmt.format(value)}{suffix}"
    except Exception:
        return str(value)

def drop_all_null_columns(df):
    if df is None or df.empty:
        return df
    return df.loc[:, df.notna().any(axis=0)]

def ensure_dataframe(obj):
    """Convert narwhals/Streamlit dataframe wrappers back to pandas for Altair."""
    if obj is None or isinstance(obj, pd.DataFrame):
        return obj
    for attr in ("to_pandas", "to_native"):
        method = getattr(obj, attr, None)
        if callable(method):
            try:
                converted = method()
            except Exception:
                continue
            if isinstance(converted, pd.DataFrame):
                return converted
    return obj

# -----------------------
# Sidebar Inputs
# -----------------------
st.title("Freight Intelligence Dashboard")

st.sidebar.header("Data Input")
lane_file = st.sidebar.file_uploader("Upload LaneOne CSV/TSV", type=["csv", "tsv", "txt"])
al_file = st.sidebar.file_uploader("Upload American Lumber CSV/TSV", type=["csv", "tsv", "txt"])

st.sidebar.markdown("---")
st.sidebar.header("Mill KPI Inputs")
fact_file = st.sidebar.file_uploader(
    "Upload Contract Loads CSV (fact_contract_loads.csv)",
    type=["csv"],
    key="fact_contract_loads",
)
fact_df, fact_source = load_fact_dataframe(fact_file, SAMPLE_FACT_LOCATIONS)
if fact_df is None:
    st.sidebar.info(
        "Upload fact_contract_loads.csv (or place it in KP1/…/dash_inputs) to enable the KPI view."
    )
else:
    st.sidebar.caption(f"KPI data source: {fact_source} — rows: {len(fact_df):,}")

st.sidebar.markdown("---")
st.sidebar.header("Random Lengths Visuals")
rl_upload = st.sidebar.file_uploader(
    "Upload rl_reference_series.csv",
    type=["csv"],
    key="rl_reference_series",
)
rl_df, rl_source = load_optional_dataframe(rl_upload, RL_REFERENCE_LOCATIONS)
if rl_df is not None:
    st.sidebar.caption(f"RL series source: {rl_source} — rows: {len(rl_df):,}")
    rl_df["rl_date"] = pd.to_datetime(rl_df.get("rl_date"), errors="coerce")
    rl_df["grade"] = pd.to_numeric(rl_df.get("grade"), errors="coerce")
trend_upload = st.sidebar.file_uploader(
    "Upload trend_dataset.csv",
    type=["csv"],
    key="trend_dataset",
)
trend_df_full, trend_source = load_optional_dataframe(trend_upload, TREND_DATASET_LOCATIONS)
if trend_df_full is not None:
    trend_df_full = trend_df_full.rename(columns={"length":"length_ft"})
    trend_df_full["transaction_date"] = pd.to_datetime(trend_df_full.get("transaction_date"), errors="coerce")
    trend_df_full["length_ft"] = pd.to_numeric(trend_df_full.get("length_ft"), errors="coerce")
    st.sidebar.caption(f"Trend dataset source: {trend_source} — rows: {len(trend_df_full):,}")

tab_lane, tab_mill, tab_rl = st.tabs([
    "Freight Lane Analysis",
    "Mill Delivered Cost KPIs",
    "Random Lengths Trends",
])

with tab_lane:
    st.header("Freight Lane Analysis")
    sample_lane = """AljexPro #\tType of Shipment\tActual Dispatcher\tShip Date\tDelivered Date\tPickup City\tPickup State\tConsignee City\tConsignee State\tCarrier Name\tMiles/Class\tLOT Revenue\tLOT Carrier Expense
    33769\tF\tSTANVAN\t1/3/2025\t1/6/2025\tGLOSTER\tMS\tKENNARD\tTX\tFBN TRANSPORTATION\t309\t1055.31\t1000
    """
    sample_al = """poRecordID\tAljexProNum\tpoType\tDATRate\tTotalCost\tBF\tMill
    481062\t00033769\tDirect PO\t1200\t2296\t6656\tWeyerhaeuser
    """
    
    lane_df = read_tabular(lane_file, sample_lane)
    al_df = read_tabular(al_file, sample_al)
    
    lane_df.columns = [c.strip() for c in lane_df.columns]
    al_df.columns = [c.strip() for c in al_df.columns]
    
    # -----------------------
    # Detect PRO Columns
    # -----------------------
    lane_pro_col = None
    for candidate in ["AljexPro #", "AljexPro#", "Pro #", "ProNum"]:
        if candidate in lane_df.columns:
            lane_pro_col = candidate
            break
    
    al_pro_col = None
    for candidate in ["AljexProNum", "AljexPro Num", "AljexPro"]:
        if candidate in al_df.columns:
            al_pro_col = candidate
            break
    
    if not lane_pro_col or not al_pro_col:
        st.error("❌ Could not find PRO columns. Expected 'AljexPro #' in LaneOne and 'AljexProNum' in AL.")
        st.stop()
    
    # -----------------------
    # Clean and Normalize Keys
    # -----------------------
    lane_df["ProKey"] = clean_key_series(lane_df[lane_pro_col]).str.lstrip("0")
    al_df["ProKey"] = clean_key_series(al_df[al_pro_col]).str.lstrip("0")
    
    # -----------------------
    # Direct PO Filter
    # -----------------------
    if "poType" in al_df.columns:
        al_df["poType_norm"] = al_df["poType"].astype(str).str.strip().str.lower()
    else:
        al_df["poType_norm"] = ""
    
    direct_po_mask = al_df["poType_norm"].str.contains(r"direct", na=False)
    al_direct = al_df.loc[direct_po_mask].copy()
    
    #st.write("Direct PO rows in AL (count):", len(al_direct))
    
    # -----------------------
    # Parse Dates & Numbers
    # -----------------------
    lane_df = safe_dt(lane_df, ["Ship Date", "Delivered Date"])
    al_df = safe_dt(al_df, ["DeliveredDate"])
    
    lane_df = safe_num(lane_df, ["Miles/Class", "LOT Carrier Expense"])
    al_df = safe_num(al_df, ["DATRate", "TotalCost", "BF"])
    
    # -----------------------
    # Aggregate AL Direct POs
    # -----------------------
    al_agg = (
        al_direct.groupby("ProKey", dropna=False)
        .agg(
            DATRate_mean=("DATRate", "mean"),
            DATRate_count=("DATRate", "count"),
            TotalCost_sum=("TotalCost", "sum"),
            BF_sum=("BF", "sum"),
            Mill=("Mill", lambda s: s.dropna().mode().iloc[0] if not s.dropna().empty else None)
        )
        .reset_index()
    )
    
    # -----------------------
    # Merge
    # -----------------------
    lane_with_dat = lane_df.merge(al_agg, on="ProKey", how="left")
    lane_with_dat["DATRate_per_mile"] = lane_with_dat["DATRate_mean"] / lane_with_dat["Miles/Class"]
    
    # -----------------------
    # Compute Metrics
    # -----------------------
    # Ensure Created Date is parsed (some files use Created Date or CreatedDate)
    lane_df = safe_dt(lane_df, ["Created Date", "CreatedDate", "Ship Date", "ShipDate", "Delivered Date", "DeliveredDate"])
    # Ensure LOT Carrier Expense numeric exists
    lane_df = safe_num(lane_df, ["LOT Carrier Expense", "LOTCarrierExpense", "LOTCarrierExpense_num"])
    # Normalize miles into a usable numeric column
    if "Miles_num" not in lane_df.columns:
        if "Miles/Class" in lane_df.columns:
            lane_df["Miles_num"] = pd.to_numeric(lane_df["Miles/Class"], errors="coerce")
        else:
            # try "Miles" or fallback
            lane_df["Miles_num"] = pd.to_numeric(lane_df.get("Miles", np.nan), errors="coerce")
    
    # Compute Days Created -> Ship (if both dates exist)
    if ("Created Date" in lane_df.columns or "CreatedDate" in lane_df.columns) and ("Ship Date" in lane_df.columns or "ShipDate" in lane_df.columns):
        ship_col = "Ship Date" if "Ship Date" in lane_df.columns else "ShipDate" if "ShipDate" in lane_df.columns else None
        created_col = "Created Date" if "Created Date" in lane_df.columns else "CreatedDate" if "CreatedDate" in lane_df.columns else None
        lane_df["DaysCreatedToShip"] = (lane_df[ship_col] - lane_df[created_col]).dt.days
    else:
        lane_df["DaysCreatedToShip"] = np.nan
    
    # Compute LOT carrier expense numeric (safe)
    lot_cols = ["LOT Carrier Expense", "LOTCarrierExpense", "LOTCarrierExpense_num"]
    lot_col_present = next((c for c in lot_cols if c in lane_df.columns), None)
    if lot_col_present is None:
        # create zero column if missing
        lane_df["LOTCarrierExpense_num"] = 0.0
    else:
        lane_df["LOTCarrierExpense_num"] = pd.to_numeric(lane_df[lot_col_present], errors="coerce").fillna(0.0)
    
    # Carrier expense per mile
    lane_df["CarrierExpense_per_mile"] = lane_df["LOTCarrierExpense_num"] / lane_df["Miles_num"].replace({0: np.nan})
    
    # If DATRate per mile already created use it; otherwise ensure lane_with_dat has DATRate_per_mile
    # (Your earlier merge created lane_with_dat; ensure we work with that)
    if "lane_with_dat" not in globals():
        lane_with_dat = lane_df.merge(al_agg, on="ProKey", how="left")
    else:
        # refresh lane_with_dat's expense/miles/days from lane_df
        for col in ["DaysCreatedToShip", "LOTCarrierExpense_num", "Miles_num", "CarrierExpense_per_mile"]:
            lane_with_dat[col] = lane_df[col]
    
    # Recompute DATRate_per_mile safely
    lane_with_dat["DATRate_per_mile"] = lane_with_dat["DATRate_mean"] / lane_with_dat["Miles_num"].replace({0: np.nan})
    
    # Build LaneKey (pickup state -> consignee state or city -> city)
    def lane_key_fn(r):
        pstate = str(r.get("Pickup State", r.get("PickupState", "")) or "").strip()
        cstate = str(r.get("Consignee State", r.get("ConsigneeState", "")) or "").strip()
        if pstate and cstate:
            return f"{pstate} → {cstate}"
        pcity = str(r.get("Pickup City", r.get("PickupCity", "")) or "").strip()
        ccity = str(r.get("Consignee City", r.get("ConsigneeCity", "")) or "").strip()
        if pcity and ccity:
            return f"{pcity} → {ccity}"
        return "Unknown"
    
    lane_with_dat["LaneKey"] = lane_with_dat.apply(lane_key_fn, axis=1)
    
    # Aggregate to lane-level
    min_loads = 1  # you can expose as a slider if desired
    lane_agg = (
        lane_with_dat.groupby("LaneKey", dropna=False)
        .agg(
            avg_days=("DaysCreatedToShip", "mean"),
            median_days=("DaysCreatedToShip", "median"),
            avg_expense_per_mile=("CarrierExpense_per_mile", "mean"),
            median_expense_per_mile=("CarrierExpense_per_mile", "median"),
            avg_miles=("Miles_num", "mean"),
            load_count=("ProKey", lambda s: s.nunique()),
            avg_DATRate_per_mile=("DATRate_per_mile", "mean"),
            dat_load_count=("DATRate_per_mile", lambda s: s.notna().sum())
        )
        .reset_index()
    )
    
    # Filter low-count lanes if desired
    lane_agg = lane_agg[lane_agg["load_count"] >= min_loads].copy()
    lane_agg["expense_minus_DAT_per_mile"] = lane_agg["avg_expense_per_mile"] - lane_agg["avg_DATRate_per_mile"]
    
    # -----------------------
    # Compute mill_agg (mill-level summary)
    # -----------------------
    if "Mill" in lane_with_dat.columns and lane_with_dat["Mill"].notna().any():
        mill_agg = (
            lane_with_dat.groupby("Mill")
            .agg(
                avg_days=("DaysCreatedToShip", "mean"),
                avg_expense_per_mile=("CarrierExpense_per_mile", "mean"),
                load_count=("ProKey", "nunique")
            )
            .reset_index()
        )
    else:
        mill_agg = pd.DataFrame(columns=["Mill", "avg_days", "avg_expense_per_mile", "load_count"])
    
    lane_with_dat = ensure_dataframe(lane_with_dat)
    lane_agg = ensure_dataframe(lane_agg)
    mill_agg = ensure_dataframe(mill_agg)
    
    # -----------------------
    # Visualization plots
    # -----------------------
    tab1, tab2, tab3, tab4 = st.tabs([
        "📦 Days Created → Ship",
        "💰 Carrier Expense per Mile",
        "📊 DAT Index Comparison",
        "🏭 Mill Performance"
    ])
    
    with tab1:
        st.header("📦 Distribution of Days from Load Creation to Shipment")
        hist_days = alt.Chart(lane_with_dat).mark_bar().encode(
            x=alt.X("DaysCreatedToShip:Q", bin=True, title="Days Created → Ship"),
            y="count()"
        )
        st.altair_chart(hist_days, use_container_width=True)
    
        st.subheader("Average Days from Load Creation to Shipment by Lane")
        chart_days = alt.Chart(lane_agg).mark_bar().encode(
            x=alt.X("LaneKey:N", sort='-y'),
            y=alt.Y("avg_days:Q", title="Avg Days Created → Ship"),
            tooltip=["LaneKey", "avg_days", "load_count"]
        ).properties(height=400)
    
        st.altair_chart(chart_days, use_container_width=True)
    
        # Show top/bottom by avg days
        st.markdown("---")
        st.subheader("Top lanes by Average Days Created → Ship (longest)")
        st.dataframe(lane_agg.sort_values("avg_days", ascending=False)[
                     ["LaneKey", "avg_days", "avg_expense_per_mile", "avg_DATRate_per_mile", "load_count"]].round(
        2).head(10))

        st.subheader("Bottom lanes by Average Days Created → Ship (shortest)")
        st.dataframe(lane_agg.sort_values("avg_days", ascending=True)[
                     ["LaneKey", "avg_days", "avg_expense_per_mile", "avg_DATRate_per_mile", "load_count"]].round(
        2).head(10))

        st.subheader("🚨 Negative Days Diagnostics")
        negatives = lane_df[lane_df["DaysCreatedToShip"] < 0]
        st.write(f"Negative records found: {len(negatives)}")

        if len(negatives) > 0:
            st.write(negatives[[
                lane_pro_col,
                "Ship Date",
                "Created Date",
                "DaysCreatedToShip"
            ]].head(50))

        st.subheader("🚨 NaN Days Diagnostics")

        nan_days = lane_df[lane_df["DaysCreatedToShip"].isna()]
        st.write(f"NaN records found: {len(nan_days)}")

        if len(nan_days) > 0:
            # Only show columns that actually exist
            cols_to_show = [lane_pro_col]

            if "Ship Date" in lane_df.columns:
                cols_to_show.append("Ship Date")
            if "Created Date" in lane_df.columns:
                cols_to_show.append("Created Date")
            if "DaysCreatedToShip" in lane_df.columns:
                cols_to_show.append("DaysCreatedToShip")
    
            st.write(nan_days[cols_to_show].head(50))


with tab2:
    st.header("💰 Carrier Expense per Mile")
    # Visualization
    chart_expense = alt.Chart(lane_agg).mark_bar().encode(
        x=alt.X("LaneKey:N", sort="-y", title="Lane"),
        y=alt.Y("avg_expense_per_mile:Q", title="Avg Cost per Mile ($/mile)"),
        tooltip=["LaneKey", "avg_expense_per_mile", "load_count"]
    ).properties(
        height=400,
        title="Average Carrier Expense per Mile by Lane"
    )
    st.altair_chart(chart_expense, use_container_width=True)

    # Boxplot (variation)
    box = alt.Chart(lane_with_dat).mark_boxplot().encode(
        x=alt.X("LaneKey:N", title="Lane"),
        y=alt.Y("CarrierExpense_per_mile:Q", title="Cost per Mile"),
        tooltip=["LaneKey", "CarrierExpense_per_mile"]
    ).properties(
        height=450,
        title="Cost per Mile Variability by Lane"
    )
    st.altair_chart(box, use_container_width=True)
    # Show top/bottom by expense per mile
    st.markdown("---")
    st.subheader("Top lanes by Average Carrier Expense per Mile (highest)")
    st.dataframe(lane_agg.sort_values("avg_expense_per_mile", ascending=False)[
                     ["LaneKey", "avg_expense_per_mile", "avg_DATRate_per_mile", "avg_days", "load_count"]].round(
        3).head(10))

    st.subheader("Bottom lanes by Average Carrier Expense per Mile (lowest)")
    st.dataframe(lane_agg.sort_values("avg_expense_per_mile", ascending=True)[
                     ["LaneKey", "avg_expense_per_mile", "avg_DATRate_per_mile", "avg_days", "load_count"]].round(
        3).head(10))

with tab3:
    # Bar: Expense - DAT difference
    diff_bar = alt.Chart(lane_agg).mark_bar().encode(
        x=alt.X("LaneKey:N", sort="-y", title="Lane"),
        y=alt.Y("expense_minus_DAT_per_mile:Q", title="Expense − DAT ($/mile)"),
        tooltip=["LaneKey", "expense_minus_DAT_per_mile"]
    ).properties(
        title="Difference Between Actual Carrier Cost and DAT Index"
    )
    st.altair_chart(diff_bar, use_container_width=True)

    # Quick table of lanes with highest expense - DAT gaps
    st.markdown("---")
    st.subheader("Lanes with largest Expense − DAT per mile (top 10)")
    st.dataframe(lane_agg.sort_values("expense_minus_DAT_per_mile", ascending=False)[
                     ["LaneKey", "avg_expense_per_mile", "avg_DATRate_per_mile", "expense_minus_DAT_per_mile",
                      "load_count"]].head(10).round(3))


    # Compare expense vs DATRate per mile in a scatter
    st.markdown("---")
    st.subheader("Scatter: Avg Expense per Mile vs Avg DATRate per Mile (lane)")
    if lane_agg.shape[0] > 0:
        scatter = alt.Chart(lane_agg).mark_circle().encode(
            x=alt.X("avg_expense_per_mile:Q", title="Avg Carrier Expense per Mile (USD)"),
            y=alt.Y("avg_DATRate_per_mile:Q", title="Avg DATRate per Mile (USD)"),
            size=alt.Size("load_count:Q", title="Load Count"),
            color=alt.Color("expense_minus_DAT_per_mile:Q", title="Expense − DAT per mile",
                            scale=alt.Scale(scheme="redblue")),
            tooltip=["LaneKey", "avg_expense_per_mile", "avg_DATRate_per_mile", "avg_days", "load_count"]
        ).interactive()
        st.altair_chart(scatter, use_container_width=True)

with tab4:
    st.header("🏭 Mill Performance Comparison")
    cost_chart = alt.Chart(mill_agg).mark_bar().encode(
        x=alt.X("avg_expense_per_mile:Q", title="Avg Cost per Mile"),
        y=alt.Y("Mill:N", sort='-x', title="Mill"),
        tooltip=["Mill", "avg_expense_per_mile", "load_count"]
    ).properties(
        height=500,
        title="Average Carrier Expense per Mile by Mill"
    )
    st.altair_chart(cost_chart, use_container_width=True)

    days_chart = alt.Chart(mill_agg).mark_bar().encode(
        x=alt.X("avg_days:Q", title="Avg Days Created → Ship"),
        y=alt.Y("Mill:N", sort='-x'),
        tooltip=["Mill", "avg_days", "load_count"]
    ).properties(
        height=500,
        title="Average Days Created → Ship by Mill"
    )
    st.altair_chart(days_chart, use_container_width=True)
    # Mill-level aggregation & top mills
    if "Mill" in lane_with_dat.columns and lane_with_dat["Mill"].notna().any():
        mill_agg = lane_with_dat.groupby("Mill").agg(
            avg_days=("DaysCreatedToShip", "mean"),
            avg_expense_per_mile=("CarrierExpense_per_mile", "mean"),
            load_count=("ProKey", lambda s: s.nunique())
        ).reset_index()
        st.markdown("---")
        st.subheader("Top Mills by Average Carrier Expense per Mile")
        st.dataframe(mill_agg.sort_values("avg_expense_per_mile", ascending=False).head(10).round(3))
        st.subheader("Top Mills by Average Days Created → Ship")
        st.dataframe(mill_agg.sort_values("avg_days", ascending=False).head(10).round(2))
    else:
        st.info("No Mill information available to aggregate.")


with tab_mill:
    st.header("Mill Delivered Cost KPIs")
    if fact_df is None:
        st.info("Upload fact_contract_loads.csv in the sidebar to enable this view.")
    else:
        ship_dates = fact_df["ship_date"] if "ship_date" in fact_df.columns else pd.Series([], dtype="datetime64[ns]")
        min_ship = pd.to_datetime(ship_dates.min()) if not ship_dates.empty else None
        max_ship = pd.to_datetime(ship_dates.max()) if not ship_dates.empty else None
        default_range = None
        if pd.notna(min_ship) and pd.notna(max_ship):
            default_range = (min_ship.date(), max_ship.date())

        with st.expander("Filters", expanded=True):
            region_series = fact_df.get("mill_region")
            region_options = sorted(region_series.dropna().unique().tolist()) if region_series is not None else []
            dest_series = fact_df.get("dest_location_type")
            dest_options = sorted(pd.Series(dest_series).dropna().unique().tolist()) if dest_series is not None else []
            product_series = fact_df.get("product_key")
            product_options = sorted(product_series.dropna().unique().tolist()) if product_series is not None else []

            c1, c2 = st.columns(2)
            region_sel = c1.multiselect("Region", region_options, key="region_filter")
            dest_sel = c2.multiselect("Destination Type", dest_options, key="dest_filter")
            product_sel = st.multiselect("Product (Dimension | Grade | Length)", product_options, key="product_filter")

            if default_range:
                date_input = st.date_input(
                    "Ship Date Range",
                    value=default_range,
                    key="kpi_date_range",
                )
            else:
                today = pd.Timestamp.today().date()
                date_input = st.date_input(
                    "Ship Date Range",
                    value=(today, today),
                    key="kpi_date_range",
                )
            if isinstance(date_input, tuple) and len(date_input) == 2:
                date_range = date_input
            else:
                date_range = (date_input, date_input)

        filtered_fact = apply_fact_filters(
            fact_df,
            vendors=None,
            regions=region_sel or None,
            products=product_sel or None,
            dest_types=dest_sel or None,
            date_range=date_range,
        )
        filtered_fact = ensure_dataframe(filtered_fact)

        if filtered_fact is None or filtered_fact.empty:
            st.warning("No rows match the selected filters.")
        else:
            summary_metrics = compute_overall_metrics(filtered_fact)
            comparison_by_mill = ensure_dataframe(aggregate_kpis(filtered_fact, ["mill"]))
            comparison_by_vendor = ensure_dataframe(aggregate_kpis(filtered_fact, ["vendor_cid"]))
            comparison_by_region = ensure_dataframe(aggregate_kpis(filtered_fact, ["mill_region"]))
            comparison_by_product = ensure_dataframe(aggregate_kpis(filtered_fact, ["product_key"]))
            comparison_by_mill_dest = ensure_dataframe(aggregate_kpis(filtered_fact, ["mill", "dest_location_type"]))
            trend_df = ensure_dataframe(compute_trend_series(filtered_fact, freq="W"))

            card_cols = st.columns(3)
            card_cols[0].metric("Total Volume (BF)", format_number(summary_metrics.get("total_volume_bf"), 0))
            card_cols[1].metric("Delivered Spend (USD)", format_number(summary_metrics.get("total_delivered_usd"), 0))
            card_cols[2].metric("Avg Delivered $/MBF", format_number(summary_metrics.get("avg_delivered_cost_per_mbf"), 2))
            card_cols2 = st.columns(3)
            card_cols2[0].metric("Avg Days Ready → Ship", format_number(summary_metrics.get("avg_days_ready_to_ship"), 1))
            card_cols2[1].metric("Avg Gross Margin $/MBF", format_number(summary_metrics.get("gross_margin_per_mbf_avg"), 2))
            card_cols2[2].metric("Avg Index Margin $/MBF", format_number(summary_metrics.get("index_relative_margin_per_mbf_avg"), 2))

            st.markdown("### Delivered vs RL Price Trend")
            if trend_df.empty:
                st.info("Not enough ship dates to plot a trend.")
            else:
                plot_df = trend_df.melt("period", ["avg_delivered", "avg_rl"], var_name="Series", value_name="Value").dropna(subset=["Value"])
                plot_df = ensure_dataframe(plot_df)
                trend_chart = (
                    alt.Chart(plot_df)
                    .mark_line(point=True)
                    .encode(
                        x=alt.X("period:T", title="Ship Week"),
                        y=alt.Y("Value:Q", title="$ per MBF"),
                        color=alt.Color("Series:N", title="Series", scale=alt.Scale(range=["#1f77b4", "#ff7f0e"])),
                        tooltip=[alt.Tooltip("period:T", title="Week"), alt.Tooltip("Series:N"), alt.Tooltip("Value:Q", format=".1f")],
                    )
                    .properties(height=320)
                )
                st.altair_chart(trend_chart, use_container_width=True)

            vendor_table = drop_all_null_columns(comparison_by_vendor).round(2)
            st.markdown("### Performance by Vendor")
            if vendor_table.empty:
                st.info("Vendor information unavailable.")
            else:
                st.dataframe(vendor_table)
                vendor_chart_df = ensure_dataframe(
                    comparison_by_vendor.dropna(subset=["delivered_cost_per_mbf_avg"]).head(25)
                )
                vendor_chart = (
                    alt.Chart(vendor_chart_df)
                    .mark_bar()
                    .encode(
                        x=alt.X("vendor_cid:N", sort="-y", title="Vendor CID"),
                        y=alt.Y("delivered_cost_per_mbf_avg:Q", title="Avg Delivered $/MBF"),
                        color=alt.Color("index_relative_margin_per_mbf_avg:Q", title="Index Margin", scale=alt.Scale(scheme="redblue")),
                        tooltip=[
                            alt.Tooltip("vendor_cid:N", title="Vendor"),
                            alt.Tooltip("volume_bf:Q", title="Volume", format=","),
                            alt.Tooltip("delivered_cost_per_mbf_avg:Q", title="Delivered $/MBF", format=".1f"),
                            alt.Tooltip("rl_price_per_mbf_avg:Q", title="RL $/MBF", format=".1f"),
                            alt.Tooltip("index_relative_margin_per_mbf_avg:Q", title="Index Margin", format=".1f"),
                        ],
                    )
                )
                st.altair_chart(vendor_chart, use_container_width=True)

            mill_table = drop_all_null_columns(comparison_by_mill).round(2)
            st.markdown("### Performance by Mill")
            if mill_table.empty:
                st.info("Mill information unavailable.")
            else:
                st.dataframe(mill_table)
                mill_chart_df = ensure_dataframe(
                    comparison_by_mill.dropna(subset=["delivered_cost_per_mbf_avg"]).copy()
                )
                color_channel = alt.value("#4c78a8")
                if "mill_region" in mill_chart_df.columns:
                    mill_chart_df["mill_region_plot"] = (
                        mill_chart_df["mill_region"]
                        .fillna("Unknown")
                        .astype(str)
                    )
                    color_channel = alt.Color("mill_region_plot:N", title="Region")
                else:
                    mill_chart_df["mill_region_plot"] = "Unknown"
                mill_scatter = (
                    alt.Chart(mill_chart_df)
                    .mark_circle(size=120, opacity=0.75)
                    .encode(
                        x=alt.X("delivered_cost_per_mbf_avg:Q", title="Delivered $/MBF"),
                        y=alt.Y("index_relative_margin_per_mbf_avg:Q", title="Index Margin $/MBF"),
                        size=alt.Size("volume_bf:Q", title="Volume (BF)"),
                        color=color_channel,
                        tooltip=[
                            "mill",
                            "mill_region_plot",
                            "volume_bf",
                            "delivered_cost_per_mbf_avg",
                            "rl_price_per_mbf_avg",
                            "index_relative_margin_per_mbf_avg",
                        ],
                    )
                )
                st.altair_chart(mill_scatter, use_container_width=True)

            region_table = ensure_dataframe(drop_all_null_columns(comparison_by_region).round(2))
            st.markdown("### Performance by Region")
            if region_table.empty:
                st.info("Region column missing.")
            else:
                nan_region = region_table.loc[region_table["mill_region"].isna()]
                region_table = region_table.loc[region_table["mill_region"].notna()]
                region_table = region_table.loc[:, region_table.notna().any(axis=0)]
                if not region_table.empty:
                    tooltips = ["mill_region", "delivered_cost_per_mbf_avg", "avg_days_ready_to_ship"]
                    if "rl_price_per_mbf_avg" in region_table.columns:
                        tooltips.insert(2, "rl_price_per_mbf_avg")
                    region_chart = (
                        alt.Chart(region_table)
                        .mark_bar()
                        .encode(
                            x=alt.X("mill_region:N", title="Region"),
                            y=alt.Y("delivered_cost_per_mbf_avg:Q", title="Avg Delivered $/MBF"),
                            tooltip=tooltips,
                        )
                    )
                    st.altair_chart(region_chart, use_container_width=True)
                    st.dataframe(region_table)
                if not nan_region.empty:
                    st.markdown("#### Shipments With Missing Region")
                    st.dataframe(nan_region)

            st.markdown("### Top Products")
            product_table = drop_all_null_columns(
                comparison_by_product.sort_values("volume_bf", ascending=False).head(25)
            ).round(2)
            if product_table.empty:
                st.info("Product information unavailable.")
            else:
                st.dataframe(product_table)

            st.markdown("### Direct vs Plant Purchase Orders")
            direct_mask = filtered_fact["po_type_norm"].str.contains("direct", na=False)
            plant_mask = filtered_fact["po_type_norm"].str.contains("plant", na=False)
            direct_df = filtered_fact[direct_mask]
            plant_df = filtered_fact[plant_mask]

            dcols = st.columns(3)
            direct_metrics = compute_overall_metrics(direct_df)
            dcols[0].metric("Direct Volume (BF)", format_number(direct_metrics.get("total_volume_bf"), 0))
            dcols[1].metric("Direct Delivered $/MBF", format_number(direct_metrics.get("avg_delivered_cost_per_mbf"), 2))
            dcols[2].metric("Direct Index Margin $/MBF", format_number(direct_metrics.get("index_relative_margin_per_mbf_avg"), 2))

            pcols = st.columns(3)
            plant_metrics = compute_overall_metrics(plant_df)
            pcols[0].metric("Plant Volume (BF)", format_number(plant_metrics.get("total_volume_bf"), 0))
            pcols[1].metric("Plant Delivered $/MBF", format_number(plant_metrics.get("avg_delivered_cost_per_mbf"), 2))
            pcols[2].metric("Plant Index Margin $/MBF", format_number(plant_metrics.get("index_relative_margin_per_mbf_avg"), 2))

            plant_by_dest = ensure_dataframe(
                drop_all_null_columns(aggregate_kpis(plant_df, ["dest_location_type", "mill"])).round(2)
            )
            if not plant_by_dest.empty:
                st.markdown("#### Plant PO by Location (BLR/TLR)")
                st.dataframe(plant_by_dest)
                dest_chart = (
                    alt.Chart(plant_by_dest)
                    .mark_bar()
                    .encode(
                        x=alt.X("dest_location_type:N", title="Destination"),
                        y=alt.Y("delivered_cost_per_mbf_avg:Q", title="Avg Delivered $/MBF"),
                        color="dest_location_type:N",
                        tooltip=["dest_location_type","mill","delivered_cost_per_mbf_avg","volume_bf"],
                    )
                )
                st.altair_chart(dest_chart, use_container_width=True)

            st.markdown("#### Top Plant Products")
            plant_products = drop_all_null_columns(
                aggregate_kpis(plant_df, ["product_key"]).sort_values("volume_bf", ascending=False).head(25)
            ).round(2)
            if not plant_products.empty:
                st.dataframe(plant_products)

            st.markdown("### Customer vs Plant Comparisons")
            dest_choice = st.selectbox(
                "Destination Class",
                ["All"] + dest_options if dest_options else ["All"],
                key="dest_class_tab3",
            )
            comp_df = comparison_by_mill_dest.copy()
            if dest_choice != "All":
                comp_df = comp_df[comp_df["dest_location_type"] == dest_choice]
            comp_df = ensure_dataframe(drop_all_null_columns(comp_df).sort_values("delivered_cost_per_mbf_avg"))
            if comp_df.empty:
                st.info("No rows for the selected destination class.")
            else:
                st.dataframe(comp_df.round(2))
                comp_chart_df = ensure_dataframe(comp_df.head(30))
                route_chart = (
                    alt.Chart(comp_chart_df)
                    .mark_bar()
                    .encode(
                        x=alt.X("delivered_cost_per_mbf_avg:Q", title="Avg Delivered $/MBF"),
                        y=alt.Y("mill:N", sort="-x", title="Mill"),
                        color="dest_location_type:N",
                        tooltip=[t for t in ["mill","dest_location_type","delivered_cost_per_mbf_avg","rl_price_per_mbf_avg","volume_bf"] if t in comp_df.columns],
                    )
                )
                st.altair_chart(route_chart, use_container_width=True)

            st.markdown("#### Product Detail by Mill and Destination")
            product_comp = aggregate_kpis(filtered_fact, ["mill", "product_key", "dest_location_type"])
            if dest_choice != "All":
                product_comp = product_comp[product_comp["dest_location_type"] == dest_choice]
            product_comp = ensure_dataframe(
                drop_all_null_columns(product_comp).sort_values(
                    ["dest_location_type", "delivered_cost_per_mbf_avg"]
                )
            )
            if product_comp.empty:
                st.info("No product-level rows for the selection.")
            else:
                st.dataframe(product_comp.round(2).head(100))

            st.markdown("### Optimal Mill Recommendations")
            rec_dest = st.selectbox(
                "Destination Type",
                dest_options if dest_options else ["Customer"],
                key="rec_dest_select",
            )
            min_volume = int(st.slider("Minimum Volume (BF)", min_value=10, max_value=1000, value=100, step=10))
            rec_table = recommend_routes(filtered_fact, rec_dest, min_volume=min_volume)
            if rec_table.empty:
                st.info("No recommendations found for the selected constraints.")
            else:
                rec_table = ensure_dataframe(rec_table.round(2))
                st.dataframe(rec_table)
                rec_chart = (
                    alt.Chart(rec_table)
                    .mark_circle(size=140)
                    .encode(
                        x=alt.X("delivered_cost_per_mbf:Q", title="Delivered $/MBF"),
                        y=alt.Y("rl_price_per_mbf:Q", title="Random Lengths $/MBF"),
                        size=alt.Size("convbf:Q", title="Volume (BF)"),
                        color=alt.Color("index_relative_margin_per_mbf:Q", title="Index Margin", scale=alt.Scale(scheme="redblue")),
                        tooltip=["mill","dest_city","dest_st","dimension","grade","length_ft","convbf","delivered_cost_per_mbf","rl_price_per_mbf","index_relative_margin_per_mbf"],
                    )
                )
                st.altair_chart(rec_chart, use_container_width=True)

with tab_rl:
    st.header("Random Lengths Price Trends")
    if rl_df is None or rl_df.empty:
        st.info("Upload rl_reference_series.csv in the sidebar to view RL price trends.")
    else:
        region_options = sorted(rl_df["region"].dropna().unique())
        dimension_options = sorted(rl_df["dimension"].dropna().unique())
        grade_options = sorted(rl_df["grade"].dropna().unique())
        col1, col2, col3 = st.columns(3)
        if not region_options or not grade_options or not dimension_options:
            st.info("rl_reference_series.csv is missing region/grade/dimension values.")
        else:
            region = col1.selectbox("Region", region_options)
            grade = col2.selectbox("Grade", grade_options)
            dimension = col3.selectbox("Dimension", dimension_options)
            subset = rl_df[
                (rl_df["region"] == region)
                & (rl_df["grade"] == grade)
                & (rl_df["dimension"] == dimension)
            ].dropna(subset=["rl_date", "rl_price_per_mbf"])
            subset = ensure_dataframe(subset)
            if subset.empty:
                st.info("No Random Lengths rows for that selection.")
            else:
                length_options = sorted(subset["length_ft"].dropna().unique().tolist())
                length_sel = st.multiselect(
                    "Lengths (ft)",
                    length_options,
                    default=length_options,
                )
                subset = subset[subset["length_ft"].isin(length_sel)]
                trend_chart = (
                    alt.Chart(subset)
                    .mark_line(point=True)
                    .encode(
                        x=alt.X("rl_date:T", title="Transaction Date"),
                        y=alt.Y("rl_price_per_mbf:Q", title="Price ($/MBF)"),
                        color=alt.Color("length_ft:N", title="Length (ft)", scale=alt.Scale(scheme="magma")),
                        tooltip=["rl_date:T","length_ft:N",alt.Tooltip("rl_price_per_mbf:Q", format=".0f")],
                    )
                    .properties(height=360, title=f"Lumber Price Trend | {region.title()} | Grade #{int(grade)} | {dimension}")
                )
                st.altair_chart(trend_chart, use_container_width=True)

    st.markdown("---")
    st.header("Trend Dataset (Rolling Averages)")
    if trend_df_full is None or trend_df_full.empty:
        st.info("Upload trend_dataset.csv in the sidebar to visualize rolling RL trends.")
    else:
        region_opts = sorted(trend_df_full["region"].dropna().unique())
        grade_opts = sorted(trend_df_full["grade"].dropna().unique())
        dim_opts = sorted(trend_df_full["dimension"].dropna().unique())
        if not region_opts or not grade_opts or not dim_opts:
            st.info("trend_dataset.csv is missing region/grade/dimension values.")
        else:
            c1, c2, c3 = st.columns(3)
            trend_region = c1.selectbox("Trend Region", region_opts, key="trend_region")
            trend_grade = c2.selectbox("Trend Grade", grade_opts, key="trend_grade")
            trend_dimension = c3.selectbox("Trend Dimension", dim_opts, key="trend_dimension")
            subset_trend = trend_df_full[
                (trend_df_full["region"] == trend_region)
                & (trend_df_full["grade"] == trend_grade)
                & (trend_df_full["dimension"] == trend_dimension)
            ].dropna(subset=["transaction_date","rolling_avg"])
            subset_trend = ensure_dataframe(subset_trend)
            if subset_trend.empty:
                st.info("No rows in trend_dataset for that selection.")
            else:
                length_opts_trend = sorted(subset_trend["length_ft"].dropna().unique())
                length_sel_trend = st.multiselect(
                    "Trend Lengths (ft)",
                    length_opts_trend,
                    default=length_opts_trend,
                    key="trend_length_sel",
                )
                subset_trend = subset_trend[subset_trend["length_ft"].isin(length_sel_trend)]
                if subset_trend.empty:
                    st.info("No rows after length filtering.")
                else:
                    trend_chart_ds = (
                        alt.Chart(subset_trend)
                        .mark_line(point=True)
                        .encode(
                            x=alt.X("transaction_date:T", title="Transaction Date"),
                            y=alt.Y("rolling_avg:Q", title="Rolling Avg Price ($/MBF)"),
                            color=alt.Color("length_ft:N", title="Length (ft)", scale=alt.Scale(scheme="plasma")),
                            tooltip=["transaction_date:T","length_ft:N",alt.Tooltip("rolling_avg:Q", format=".0f")],
                        )
                        .properties(height=360, title=f"Rolling RL Trend | {trend_region.title()} | Grade #{int(trend_grade)} | {trend_dimension}")
                    )
                    st.altair_chart(trend_chart_ds, use_container_width=True)

