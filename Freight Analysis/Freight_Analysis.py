
# python -m venv .venv
# .venv\Scripts\activate       
# cd "Freight Analysis"
# pip install pandas openpyxl python-dateutil
# python Freight_Analysis.py - run


import re
import pandas as pd
from dateutil import parser
from pathlib import Path


LANE_ONE_XLSX = "Lane One Data.xlsx"   # Lane One workbook
LANE_ONE_SHEET = None                  # None = auto-use first sheet; or set to sheet name/index

AL_DATA_XLSX  = "AL Data.xlsx"         # American Lumber workbook
AL_DATA_SHEET = None                   # None = auto-use first sheet; or set to sheet name/index

# Output folder
OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)

LANES_SUMMARY_CSV        = OUT_DIR / "lanes_summary.csv"
LANES_RANK_COST_CSV      = OUT_DIR / "lanes_rank_by_avg_cost_per_mile.csv"
LANES_RANK_DAYS_CSV      = OUT_DIR / "lanes_rank_by_avg_days_to_ship.csv"
DIRECT_COMPARISON_CSV    = OUT_DIR / "direct_pos_market_comparison.csv"
MILL_SUMMARY_CSV         = OUT_DIR / "mill_summary.csv"


# Helpers

def to_datetime(s):
    if pd.isna(s): 
        return pd.NaT
    try:
        return parser.parse(str(s), dayfirst=False, yearfirst=False)
    except Exception:
        return pd.NaT

def safe_div(n, d):
    try:
        if pd.notna(n) and pd.notna(d) and float(d) != 0:
            return float(n) / float(d)
    except Exception:
        pass
    return pd.NA

def coerce_numeric(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

def read_single_sheet(path: str, sheet_spec=None) -> pd.DataFrame:
    """Always return one DataFrame. If sheet_spec invalid/missing -> use first sheet."""
    xls = pd.ExcelFile(path, engine="openpyxl")
    sheets = xls.sheet_names
    if isinstance(sheet_spec, int):
        idx = max(0, min(sheet_spec, len(sheets)-1))
        print(f"[INFO] {path} -> using sheet index: {idx} ({sheets[idx]})")
        return pd.read_excel(xls, sheet_name=idx)
    elif isinstance(sheet_spec, str):
        if sheet_spec in sheets:
            print(f"[INFO] {path} -> using sheet: '{sheet_spec}'")
            return pd.read_excel(xls, sheet_name=sheet_spec)
        else:
            print(f"[WARN] Sheet '{sheet_spec}' not found in {sheets}. Using first: {sheets[0]}")
            return pd.read_excel(xls, sheet_name=0)
    else:
        print(f"[INFO] {path} sheets: {sheets} -> using first: {sheets[0]}")
        return pd.read_excel(xls, sheet_name=0)

def strip_all(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip() for c in df.columns]
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()  
    return df

def norm(s: str) -> str:
    """Lowercase, remove all non-alphanumeric (so 'Pro #' -> 'pro')."""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())

def pick_col(df: pd.DataFrame, candidates, required=True, label=""):
    """
    candidates = list of normalized substrings to try to match.
    Returns the actual column name or None.
    """

    exact_map = {norm(c): c for c in df.columns}

    for cand in candidates:
        if cand in exact_map:
            chosen = exact_map[cand]
            print(f"[MAP] {label:>16}: '{chosen}'")
            return chosen

    for c in df.columns:
        nc = norm(c)
        if any(cand in nc for cand in candidates):
            print(f"[MAP] {label:>16}: '{c}' (via contains)")
            return c

    if required:
        print(f"[WARN] Could not find column for {label} using patterns {candidates}. Available: {list(df.columns)}")
    return None

def auto_rename(df: pd.DataFrame, spec):
    """
    spec: {target_name: [candidate_patterns]}
    Returns {actual_col: target_name} mapping suitable for df.rename().
    """
    rename_map = {}
    for target, cands in spec.items():
        found = pick_col(df, cands, required=False, label=target)
        if found:
            rename_map[found] = target
    return rename_map

print("Reading Excel files…")
lane = read_single_sheet(LANE_ONE_XLSX, LANE_ONE_SHEET)
al   = read_single_sheet(AL_DATA_XLSX,  AL_DATA_SHEET)

lane = strip_all(lane)
al   = strip_all(al)

