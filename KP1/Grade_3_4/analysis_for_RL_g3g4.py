#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Nov 16 19:59:36 2025

@author: nitaishah
"""

# analysis_for_RL_g3g4.py
import os
import re
import pandas as pd
import numpy as np

# ================== EDIT THESE ==================
RL_XLSX = r"/Users/nitaishah/Desktop/STAT-683/FINAL_PROJECT/KP1/output_sheets/Random Lengths (Grade 3&4).xlsx"
OUT_CSV = r"./RL_long_g3g4_equal_lengths.csv"
LENGTHS = [8, 10, 12, 14, 16, 18, 20]   # assumed same price across these
REGION_SET = {"west","central","east"}
# ===============================================

def normalize_cols(df):
    out = df.copy()
    out.columns = [c.strip().replace("\n"," ").strip() for c in out.columns]
    return out

def parse_dimension(item):
    if not isinstance(item, str): return pd.NA
    m = re.search(r'(\d+)\s*[-xX]\s*(\d+)', item)
    if not m: return pd.NA
    return f"{int(m.group(1))}x{int(m.group(2))}".lower()

def parse_grade_from_col(gr):
    # grade col is '#3' or '#4'
    if pd.isna(gr): return pd.NA
    s = str(gr)
    m = re.search(r'([0-9]+)', s)
    return int(m.group(1)) if m else pd.NA

def main():
    # Grade 3&4 file has header at row 2 frequently; try header=1; fallback header=0
    try:
        df0 = pd.read_excel(RL_XLSX, sheet_name=0, header=1)
    except Exception:
        df0 = pd.read_excel(RL_XLSX, sheet_name=0, header=0)

    df0 = df0.dropna(how="all")
    df0 = normalize_cols(df0)

    # Expected cols: Grade, ItemDescription, TransactionDate, West, Central, East
    # Find region columns present
    region_cols = [c for c in df0.columns if c.strip().lower() in REGION_SET]
    must = ["Grade","ItemDescription","TransactionDate"]
    for m in must:
        if m not in df0.columns:
            raise ValueError(f"Missing '{m}' in RL G3&4 input.")

    if not region_cols:
        raise ValueError("No region columns (West/Central/East) found in RL G3&4 input.")

    # Melt regions
    rl_reg = df0.melt(
        id_vars=["Grade","ItemDescription","TransactionDate"],
        value_vars=region_cols,
        var_name="region",
        value_name="rl_price_per_mbf"
    )

    rl_reg["region"] = rl_reg["region"].astype(str).str.strip().str.title()  # West/Central/East
    rl_reg["region"] = rl_reg["region"].str.lower()
    rl_reg["transaction_date"] = pd.to_datetime(rl_reg["TransactionDate"], errors="coerce")

    rl_reg["dimension"] = rl_reg["ItemDescription"].apply(parse_dimension)
    rl_reg["grade"] = rl_reg["Grade"].apply(parse_grade_from_col).astype("Int64")
    rl_reg = rl_reg.dropna(subset=["transaction_date", "dimension", "grade", "rl_price_per_mbf"])
    rl_reg = rl_reg[rl_reg["region"].isin(REGION_SET)]

    # Explode across lengths with same price
    rl_reg["key"] = 1
    lengths_df = pd.DataFrame({"length_ft": LENGTHS, "key": 1})
    rl_long = pd.merge(rl_reg, lengths_df, on="key").drop(columns=["key"])

    rl_long["assumption_equal_length"] = True
    rl_long["source_grade_group"] = "G3_4"

    out = rl_long[[
        "region",
        "ItemDescription",
        "transaction_date",
        "dimension",
        "grade",
        "length_ft",
        "rl_price_per_mbf",
        "assumption_equal_length",
        "source_grade_group"
    ]].rename(columns={"ItemDescription":"item_description"})

    out = out.sort_values(["region","dimension","grade","length_ft","transaction_date"])

    os.makedirs(os.path.dirname(OUT_CSV) or ".", exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    print("Saved:", OUT_CSV, "| Rows:", len(out))
    print(out.head(10))

if __name__ == "__main__":
    main()
