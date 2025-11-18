#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov  3 22:32:12 2025

@author: nitaishah
"""

import re
import os
import pandas as pd

# ====== EDIT THESE ======
al_path = r"/Users/nitaishah/Desktop/STAT-683/FINAL_PROJECT/output_sheets_original_data/AL Data.xlsx"     # your AL dataset (the one with Mill columns)
out_csv = r"./AL_clean_filtered.csv"
# ========================

# Read
df = pd.read_excel(al_path)

# Normalize column names for easy matching
orig_cols = df.columns
df.columns = [c.strip().lower().replace(' ', '').replace('\n','') for c in df.columns]

# Helper to fetch a column by “contains” pattern (case-insensitive, normalized)
def pick(col_like_options, required=True):
    for opt in col_like_options:
        for c in df.columns:
            if opt.lower() in c.lower():
                return c
    if required:
        raise KeyError(f"Required column not found among: {col_like_options}\nAvailable: {list(df.columns)}")
    return None

# Map needed columns (adjust if your headers differ slightly)
col_region   = pick(["millregion","region"])
col_mill     = pick(["mill"])
col_item     = pick(["itemdescription","itemdesc"])
col_date     = pick(["callreadydate","delivereddate","transactiondate"])   # prefer CallReadyDate if present
col_price    = pick(["deliveredcost/mbf","deliveredcostpermbf","deliveredcostmbf"])

# Filter Region ∈ {West, Central, East}
keep_regions = {"west","central","east"}
df = df[df[col_region].str.strip().str.lower().isin(keep_regions)].copy()

# Parse fields from ItemDescription
item_series = df[col_item].astype(str)

# 1) Dimension: capture things like "2X4", "2-8", "2 x 10"
#    Normalize to "2x4", "2x8", etc.
dim_match = item_series.str.extract(r'(\d+)\s*[-xX]\s*(\d+)', expand=True)
df["dimension"] = dim_match.apply(
    lambda r: f"{int(r[0])}x{int(r[1])}" if pd.notna(r[0]) and pd.notna(r[1]) else pd.NA,
    axis=1
)

# 2) Length (feet): often appears immediately after the dimension, e.g. "2X4-8 #3"
#    Strategy: find the FIRST number that follows the dimension match.
def extract_length(s):
    if not isinstance(s, str):
        return pd.NA
    m_dim = re.search(r'(\d+)\s*[-xX]\s*(\d+)', s)
    if not m_dim:
        return pd.NA
    # start searching after the dimension match
    start = m_dim.end()
    # look for a 1-2 digit number plausibly representing feet (6–24, adjust if needed)
    m_len = re.search(r'(\d{1,2})\s*(?:ft|foot|feet|\'|")?', s[start:], flags=re.IGNORECASE)
    if not m_len:
        return pd.NA
    val = int(m_len.group(1))
    if 6 <= val <= 24:
        return val
    return pd.NA

df["length_ft"] = item_series.apply(extract_length)

# 3) Grade: capture "#1", "#2", "#3" etc., keep only 1 or 2
grade_match = item_series.str.extract(r'#\s*(\d+)', expand=True)[0]
df["grade"] = pd.to_numeric(grade_match, errors="coerce").astype("Int64")
df = df[df["grade"].isin([1, 2])].copy()

# Dates & price
df["date"] = pd.to_datetime(df[col_date], errors="coerce")
df["delivered_cost_per_mbf"] = pd.to_numeric(df[col_price], errors="coerce")

# Final tidy selection
out_cols = [
    col_region, col_mill, col_item, "dimension", "length_ft", "grade", "date", "delivered_cost_per_mbf"
]
# Keep only columns that exist
out_cols = [c for c in out_cols if c in df.columns or c in ["dimension","length_ft","grade","date","delivered_cost_per_mbf"]]
clean = df[out_cols].rename(columns={
    col_region: "region",
    col_mill: "mill",
    col_item: "item_description"
})

# Optional: drop rows missing any of the critical parsed fields
clean = clean.dropna(subset=["dimension","length_ft","grade","date","delivered_cost_per_mbf"])

# Save
os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
clean.to_csv(out_csv, index=False)

print("Saved:", out_csv)
print("Rows:", len(clean))
print("Region counts:\n", clean["region"].value_counts())
print("Sample:\n", clean.head(10))