# ---- Auto-detect & rename Lane One columns ----
lane_spec = {
    "ProNumber":       ["pro", "aljexpronumber", "pronumber"],
    "CreatedDate":     ["createddate", "created_dt", "created"],
    "ShipDate":        ["shipdate", "shippeddate", "pickupdate", "ship_dt"],
    "PickupCity":      ["pickupcity", "origin", "pickup_city"],
    "PickupState":     ["pickupstate", "originstate", "pickup_st", "pickupstatecode"],
    "ConsigneeCity":   ["consigneecity", "deliverycity", "destcity"],
    "ConsigneeState":  ["consigneestate", "deliverystate", "deststate"],
    "Miles":           ["milesclass", "miles", "distance"],
    "CarrierExpense":  ["lotcarrierexpense", "carrierexpense", "carrierpay", "truckingcost"],
    "MillReadyDate":   ["millreadydt", "readydate", "callreadydate"],
    "ShipmentType":    ["typeofshipment", "shipmenttype", "shipvia"],
}
lane.rename(columns=auto_rename(lane, lane_spec), inplace=True)

# ---- Auto-detect & rename AL columns ----
al_spec = {
    "ProNumber":    ["aljexpronumber", "pro", "pronumber"],
    "POType":       ["potype", "po_type"],
    "DATRate":      ["datrate", "dat_rate"],
    "Mill":         ["mill"],
    "DeliveredDate":["delivereddate", "delivered_dt"],
    "VendorCID":    ["vendorcid", "vendor_id"],
}
al.rename(columns=auto_rename(al, al_spec), inplace=True)

needed_lane = ["ProNumber", "CreatedDate", "ShipDate", "Miles", "CarrierExpense",
               "PickupCity", "PickupState", "ConsigneeCity", "ConsigneeState"]
missing_lane = [c for c in needed_lane if c not in lane.columns]
if missing_lane:
    print(f"[WARN] Missing expected Lane One columns AFTER auto-map: {missing_lane}")

needed_al = ["ProNumber", "POType", "DATRate", "Mill"]
missing_al = [c for c in needed_al if c not in al.columns]
if missing_al:
    print(f"[WARN] Missing expected AL columns AFTER auto-map: {missing_al}")

coerce_numeric(lane, ["Miles", "CarrierExpense"])
coerce_numeric(al,   ["DATRate"])

for c in ["CreatedDate", "ShipDate", "MillReadyDate"]:
    if c in lane.columns:
        lane[c] = lane[c].apply(to_datetime)
if "DeliveredDate" in al.columns:
    al["DeliveredDate"] = al["DeliveredDate"].apply(to_datetime)

lane["DaysToShip"] = (
    (lane["ShipDate"] - lane["CreatedDate"]).dt.days
    if {"ShipDate","CreatedDate"}.issubset(lane.columns) else pd.NA
)

lane["CostPerMile"] = (
    lane.apply(lambda r: safe_div(r.get("CarrierExpense"), r.get("Miles")), axis=1)
    if {"CarrierExpense","Miles"}.issubset(lane.columns) else pd.NA
)

lane["Lane"] = (
    lane.get("PickupCity", pd.Series(["Unknown"]*len(lane))).fillna("Unknown") + ", " +
    lane.get("PickupState", pd.Series([""]*len(lane))).fillna("") +
    " \u2192 " +
    lane.get("ConsigneeCity", pd.Series(["Unknown"]*len(lane))).fillna("Unknown") + ", " +
    lane.get("ConsigneeState", pd.Series([""]*len(lane))).fillna("")
)


if "Lane" not in lane.columns:
    raise RuntimeError("Could not build 'Lane' label. Check origin/destination columns.")

lane_grp = lane.groupby("Lane", dropna=False).agg(
    Loads=("ProNumber", "count") if "ProNumber" in lane.columns else ("Lane","size"),
    AvgDaysToShip=("DaysToShip", "mean"),
    AvgCostPerMile=("CostPerMile", "mean"),
    MilesAvg=("Miles", "mean") if "Miles" in lane.columns else ("Lane","size")
).reset_index()

rank_cost = lane_grp.sort_values("AvgCostPerMile", ascending=False)
rank_days = lane_grp.sort_values("AvgDaysToShip",   ascending=False)

if "POType" in al.columns:
    al_direct = al[al["POType"].astype(str).str.lower() == "direct"].copy()
else:
    al_direct = al.iloc[0:0].copy()

join_cols = ["ProNumber"] if "ProNumber" in lane.columns and "ProNumber" in al_direct.columns else []
if join_cols:
    keep_cols = [c for c in ["ProNumber","DATRate","Mill"] if c in al_direct.columns]
    direct_join = lane.merge(al_direct[keep_cols], on="ProNumber", how="inner")
else:
    print("[WARN] Cannot join Direct POs to Lane data (no common ProNumber).")
    direct_join = lane.iloc[0:0].copy()

if not direct_join.empty and {"DATRate","Miles"}.issubset(direct_join.columns):
    direct_join["DATRatePerMile"] = direct_join.apply(lambda r: safe_div(r.get("DATRate"), r.get("Miles")), axis=1)
    direct_join["Delta_vs_DAT"] = direct_join["CostPerMile"] - direct_join["DATRatePerMile"]
    direct_lane_grp = direct_join.groupby("Lane", dropna=False).agg(
        Loads=("ProNumber","count") if "ProNumber" in direct_join.columns else ("Lane","size"),
        AvgCostPerMile=("CostPerMile","mean"),
        AvgDATPerMile=("DATRatePerMile","mean"),
        AvgDelta_vs_DAT=("Delta_vs_DAT","mean")
    ).reset_index()
