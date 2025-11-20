#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Nov 16 20:04:44 2025

@author: nitaishah
"""

# final_match_data_g3g4.py
import os
import re
import pandas as pd
import numpy as np

# ================== EDIT THESE ==================
AL_CSV = r"/Users/nitaishah/Desktop/STAT-683/FINAL_PROJECT/KP1/Grade_3_4/AL_clean_filtered_g3g4.csv"
RL_LONG_CSV = r"/Users/nitaishah/Desktop/STAT-683/FINAL_PROJECT/KP1/Grade_3_4/RL_long_g3g4_equal_lengths.csv"
OUT_CSV = r"./matched_fact_g3g4.csv"
ASOF_TOLERANCE_DAYS = 14
# Optional: if AL length is missing, you can choose a fallback (e.g., use 16 ft)
FALLBACK_LENGTH_IF_MISSING = None  # set to an int like 16 or leave None to require length
# ===============================================

def normalize_cols(df):
    out = df.copy()
    out.columns = [c.strip().replace("\n"," ").strip() for c in out.columns]
    return out

def main():
    al = pd.read_csv(AL_CSV)
    rl = pd.read_csv(RL_LONG_CSV)

    al = normalize_cols(al)
    rl = normalize_cols(rl)

    # Standardize types
    al["region"] = al["region"].astype(str).str.strip().str.lower()
    rl["region"] = rl["region"].astype(str).str.strip().str.lower()

    al["dimension"] = al["dimension"].astype(str).str.lower().str.strip()
    rl["dimension"] = rl["dimension"].astype(str).str.lower().str.strip()

    al["grade"] = pd.to_numeric(al["grade"], errors="coerce").astype("Int64")
    rl["grade"] = pd.to_numeric(rl["grade"], errors="coerce").astype("Int64")

    al["length_ft"] = pd.to_numeric(al["length_ft"], errors="coerce").astype("Int64")
    rl["length_ft"] = pd.to_numeric(rl["length_ft"], errors="coerce").astype("Int64")

    al["date"] = pd.to_datetime(al["date"], errors="coerce")
    rl["transaction_date"] = pd.to_datetime(rl["transaction_date"], errors="coerce")

    al["delivered_cost_per_mbf"] = pd.to_numeric(al["delivered_cost_per_mbf"], errors="coerce")
    rl["rl_price_per_mbf"] = pd.to_numeric(rl["rl_price_per_mbf"], errors="coerce")

    # Optional: fallback length if AL lacks length
    if FALLBACK_LENGTH_IF_MISSING is not None:
        al.loc[al["length_ft"].isna(), "length_ft"] = FALLBACK_LENGTH_IF_MISSING

    # Build supported key set from RL
    rl_keys = rl[["region","dimension","grade","length_ft"]].drop_duplicates()

    # Sort for asof
    rl_sorted = rl.sort_values(["region","dimension","grade","length_ft","transaction_date"])
    al_sorted = al.sort_values(["region","dimension","grade","length_ft","date"])

    tol = pd.Timedelta(days=ASOF_TOLERANCE_DAYS)
    parts = []

    for key, grp in al_sorted.groupby(["region","dimension","grade","length_ft"], dropna=False):
        r, d, g, L = key

        # Determine whether RL has this series
        has_series = not rl_keys[
            (rl_keys["region"]==r) &
            (rl_keys["dimension"]==d) &
            (rl_keys["grade"]==g) &
            (rl_keys["length_ft"]==L)
        ].empty

        rl_grp = rl_sorted[
            (rl_sorted["region"]==r) &
            (rl_sorted["dimension"]==d) &
            (rl_sorted["grade"]==g) &
            (rl_sorted["length_ft"]==L)
        ][["transaction_date","rl_price_per_mbf"]].sort_values("transaction_date")

        if not has_series or rl_grp.empty:
            tmp = grp.copy()
            tmp["rl_date"] = pd.NaT
            tmp["rl_price_per_mbf"] = np.nan
            tmp["days_to_rl_quote"] = np.nan
            tmp["match_flag"] = "no_series"
            parts.append(tmp)
            continue

        merged = pd.merge_asof(
            grp.sort_values("date"),
            rl_grp,
            left_on="date",
            right_on="transaction_date",
            direction="backward",
            tolerance=tol
        )
        merged = merged.rename(columns={"transaction_date":"rl_date"})
        merged["days_to_rl_quote"] = (merged["date"] - merged["rl_date"]).dt.days
        merged["match_flag"] = np.where(merged["rl_date"].isna(), "no_date_within_tol", "ok")
        parts.append(merged)

    matched = pd.concat(parts, ignore_index=True)

    # Diagnostics: why no_series?
    miss = matched[matched["match_flag"]=="no_series"].copy()
    if not miss.empty:
        S_region = set(rl["region"].unique())
        S_region_dim = set(zip(rl["region"], rl["dimension"]))
        S_region_dim_grade = set(zip(rl["region"], rl["dimension"], rl["grade"]))
        S_region_dim_len = set(zip(rl["region"], rl["dimension"], rl["length_ft"]))
        S_full = set(zip(rl["region"], rl["dimension"], rl["grade"], rl["length_ft"]))

        def label_reason(row):
            t_reg = row["region"]
            t_dim = row["dimension"]
            t_g = row["grade"]
            t_L = row["length_ft"]
            if t_reg not in S_region: return "region_not_in_RL"
            if (t_reg, t_dim) not in S_region_dim: return "dimension_not_in_region"
            if (t_reg, t_dim, t_g) not in S_region_dim_grade: return "grade_not_in_region_dimension"
            if (t_reg, t_dim, t_L) not in S_region_dim_len: return "length_not_in_region_dimension"
            if (t_reg, t_dim, t_g, t_L) not in S_full: return "exact_combo_unpublished"
            return "should_not_happen"

        miss["reason"] = miss.apply(label_reason, axis=1)
        matched = matched.merge(
            miss[["region","dimension","grade","length_ft","date","reason"]],
            on=["region","dimension","grade","length_ft","date"],
            how="left"
        )

    # Metrics
    matched["rl_price_per_mbf"] = pd.to_numeric(matched["rl_price_per_mbf"], errors="coerce")
    matched["basis_abs"] = matched["delivered_cost_per_mbf"] - matched["rl_price_per_mbf"]
    matched["item_description_key"] = matched["dimension"].astype(str) + " #" + matched["grade"].astype(str)

    cols = [
        "region","mill","item_description","dimension","length_ft","grade",
        "date","delivered_cost_per_mbf",
        "rl_date","rl_price_per_mbf","days_to_rl_quote","match_flag","reason",
        "basis_abs","item_description_key"
    ]
    cols = [c for c in cols if c in matched.columns]
    matched = matched[cols].sort_values(["region","mill","dimension","grade","length_ft","date"])

    os.makedirs(os.path.dirname(OUT_CSV) or ".", exist_ok=True)
    matched.to_csv(OUT_CSV, index=False)
    print("Saved:", OUT_CSV, "| Rows:", len(matched))
    print(matched.head(10))

if __name__ == "__main__":
    main()
