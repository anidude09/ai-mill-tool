#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Nov 16 19:52:08 2025

@author: nitaishah
"""

# clean_al_for_g3g4.py
import re
import os
import pandas as pd
import numpy as np

# ================== EDIT THESE ==================
AL_XLSX = r"/Users/nitaishah/Desktop/STAT-683/FINAL_PROJECT/output_sheets_original_data/AL Data.xlsx"  
OUT_CSV = r"./AL_clean_filtered_g3g4.csv"
PREFERRED_DATE_ORDER = ["CallReadyDate", "DeliveredDate", "TransactionDate"]
KEEP_REGIONS = {"west", "central", "east"}  # case-insensitive
# ===============================================

def read_first_sheet(path):
    # robust read: take first sheet
    return pd.read_excel(path)

def normalize_cols(df):
    out = df.copy()
    out.columns = [c.strip().replace("\n"," ").strip() for c in out.columns]
    return out

def pick(df, options, required=True):
    for opt in options:
        for c in df.columns:
            if opt.lower() == c.lower():
                return c
    if required:
        raise KeyError(f"Required column not found among options: {options}.\nAvailable: {list(df.columns)}")
    return None

def extract_dimension(s: str):
    if not isinstance(s, str): return pd.NA
    m = re.search(r'(\d+)\s*[-xX]\s*(\d+)', s)
    if not m: return pd.NA
    return f"{int(m.group(1))}x{int(m.group(2))}".lower()

def extract_length_after_dimension(s: str, min_ft=6, max_ft=24):
    if not isinstance(s, str): return pd.NA
    md = re.search(r'(\d+)\s*[-xX]\s*(\d+)', s)
    if not md: return pd.NA
    start = md.end()
    m = re.search(r'(\d{1,2})\s*(?:ft|foot|feet|\'|")?', s[start:], flags=re.IGNORECASE)
    if not m: return pd.NA
    v = int(m.group(1))
    return v if (min_ft <= v <= max_ft) else pd.NA

def extract_grade_from_item(s: str):
    if not isinstance(s, str): return pd.NA
    m = re.search(r'#\s*([0-9]+)', s)
    return int(m.group(1)) if m else pd.NA

def choose_date(df, pref_list):
    for nm in pref_list:
        if nm in df.columns:
            return nm
        # case-insensitive fallback
        for c in df.columns:
            if c.lower() == nm.lower():
                return c
    # fallback: any column that contains "date"
    for c in df.columns:
        if "date" in c.lower():
            return c
    raise KeyError("No usable date column found.")

def main():
    raw = read_first_sheet(AL_XLSX)
    df = normalize_cols(raw)

    # Map likely columns (case-insensitive exact)
    # Try strict names first, else flexible find
    candidates = list(df.columns)

    def find_exact(name):
        for c in candidates:
            if c.lower() == name.lower():
                return c
        return None

    col_region = find_exact("MillRegion") or find_exact("Region")
    col_mill = find_exact("Mill")
    col_item = find_exact("ItemDescription") or find_exact("Item Desc") or find_exact("Item")
    col_price = (find_exact("Delivered Cost/MBF") or find_exact("DeliveredCost/MBF")
                 or find_exact("DeliveredCostPerMBF") or find_exact("DeliveredCostMBF")
                 or find_exact("Delivered Cost per MBF"))
    if not all([col_region, col_mill, col_item, col_price]):
        raise ValueError("Missing one of required columns: Region/Mill/ItemDescription/Delivered Cost/MBF")

    date_col_name = choose_date(df, PREFERRED_DATE_ORDER)

    # Basic fields
    out = pd.DataFrame({
        "region": df[col_region].astype(str).str.strip(),
        "mill": df[col_mill].astype(str).str.strip(),
        "item_description": df[col_item].astype(str),
        "date": pd.to_datetime(df[date_col_name], errors="coerce"),
        "delivered_cost_per_mbf": pd.to_numeric(df[col_price], errors="coerce")
    })

    # Parse dimension/length/grade from item_description
    out["dimension"] = out["item_description"].apply(extract_dimension)
    out["length_ft"] = out["item_description"].apply(extract_length_after_dimension)
    # Grade may exist in ItemDescription; but we only want 3 & 4
    out["grade"] = out["item_description"].apply(extract_grade_from_item)

    # Region filter (if regions exist)
    out = out[out["region"].str.lower().isin(KEEP_REGIONS)]

    # Keep only grades 3 & 4
    out["grade"] = pd.to_numeric(out["grade"], errors="coerce").astype("Int64")
    out = out[out["grade"].isin([3, 4])]

    # Drop rows with critical nulls
    out = out.dropna(subset=["date", "delivered_cost_per_mbf", "dimension"])

    # Length may be unknown; keep it — matcher will still use key (region, dimension, grade)
    os.makedirs(os.path.dirname(OUT_CSV) or ".", exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    print("Saved:", OUT_CSV, "| Rows:", len(out))
    print(out.head(10))

if __name__ == "__main__":
    main()
