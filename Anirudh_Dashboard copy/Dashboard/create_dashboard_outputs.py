#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov 17 09:43:21 2025

@author: nitaishah
"""

# make_dashboard_inputs.py
import os, re
import pandas as pd
import numpy as np

# ================== CONFIG (edit paths) ==================
AL_XLSX = r"/Users/nitaishah/Desktop/STAT-683/FINAL_PROJECT/output_sheets_original_data/AL Data.xlsx"
# Use whichever matched file(s) you produced; you can point to one or concatenate both.
MATCHED_FILES = [
    "/Users/nitaishah/Desktop/STAT-683/FINAL_PROJECT/KP1/Grade_3_4/matched_fact_g3g4.csv",   # from the G3&4 pipeline you ran
    "/Users/nitaishah/Desktop/STAT-683/FINAL_PROJECT/KP1/matched_fact.csv"
]
OUT_DIR = "./dash_inputs"
PLANT_BLR_ADDR = "600 liberty dr."
PLANT_TLR_ADDR = "777 clow road"
DATE_FROM = "2024-01-01"   # optional window for tiles/summaries
DATE_TO   = "2025-12-31"
# =========================================================

os.makedirs(OUT_DIR, exist_ok=True)

# ---------- 1) Load AL (raw) so we keep all metadata ----------
al = pd.read_excel(AL_XLSX)
al.columns = [c.strip().replace("\n"," ").strip() for c in al.columns]

def pick(df, names):
    # exact (case-insensitive), then contains
    for want in names:
        for c in df.columns:
            if c.lower() == want.lower(): return c
    for want in names:
        for c in df.columns:
            if want.lower() in c.lower(): return c
    return None

col_vendorcid = pick(al, ["VendorCID"])
col_mill      = pick(al, ["Mill"])
col_region    = pick(al, ["MillRegion","Region"])
col_po_type   = pick(al, ["poType","PO Type"])
col_buyer     = pick(al, ["BuyerName","Buyer"])
col_salesman  = pick(al, ["Salesman"])
col_itemdesc  = pick(al, ["ItemDescription","Item Desc","Item"])
col_species   = pick(al, ["Species"])
col_grade     = pick(al, ["Grade"])
col_convbf    = pick(al, ["ConvBF","BF","BoardFeet"])
col_purchase_uom = pick(al, ["PurchaseUOM","UOM"])
col_price_del = pick(al, ["Delivered Cost/MBF","DeliveredCost/MBF","DeliveredCostPerMBF","Delivered Cost per MBF"])
col_sale_price = pick(al, ["SalePrice","SalesPrice"])
col_sale_uom   = pick(al, ["SaleUOM","SalesUOM"])
col_callready  = pick(al, ["CallReadyDate"])
col_pickup     = pick(al, ["PickUpDate","PickupDate","ShipDate"])
col_delivered  = pick(al, ["DeliveredDate","DeliveryDate"])

# Origins & destinations
col_o_city = pick(al, ["OriginCity"])
col_o_st   = pick(al, ["OriginST","OriginState"])
col_o_zip  = pick(al, ["OriginZip"])
col_d_name = pick(al, ["CustomerName"])
col_d_addr1= pick(al, ["DestAddress1"])
col_d_addr2= pick(al, ["DestAddress2"])
col_d_city = pick(al, ["DestCity"])
col_d_st   = pick(al, ["DestST","DestState"])
col_d_zip  = pick(al, ["DestZip"])

# ---------- 2) Load matched RL facts and union ----------
mats = []
for path in MATCHED_FILES:
    if path and os.path.exists(path):
        dfm = pd.read_csv(path)
        dfm.columns = [c.strip().lower() for c in dfm.columns]
        # standardize common types
        if "rl_date" in dfm.columns:
            dfm["rl_date"] = pd.to_datetime(dfm["rl_date"], errors="coerce")
        if "date" in dfm.columns:
            dfm["date"] = pd.to_datetime(dfm["date"], errors="coerce")
        if "grade" in dfm.columns:
            dfm["grade"] = pd.to_numeric(dfm["grade"], errors="coerce").astype("Int64")
        # ---- OPTIONAL COLS TOLERANCE ----
        for opt_col, default in [
            ("assumption_equal_length", False),
            ("match_flag", pd.NA),
            ("rl_date", pd.NaT),
            ("days_to_rl_quote", pd.NA),
        ]:
            if opt_col not in dfm.columns:
                if opt_col == "rl_date":
                    dfm[opt_col] = pd.to_datetime(pd.NaT)
                else:
                    dfm[opt_col] = default
        mats.append(dfm)

if not mats:
    raise FileNotFoundError("No matched_fact* CSVs found in MATCHED_FILES.")

matched = pd.concat(mats, ignore_index=True)

# Keep RL reference series for BI tooltips
if "region" not in matched.columns and "mill_region" in matched.columns:
    matched = matched.rename(columns={"mill_region":"region"})

rl_series_cols = [c for c in ["region","dimension","grade","length_ft","rl_date","rl_price_per_mbf"] if c in matched.columns]
rl_series = (matched[rl_series_cols]
             .dropna(subset=[c for c in ["rl_date"] if c in rl_series_cols])
             .drop_duplicates()
             .sort_values([c for c in ["region","dimension","grade","length_ft","rl_date"] if c in rl_series_cols]))
rl_series.to_csv(os.path.join(OUT_DIR, "rl_reference_series.csv"), index=False)

# ---------- 3) Build FACT table from AL + join to matched ----------
def parse_dimension(s):
    if not isinstance(s, str): return pd.NA
    m = re.search(r'(\d+)\s*[-xX]\s*(\d+)', s)
    if not m: return pd.NA
    return f"{int(m.group(1))}x{int(m.group(2))}".lower()

def parse_length_after_dim(s):
    if not isinstance(s, str): return pd.NA
    md = re.search(r'(\d+)\s*[-xX]\s*(\d+)', s)
    if not md: return pd.NA
    m = re.search(r'(\d{1,2})\s*(?:ft|foot|feet|\'|")?', s[md.end():], flags=re.IGNORECASE)
    if not m: return pd.NA
    v = int(m.group(1))
    return v if 6 <= v <= 24 else pd.NA

al_std = pd.DataFrame({
    "vendor_cid": al[col_vendorcid] if col_vendorcid else pd.NA,
    "mill":       al[col_mill] if col_mill else pd.NA,
    "mill_region":al[col_region] if col_region else pd.NA,
    "po_type":    al[col_po_type] if col_po_type else pd.NA,
    "buyer_name": al[col_buyer] if col_buyer else pd.NA,
    "salesman":   al[col_salesman] if col_salesman else pd.NA,
    "item_description": al[col_itemdesc] if col_itemdesc else pd.NA,
    "species":    al[col_species] if col_species else pd.NA,
    "grade":      al[col_grade] if col_grade else pd.NA,
    "convbf":     pd.to_numeric(al[col_convbf], errors="coerce") if col_convbf else np.nan,
    "purchase_uom": al[col_purchase_uom] if col_purchase_uom else pd.NA,
    "delivered_cost_per_mbf": pd.to_numeric(al[col_price_del], errors="coerce") if col_price_del else np.nan,
    "sale_price_per_mbf": pd.to_numeric(al[col_sale_price], errors="coerce") if col_sale_price else np.nan,
    "sale_uom":     al[col_sale_uom] if col_sale_uom else pd.NA,
    "call_ready_date": pd.to_datetime(al[col_callready], errors="coerce") if col_callready else pd.NaT,
    "ship_date":      pd.to_datetime(al[col_pickup], errors="coerce") if col_pickup else pd.NaT,
    "delivered_date": pd.to_datetime(al[col_delivered], errors="coerce") if col_delivered else pd.NaT,
    "origin_city": al[col_o_city] if col_o_city else pd.NA,
    "origin_st":   al[col_o_st] if col_o_st else pd.NA,
    "origin_zip":  al[col_o_zip] if col_o_zip else pd.NA,
    "dest_name":   al[col_d_name] if col_d_name else pd.NA,
    "dest_address1": al[col_d_addr1] if col_d_addr1 else pd.NA,
    "dest_address2": al[col_d_addr2] if col_d_addr2 else pd.NA,
    "dest_city":   al[col_d_city] if col_d_city else pd.NA,
    "dest_st":     al[col_d_st] if col_d_st else pd.NA,
    "dest_zip":    al[col_d_zip] if col_d_zip else pd.NA,
})
al_std["dimension"] = al_std["item_description"].astype(str).apply(parse_dimension)
al_std["length_ft"] = al_std["item_description"].astype(str).apply(parse_length_after_dim)
al_std["grade"] = pd.to_numeric(al_std["grade"], errors="coerce").astype("Int64")
al_std["ship_date"] = np.where(al_std["ship_date"].notna(), al_std["ship_date"], al_std["delivered_date"])
al_std["days_ready_to_ship"] = (al_std["ship_date"] - al_std["call_ready_date"]).dt.days

def tag_dest(row):
    addr = (str(row.get("dest_address1","")) + " " + str(row.get("dest_address2",""))).lower()
    if PLANT_BLR_ADDR in addr: return "BLR"
    if PLANT_TLR_ADDR in addr: return "TLR"
    return "Customer"
al_std["dest_location_type"] = al_std.apply(tag_dest, axis=1)
al_std["mill_region"] = al_std["mill_region"].astype(str).str.strip().str.lower()

# align key names to matched
if "region" in matched.columns and "mill_region" not in matched.columns:
    matched = matched.rename(columns={"region":"mill_region"})

# ---- OPTIONAL COLS TOLERANCE (already added above; kept columns may vary) ----
wanted = [
    "mill_region","dimension","grade","length_ft","date",
    "rl_price_per_mbf","match_flag","rl_date","days_to_rl_quote","assumption_equal_length"
]
take = [c for c in wanted if c in matched.columns]
right = matched[take].rename(columns={"date": "al_match_date"})

# Merge by exact key + AL ship_date (which is the operational “ship” event)
joined = pd.merge(
    al_std,
    right,
    left_on=["mill_region","dimension","grade","length_ft","ship_date"],
    right_on=["mill_region","dimension","grade","length_ft","al_match_date"],
    how="left"
)

# Metrics
joined["delivered_total_usd"] = (joined["delivered_cost_per_mbf"] * (joined["convbf"]/1000.0)).where(joined["convbf"].notna())
joined["sale_total_usd"] = (joined["sale_price_per_mbf"] * (joined["convbf"]/1000.0)).where(joined["convbf"].notna()) if "sale_price_per_mbf" in joined else np.nan
joined["gross_margin_per_mbf"] = (joined["sale_price_per_mbf"] - joined["delivered_cost_per_mbf"]) if "sale_price_per_mbf" in joined else np.nan
joined["index_relative_margin_per_mbf"] = joined["rl_price_per_mbf"] - joined["delivered_cost_per_mbf"]

# Save FACT table
fact_cols = [
    "vendor_cid","mill","mill_region","po_type","buyer_name","salesman",
    "origin_city","origin_st","origin_zip","dest_name","dest_address1","dest_address2","dest_city","dest_st","dest_zip",
    "dest_location_type",
    "item_description","species","dimension","grade","length_ft","convbf","purchase_uom",
    "call_ready_date","ship_date","delivered_date","days_ready_to_ship",
    "delivered_cost_per_mbf","sale_price_per_mbf","rl_price_per_mbf",
    "delivered_total_usd","sale_total_usd","gross_margin_per_mbf","index_relative_margin_per_mbf",
    "match_flag","rl_date","days_to_rl_quote","assumption_equal_length"
]
fact_cols = [c for c in fact_cols if c in joined.columns]  # tolerance on output schema
fact = joined[fact_cols]
fact.to_csv(os.path.join(OUT_DIR, "fact_contract_loads.csv"), index=False)

# ---------- 4) Summary tiles for date window ----------
mask = pd.Series(True, index=fact.index)
if DATE_FROM: mask &= fact["ship_date"] >= pd.to_datetime(DATE_FROM)
if DATE_TO:   mask &= fact["ship_date"] <= pd.to_datetime(DATE_TO)
sub = fact.loc[mask].copy()

tiles = pd.DataFrame({
    "total_volume_bf": [sub["convbf"].sum(skipna=True) if "convbf" in sub.columns else np.nan],
    "total_delivered_usd": [sub["delivered_total_usd"].sum(skipna=True) if "delivered_total_usd" in sub.columns else np.nan],
    "avg_delivered_cost_per_mbf": [sub["delivered_cost_per_mbf"].mean(skipna=True)],
    "avg_days_ready_to_ship": [sub["days_ready_to_ship"].mean(skipna=True)],
    "gross_margin_per_mbf_avg": [sub["gross_margin_per_mbf"].mean(skipna=True) if "gross_margin_per_mbf" in sub.columns else np.nan],
    "index_relative_margin_per_mbf_avg": [sub["index_relative_margin_per_mbf"].mean(skipna=True)],
})
tiles.to_csv(os.path.join(OUT_DIR, "summary_tiles.csv"), index=False)

# ---------- 5) Route summary (mill -> destination) ----------
group_cols = ["mill","vendor_cid","mill_region","dest_location_type","dest_city","dest_st","dimension","grade","length_ft"]
for c in group_cols:
    if c not in sub.columns:
        sub[c] = pd.NA

route_grp = (sub
    .groupby(group_cols, dropna=False)
    .agg(
        volume_bf=("convbf","sum") if "convbf" in sub.columns else ("dimension","size"),
        delivered_cost_per_mbf_avg=("delivered_cost_per_mbf","mean"),
        rl_price_per_mbf_avg=("rl_price_per_mbf","mean"),
        index_relative_margin_per_mbf_avg=("index_relative_margin_per_mbf","mean")
    )
    .reset_index()
)
route_grp.to_csv(os.path.join(OUT_DIR, "route_summary.csv"), index=False)

# ---------- 6) Mill rankings (lowest delivered $/MBF) ----------
mill_grp_cols = ["vendor_cid","mill","mill_region"]
for c in mill_grp_cols:
    if c not in sub.columns:
        sub[c] = pd.NA

mill_rank = (sub
    .groupby(mill_grp_cols, dropna=False)
    .agg(
        volume_bf=("convbf","sum") if "convbf" in sub.columns else ("dimension","size"),
        delivered_cost_per_mbf_avg=("delivered_cost_per_mbf","mean"),
        rl_price_per_mbf_avg=("rl_price_per_mbf","mean"),
        index_relative_margin_per_mbf_avg=("index_relative_margin_per_mbf","mean")
    )
    .reset_index()
    .sort_values(["delivered_cost_per_mbf_avg","rl_price_per_mbf_avg"], ascending=[True, True])
)
mill_rank.to_csv(os.path.join(OUT_DIR, "mill_rankings.csv"), index=False)

print("Wrote:")
for f in ["fact_contract_loads.csv","rl_reference_series.csv","summary_tiles.csv","route_summary.csv","mill_rankings.csv"]:
    print(" -", os.path.join(OUT_DIR, f))