else:
    direct_lane_grp = pd.DataFrame(columns=["Lane","Loads","AvgCostPerMile","AvgDATPerMile","AvgDelta_vs_DAT"])


if "Mill" in al.columns and "ProNumber" in lane.columns and "ProNumber" in al.columns:
    mill_join = lane.merge(al[["ProNumber","Mill"]].drop_duplicates(), on="ProNumber", how="left")
    mill_summary = mill_join.groupby("Mill", dropna=False).agg(
        Loads=("ProNumber","count"),
        AvgDaysToShip=("DaysToShip","mean"),
        AvgCostPerMile=("CostPerMile","mean")
    ).reset_index().sort_values(["AvgCostPerMile","AvgDaysToShip"], ascending=False)
else:
    mill_summary = pd.DataFrame(columns=["Mill","Loads","AvgDaysToShip","AvgCostPerMile"])
    print("[WARN] Mill summary skipped (missing Mill or ProNumber in one of the files).")

# Save outputs

lane_grp.to_csv(LANES_SUMMARY_CSV, index=False)
rank_cost.to_csv(LANES_RANK_COST_CSV, index=False)
rank_days.to_csv(LANES_RANK_DAYS_CSV, index=False)
direct_lane_grp.to_csv(DIRECT_COMPARISON_CSV, index=False)
mill_summary.to_csv(MILL_SUMMARY_CSV, index=False)

pd.options.display.float_format = "{:,.2f}".format

print("\n=== Top 10 Most Expensive Lanes (Avg Cost/Mile) ===")
print(rank_cost.head(10)[["Lane", "AvgCostPerMile", "AvgDaysToShip", "Loads"]])

print("\n=== Top 10 Slowest Lanes (Avg Days to Ship) ===")
print(rank_days.head(10)[["Lane", "AvgDaysToShip", "AvgCostPerMile", "Loads"]])

if not direct_lane_grp.empty:
    print("\n=== Direct POs: Lane vs DAT (Top 10 by AvgDelta_vs_DAT) ===")
    print(
        direct_lane_grp.sort_values("AvgDelta_vs_DAT", ascending=False)
        .head(10)[["Lane","AvgCostPerMile","AvgDATPerMile","AvgDelta_vs_DAT","Loads"]]
    )
else:
    print("\n(No Direct POs lane-vs-DAT comparison available.)")

print(f"\nFiles written to: {OUT_DIR.resolve()}")

# MASTER Outputs for analysis

# ===== Consolidate to a single Excel workbook & a master CSV =====
MASTER_XLSX = OUT_DIR / "Freight_Summary.xlsx"
MASTER_CSV  = OUT_DIR / "master_lanes_with_market.csv"

# 1) Excel with multiple sheets
with pd.ExcelWriter(MASTER_XLSX, engine="openpyxl") as xw:
    lane_grp.to_excel(xw, index=False, sheet_name="Lane Summary")
    rank_cost.to_excel(xw, index=False, sheet_name="Rank by Cost_Mile")
    rank_days.to_excel(xw, index=False, sheet_name="Rank by DaysToShip")
    direct_lane_grp.to_excel(xw, index=False, sheet_name="Direct vs DAT")
    mill_summary.to_excel(xw, index=False, sheet_name="Mill Summary")

# 2) Single “master” table (join lane metrics + DAT metrics, per lane)
master = lane_grp.merge(
    direct_lane_grp[["Lane", "AvgDATPerMile", "AvgDelta_vs_DAT"]],
    on="Lane", how="left"
)

# Helpful rankings
master["Rank_CostPerMile"] = master["AvgCostPerMile"].rank(ascending=False, method="dense")
master["Rank_DaysToShip"]  = master["AvgDaysToShip"].rank(ascending=False, method="dense")

# Save master CSV
master.to_csv(MASTER_CSV, index=False)

print(f"[OK] Wrote consolidated workbook: {MASTER_XLSX}")
print(f"[OK] Wrote master CSV:         {MASTER_CSV}")


# OUTPUTS 

# lanes_summary.csv → Overview of all lanes.

# lanes_rank_by_avg_cost_per_mile.csv → Most & least expensive lanes.

# lanes_rank_by_avg_days_to_ship.csv → Slowest & fastest lanes.

# direct_pos_market_comparison.csv → Compare your cost vs. market.

# mill_summary.csv → Compare mill performance & shipping cost.


# JOINED OUTPUTS

# Freight_Summary
# master_lanes_with_market