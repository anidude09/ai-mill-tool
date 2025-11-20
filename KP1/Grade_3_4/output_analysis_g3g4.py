#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Nov 16 20:05:29 2025

@author: nitaishah
"""

# output_analysis_g3g4.py
import os
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ================== EDIT THESE ==================
MATCHED_CSV = r"/Users/nitaishah/Desktop/STAT-683/FINAL_PROJECT/KP1/Grade_3_4/matched_fact_g3g4.csv"
OUTPUT_DIR  = r"./mill_eda_outputs_g3g4"
CHARTS_DIR  = os.path.join(OUTPUT_DIR, "charts_by_mill")
START_DATE  = "2024-01-01"
END_DATE    = "2025-12-31"
ROLL_W      = 4  # rolling window for charts
# ===============================================

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CHARTS_DIR, exist_ok=True)

def main():
    df = pd.read_csv(MATCHED_CSV)
    df.columns = [c.strip().lower() for c in df.columns]

    # Column validity stats
    total_cols = len(df.columns)
    valid_cols_mask = df.notna().any(axis=0)
    num_valid_cols = int(valid_cols_mask.sum())
    invalid_cols = df.columns[~valid_cols_mask].tolist()
    print("=== COLUMN SUMMARY ===")
    print("Total columns:", total_cols)
    print("Valid columns (any non-null):", num_valid_cols)
    print("Columns with all nulls:", invalid_cols)

    # Required columns
    need = {"mill","region","date","dimension","length_ft","grade","delivered_cost_per_mbf","rl_price_per_mbf"}
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Types
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["delivered_cost_per_mbf"] = pd.to_numeric(df["delivered_cost_per_mbf"], errors="coerce")
    df["rl_price_per_mbf"] = pd.to_numeric(df["rl_price_per_mbf"], errors="coerce")
    df["length_ft"] = pd.to_numeric(df["length_ft"], errors="coerce").astype("Int64")
    df["grade"] = pd.to_numeric(df["grade"], errors="coerce").astype("Int64")

    # Margin: index-relative (positive = bought below index)
    df["index_relative_margin_per_mbf"] = df["rl_price_per_mbf"] - df["delivered_cost_per_mbf"]

    # Product key
    df["product"] = (
        df["dimension"].astype(str).str.lower().str.strip()
        + " | #" + df["grade"].astype("Int64").astype(str)
        + " | " + df["length_ft"].astype("Int64").astype(str) + "ft"
    )

    # Window
    mask = (df["date"] >= pd.to_datetime(START_DATE)) & (df["date"] <= pd.to_datetime(END_DATE))
    dfw = df.loc[mask].copy()

    # Volume detection
    vol_candidates = ["bf","convbf","mbf","quantity","qty","boardfeet"]
    vol_col = next((c for c in vol_candidates if c in dfw.columns), None)

    def mill_summary(g: pd.DataFrame):
        total_margin = g["index_relative_margin_per_mbf"].sum()
        avg_margin   = g["index_relative_margin_per_mbf"].mean()
        med_margin   = g["index_relative_margin_per_mbf"].median()
        n_rows       = len(g)
        n_ok         = (g.get("match_flag","").astype(str) == "ok").sum()

        # top seller
        if vol_col:
            s = g.groupby("product", as_index=False)[vol_col].sum().sort_values(vol_col, ascending=False)
            top_seller = s.iloc[0]["product"] if len(s) else None
            top_seller_vol = s.iloc[0][vol_col] if len(s) else np.nan
        else:
            cnt = g["product"].value_counts()
            top_seller = cnt.index[0] if len(cnt) else None
            top_seller_vol = int(cnt.iloc[0]) if len(cnt) else 0

        pm = g.groupby("product", as_index=False)["index_relative_margin_per_mbf"].sum()
        if not pm.empty:
            best_row = pm.sort_values("index_relative_margin_per_mbf", ascending=False).iloc[0]
            worst_row = pm.sort_values("index_relative_margin_per_mbf", ascending=True).iloc[0]
            best_prod, best_val = best_row["product"], float(best_row["index_relative_margin_per_mbf"])
            worst_prod, worst_val = worst_row["product"], float(worst_row["index_relative_margin_per_mbf"])
        else:
            best_prod = best_val = worst_prod = worst_val = None

        profitable = total_margin > 0
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

    out_summary = os.path.join(OUTPUT_DIR, "mill_profitability_summary_2024_2025_g3g4.csv")
    mill_sum.to_csv(out_summary, index=False)
    print("Saved:", out_summary)

    # Weekly trend charts
    dfw["year_week"] = dfw["date"].dt.to_period("W").apply(lambda p: p.start_time)
    for mill, g in dfw.groupby("mill"):
        g = g.sort_values("date").copy()
        agg = g.groupby("year_week", as_index=False).agg(
            avg_delivered=("delivered_cost_per_mbf","mean"),
            avg_rl=("rl_price_per_mbf","mean"),
            avg_margin=("index_relative_margin_per_mbf","mean"),
            n=("index_relative_margin_per_mbf","size")
        ).sort_values("year_week")

        agg["avg_delivered_roll"] = agg["avg_delivered"].rolling(ROLL_W, min_periods=1).mean()
        agg["avg_rl_roll"] = agg["avg_rl"].rolling(ROLL_W, min_periods=1).mean()
        agg["avg_margin_roll"] = agg["avg_margin"].rolling(ROLL_W, min_periods=1).mean()

        plt.figure(figsize=(10,6))
        plt.plot(agg["year_week"], agg["avg_delivered_roll"], label="Delivered ($/MBF)")
        plt.plot(agg["year_week"], agg["avg_rl_roll"], label="RL Index ($/MBF)")
        plt.plot(agg["year_week"], agg["avg_margin_roll"], label="Index-Relative Margin ($/MBF)")
        plt.title(f"{mill} — Weekly Trends (2024–2025, G3–G4)")
        plt.xlabel("Week")
        plt.ylabel("$ per MBF")
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        safe = re.sub(r'[^A-Za-z0-9_. -]+','_', mill).strip().replace(' ','_')[:120]
        out_png = os.path.join(CHARTS_DIR, f"{safe}_trend_2024_2025_g3g4.png")
        plt.savefig(out_png, dpi=150)
        plt.close()

    # Detail tables
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

    top_sellers_csv = os.path.join(OUTPUT_DIR, "top_selling_products_by_mill_g3g4.csv")
    prod_margin_csv = os.path.join(OUTPUT_DIR, "product_index_margin_by_mill_g3g4.csv")
    top_sellers.to_csv(top_sellers_csv, index=False)
    prod_margin.to_csv(prod_margin_csv, index=False)

    print("Saved:", top_sellers_csv)
    print("Saved:", prod_margin_csv)
    print("Charts folder:", CHARTS_DIR)

if __name__ == "__main__":
    main()
