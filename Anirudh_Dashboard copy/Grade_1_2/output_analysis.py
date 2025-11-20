#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov  3 23:30:15 2025

@author: nitaishah
"""

# === MILL EDA (keeps no_series) ==============================================
# What it does:
# - Loads matched_fact.csv (must include: mill, region, date, dimension, length_ft, grade,
#   delivered_cost_per_mbf, rl_price_per_mbf, match_flag)
# - Prints # of valid columns (non-null in at least one row)
# - Computes index-relative margin: RL - Delivered (positive = favorable vs index)
# - Builds per-mill profitability summary (2024–2025)
# - Finds top-selling product (by volume if BF/ConvBF present else by count)
# - Finds best/worst product by total margin (index-relative)
# - Exports CSVs and per-mill weekly trend charts (Delivered, RL, Margin)
# ============================================================================

import os
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ------------------ CONFIG ------------------
INPUT_CSV  = r"/Users/nitaishah/Desktop/STAT-683/FINAL_PROJECT/KP1/matched_fact.csv"          # <-- set to your file
OUTPUT_DIR = r"./mill_eda_outputs"
CHARTS_DIR = os.path.join(OUTPUT_DIR, "charts_by_mill")

START_DATE = "2024-01-01"
END_DATE   = "2025-12-31"
ROLL_W     = 4   # rolling window for smoother charts
# --------------------------------------------

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CHARTS_DIR, exist_ok=True)

# 1) Load & normalize columns
df = pd.read_csv(INPUT_CSV)
df.columns = [c.strip().lower() for c in df.columns]

# Valid columns count (any non-null)
valid_cols_mask = df.notna().any(axis=0)
valid_cols = df.columns[valid_cols_mask].tolist()
invalid_cols = df.columns[~valid_cols_mask].tolist()
print("=== COLUMN SUMMARY ===")
print("Total columns:", len(df.columns))
print("Valid columns (any non-null):", len(valid_cols))
print("Columns with all nulls:", invalid_cols)

# 2) Basic checks
req = {"mill","region","date","dimension","length_ft","grade","delivered_cost_per_mbf","rl_price_per_mbf"}
missing = [c for c in req if c not in df.columns]
if missing:
    raise ValueError(f"Missing required columns: {missing}")

# 3) Parse/convert
df["date"] = pd.to_datetime(df["date"], errors="coerce")
df["delivered_cost_per_mbf"] = pd.to_numeric(df["delivered_cost_per_mbf"], errors="coerce")
df["rl_price_per_mbf"] = pd.to_numeric(df["rl_price_per_mbf"], errors="coerce")
df["grade"] = pd.to_numeric(df["grade"], errors="coerce").astype("Int64")
df["length_ft"] = pd.to_numeric(df["length_ft"], errors="coerce").astype("Int64")

# Keep all rows (including no_series). Margin will be NaN where RL is missing.
df["index_relative_margin_per_mbf"] = df["rl_price_per_mbf"] - df["delivered_cost_per_mbf"]

# Product key
df["product"] = (
    df["dimension"].astype(str).str.lower().str.strip()
    + " | #" + df["grade"].astype("Int64").astype(str)
    + " | " + df["length_ft"].astype("Int64").astype(str) + "ft"
)

# Window filter (analysis period)
mask = (df["date"] >= pd.to_datetime(START_DATE)) & (df["date"] <= pd.to_datetime(END_DATE))
dfw = df.loc[mask].copy()

# Optional volume column detection
vol_candidates = ["bf","convbf","mbf","quantity","qty","boardfeet"]
vol_col = next((c for c in vol_candidates if c in dfw.columns), None)

# 4) Per-mill summary
def mill_summary(g: pd.DataFrame):
    # Sum/avg margins (index-relative). NaNs ignored by default in sum/mean.
    total_margin = g["index_relative_margin_per_mbf"].sum()
    avg_margin   = g["index_relative_margin_per_mbf"].mean()
    med_margin   = g["index_relative_margin_per_mbf"].median()
    n_rows       = len(g)
    n_ok         = (g.get("match_flag", "").astype(str) == "ok").sum()

    # Top-selling product (by volume if available else by count)
    if vol_col:
        pv = g.groupby("product", as_index=False)[vol_col].sum().sort_values(vol_col, ascending=False)
        top_seller = pv.iloc[0]["product"] if len(pv) else None
        top_seller_vol = pv.iloc[0][vol_col] if len(pv) else np.nan
    else:
        cnt = g["product"].value_counts()
        top_seller = cnt.index[0] if len(cnt) else None
        top_seller_vol = int(cnt.iloc[0]) if len(cnt) else 0

    # Best / worst products by total margin (index-relative)
    pm = g.groupby("product", as_index=False)["index_relative_margin_per_mbf"].sum()
    if not pm.empty:
        best_row  = pm.sort_values("index_relative_margin_per_mbf", ascending=False).iloc[0]
        worst_row = pm.sort_values("index_relative_margin_per_mbf", ascending=True).iloc[0]
        best_prod, best_val   = best_row["product"], float(best_row["index_relative_margin_per_mbf"])
        worst_prod, worst_val = worst_row["product"], float(worst_row["index_relative_margin_per_mbf"])
    else:
        best_prod = best_val = worst_prod = worst_val = None

    profitable = (total_margin > 0)  # positive total index-relative margin over window

    return pd.Series({
        "profitable_index_relative": profitable,
        "total_index_relative_margin": total_margin,
        "avg_index_relative_margin": avg_margin,
        "median_index_relative_margin": med_margin,
        "n_rows": n_rows,
        "n_ok_matches": n_ok,
        "top_selling_product": top_seller,
        "top_selling_volume_or_count": top_seller_vol,
        "best_product_by_index_margin": best_prod,
        "best_product_total_index_margin": best_val,
        "worst_product_by_index_margin": worst_prod,
        "worst_product_total_index_margin": worst_val,
    })

mill_sum = dfw.groupby("mill", as_index=False).apply(mill_summary)
mill_sum = mill_sum.sort_values(["profitable_index_relative","total_index_relative_margin"], ascending=[False,False])
mill_summary_csv = os.path.join(OUTPUT_DIR, "mill_profitability_summary_2024_2025.csv")
mill_sum.to_csv(mill_summary_csv, index=False)
print("Saved:", mill_summary_csv)

# 5) Per-mill trend charts (weekly, rolled)
dfw["year_week"] = dfw["date"].dt.to_period("W").apply(lambda p: p.start_time)

for mill, g in dfw.groupby("mill"):
    g = g.sort_values("date").copy()
    agg = g.groupby("year_week", as_index=False).agg(
        avg_delivered=("delivered_cost_per_mbf","mean"),
        avg_rl=("rl_price_per_mbf","mean"),
        avg_margin=("index_relative_margin_per_mbf","mean"),
        n=("index_relative_margin_per_mbf","size")
    ).sort_values("year_week")

    # Rolling smoothers
    agg["avg_delivered_roll"] = agg["avg_delivered"].rolling(ROLL_W, min_periods=1).mean()
    agg["avg_rl_roll"] = agg["avg_rl"].rolling(ROLL_W, min_periods=1).mean()
    agg["avg_margin_roll"] = agg["avg_margin"].rolling(ROLL_W, min_periods=1).mean()

    # Plot (matplotlib only; no seaborn)
    plt.figure(figsize=(10,6))
    plt.plot(agg["year_week"], agg["avg_delivered_roll"], label="Delivered ($/MBF)")
    plt.plot(agg["year_week"], agg["avg_rl_roll"],        label="RL Index ($/MBF)")
    plt.plot(agg["year_week"], agg["avg_margin_roll"],    label="Index-Relative Margin ($/MBF)")
    plt.title(f"{mill} — Weekly Trends (2024–2025)")
    plt.xlabel("Week")
    plt.ylabel("$ per MBF")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    safe = re.sub(r'[^A-Za-z0-9_. -]+','_', mill).strip().replace(' ', '_')[:120]
    out_png = os.path.join(CHARTS_DIR, f"{safe}_trend_2024_2025.png")
    plt.savefig(out_png, dpi=150)
    plt.close()

print("Charts saved to:", CHARTS_DIR)

# 6) Product detail tables (handy to inspect)
if vol_col:
    top_sellers = (dfw.groupby(["mill","product"], as_index=False)[vol_col]
                     .sum()
                     .sort_values(["mill", vol_col], ascending=[True, False]))
else:
    top_sellers = (dfw.groupby(["mill","product"], as_index=False)
                     .size()
                     .rename(columns={"size":"count"})
                     .sort_values(["mill","count"], ascending=[True, False]))

prod_margin = (dfw.groupby(["mill","product"], as_index=False)
                 .agg(total_index_relative_margin=("index_relative_margin_per_mbf","sum"),
                      avg_index_relative_margin=("index_relative_margin_per_mbf","mean"),
                      n=("index_relative_margin_per_mbf","size"))
                 .sort_values(["mill","total_index_relative_margin"], ascending=[True, True]))

top_sellers_csv = os.path.join(OUTPUT_DIR, "top_selling_products_by_mill.csv")
prod_margin_csv = os.path.join(OUTPUT_DIR, "product_index_margin_by_mill.csv")
top_sellers.to_csv(top_sellers_csv, index=False)
prod_margin.to_csv(prod_margin_csv, index=False)
print("Saved:", top_sellers_csv)
print("Saved:", prod_margin_csv)

# ================= END =================
