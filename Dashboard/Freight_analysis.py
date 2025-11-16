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

# -----------------------
# Sidebar Inputs
# -----------------------
st.title("Freight Lane Analysis")

st.sidebar.header("Data Input")
lane_file = st.sidebar.file_uploader("Upload LaneOne CSV/TSV", type=["csv", "tsv", "txt"])
al_file = st.sidebar.file_uploader("Upload American Lumber CSV/TSV", type=["csv", "tsv", "txt"])

# Sample fallback (for testing)
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
    st.subheader("Top Lanes by Cost per Mile")
    st.dataframe(
        lane_agg.sort_values("avg_expense_per_mile", ascending=False)
        [["LaneKey", "avg_expense_per_mile", "avg_days", "load_count"]]
        .head(15).round(3)
    )

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
    st.header("📊 Carrier Cost per Mile vs DAT Rate per Mile")

    scatter = alt.Chart(lane_agg).mark_circle(size=80).encode(
        x=alt.X("avg_expense_per_mile:Q", title="Carrier Cost per Mile"),
        y=alt.Y("avg_DATRate_per_mile:Q", title="DAT Rate per Mile"),
        color=alt.Color("expense_minus_DAT_per_mile:Q", title="Expense − DAT ($/mile)",
                        scale=alt.Scale(scheme="redblue")),
        size="load_count",
        tooltip=["LaneKey", "avg_expense_per_mile", "avg_DATRate_per_mile", "expense_minus_DAT_per_mile"]
    ).properties(
        title="Carrier Cost vs DAT Index — Lane Efficiency Map"
    )

    st.altair_chart(scatter, use_container_width=True)

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

    st.subheader("Mills with Highest Cost per Mile")
    st.dataframe(
        mill_agg.sort_values("avg_expense_per_mile", ascending=False)
        [["Mill", "avg_expense_per_mile", "avg_days", "load_count"]]
        .head(10).round(3)
    )

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


