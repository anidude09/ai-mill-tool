#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov  3 23:02:09 2025

@author: nitaishah
"""

import pandas as pd
import numpy as np
import re
import os

# ================== EDIT THESE ==================
RL_CSV = r"/Users/nitaishah/Desktop/STAT-683/FINAL_PROJECT/KP1/output_sheets/Random Lengths (Grade 1&2).csv"        # your RL csv (wide by length)
AL_CSV = r"/Users/nitaishah/Desktop/STAT-683/FINAL_PROJECT/KP1/AL_clean_filtered.csv"     # your cleaned AL csv
OUT_CSV = r"./matched_fact.csv"
ASOF_TOLERANCE_DAYS = 14                       # max lookback window for RL match
# =================================================

# ---------- Helpers ----------
def normalize_cols(df):
    df = df.copy()
    df.columns = [c.strip().replace("\n"," ").strip() for c in df.columns]
    return df

def parse_dim_grade_from_item(item_series):
    # dimension: e.g., "2x4" or "2X4"
    dim = item_series.str.extract(r'(\d+\s*[xX]\s*\d+)')[0]
    dim = dim.str.replace(r'\s*', '', regex=True).str.lower()   # "2x4"
    # grade: "#1", "#2"
    grd = item_series.str.extract(r'#\s*([12])')[0]
    grd = pd.to_numeric(grd, errors="coerce").astype("Int64")
    return dim, grd

def melt_rl_lengths(df_rl):
    length_cols = [c for c in df_rl.columns if re.match(r'Length\d+Foot$', c, flags=re.IGNORECASE)]
    long = df_rl.melt(
        id_vars=["Region","ItemDescription","TransactionDate"],
        value_vars=length_cols,
        var_name="length_col",
        value_name="rl_price_per_mbf"
    )
    long["length_ft"] = long["length_col"].str.extract(r'Length(\d+)Foot', expand=False).astype("Int64")
    long = long.drop(columns=["length_col"])
    return long

# ---------- Load RL ----------
rl = pd.read_csv(RL_CSV)
rl = normalize_cols(rl)
# Make sure expected columns exist (adjust names if needed)
rl = rl.rename(columns={
    "Region":"Region",
    "ItemDescription":"ItemDescription",
    "TransactionDate":"TransactionDate"
})
# Reshape to long
rl_long = melt_rl_lengths(rl)
# Parse dim/grade
rl_long["dimension"], rl_long["grade"] = parse_dim_grade_from_item(rl_long["ItemDescription"])
# Keep only grade 1/2 just in case
rl_long = rl_long[rl_long["grade"].isin([1,2])]
# Dates
rl_long["rl_date"] = pd.to_datetime(rl_long["TransactionDate"], errors="coerce")
# Standardize keys
rl_long["region"] = rl_long["Region"].astype(str).str.strip()
rl_long = rl_long.dropna(subset=["dimension","grade","length_ft","rl_price_per_mbf","rl_date"])

# ---------- Load AL ----------
al = pd.read_csv(AL_CSV)
al = normalize_cols(al)
al = al.rename(columns={
    "region":"region",
    "mill":"mill",
    "item_description":"item_description",
    "dimension":"dimension",
    "length_ft":"length_ft",
    "grade":"grade",
    "date":"date",
    "delivered_cost_per_mbf":"delivered_cost_per_mbf"
})
al["date"] = pd.to_datetime(al["date"], errors="coerce")
al["dimension"] = al["dimension"].astype(str).str.lower()
al["region"] = al["region"].astype(str).str.strip()
al["grade"] = pd.to_numeric(al["grade"], errors="coerce").astype("Int64")
al["length_ft"] = pd.to_numeric(al["length_ft"], errors="coerce").astype("Int64")
al = al.dropna(subset=["region","dimension","grade","length_ft","date","delivered_cost_per_mbf"])
al = al[al["grade"].isin([1,2])]

# ---------- Asof match per key ----------
# Sort for merge_asof requirements
rl_key_sort = rl_long.sort_values(["region","dimension","grade","length_ft","rl_date"])
al_key_sort = al.sort_values(["region","dimension","grade","length_ft","date"])

# We’ll merge in groups to avoid cross-key contamination
out_parts = []
tol = pd.Timedelta(days=ASOF_TOLERANCE_DAYS)

for key, al_grp in al_key_sort.groupby(["region","dimension","grade","length_ft"], dropna=False):
    r, d, g, L = key
    rl_grp = rl_key_sort[
        (rl_key_sort["region"]==r) &
        (rl_key_sort["dimension"]==d) &
        (rl_key_sort["grade"]==g) &
        (rl_key_sort["length_ft"]==L)
    ][["rl_date","rl_price_per_mbf"]].sort_values("rl_date")
    if rl_grp.empty:
        # no RL series available for this key — mark as unmatched
        tmp = al_grp.copy()
        tmp["rl_date"] = pd.NaT
        tmp["rl_price_per_mbf"] = np.nan
        tmp["days_to_rl_quote"] = np.nan
        tmp["match_flag"] = "no_series"
        out_parts.append(tmp)
        continue

    # merge_asof: nearest RL on/before AL date within tolerance
    merged = pd.merge_asof(
        al_grp.sort_values("date"),
        rl_grp,
        left_on="date",
        right_on="rl_date",
        direction="backward",
        tolerance=tol
    )
    merged["days_to_rl_quote"] = (merged["date"] - merged["rl_date"]).dt.days
    merged["match_flag"] = np.where(merged["rl_date"].isna(), "no_date_within_tol", "ok")
    out_parts.append(merged)

matched = pd.concat(out_parts, ignore_index=True)

# ---------- Final metrics ----------
matched["basis_abs"] = matched["delivered_cost_per_mbf"] - matched["rl_price_per_mbf"]
matched["item_description_key"] = (matched["dimension"].astype(str) + " #" + matched["grade"].astype(str))


# Inputs assumed from the previous step:
# rl_long: RL long-form with columns ['region','dimension','grade','length_ft', 'rl_date','rl_price_per_mbf']
# matched: output dataframe with 'match_flag' == 'no_series' rows to diagnose

# --- Build membership sets from RL ---
S_region = set(rl_long['region'].unique())
S_region_dim = set(zip(rl_long['region'], rl_long['dimension']))
S_region_dim_grade = set(zip(rl_long['region'], rl_long['dimension'], rl_long['grade']))
S_region_dim_len = set(zip(rl_long['region'], rl_long['dimension'], rl_long['length_ft']))
S_full = set(zip(rl_long['region'], rl_long['dimension'], rl_long['grade'], rl_long['length_ft']))

# Helper to test tuple membership vectorized-ish
def isin_tuples(df, cols, keyset):
    return list(zip(*[df[c] for c in cols]))  # list of tuples for those columns, same length as df
# (we'll use it with list comprehension and pd.Series for readability)

miss = matched[matched['match_flag']=='no_series'].copy()

# 1) Region exists?
miss['reason'] = np.where(~miss['region'].isin(S_region), 'region_not_in_RL', '')

# 2) Dimension within region?
mask_next = (miss['reason'] == '')
pairs = pd.Series(isin_tuples(miss[mask_next], ['region','dimension'], S_region_dim))
miss.loc[mask_next, 'reason'] = np.where(
    [t in S_region_dim for t in pairs],
    '',
    'dimension_not_in_region'
)

# 3) Grade within (region, dimension)?
mask_next = (miss['reason'] == '')
trip = pd.Series(isin_tuples(miss[mask_next], ['region','dimension','grade'], S_region_dim_grade))
miss.loc[mask_next, 'reason'] = np.where(
    [t in S_region_dim_grade for t in trip],
    '',
    'grade_not_in_region_dimension'
)

# 4) Length within (region, dimension)?
mask_next = (miss['reason'] == '')
trip_len = pd.Series(isin_tuples(miss[mask_next], ['region','dimension','length_ft'], S_region_dim_len))
miss.loc[mask_next, 'reason'] = np.where(
    [t in S_region_dim_len for t in trip_len],
    '',
    'length_not_in_region_dimension'
)

# 5) If all components exist, then the exact (region,dimension,grade,length) combo is unpublished
mask_next = (miss['reason'] == '')
quad = pd.Series(isin_tuples(miss[mask_next], ['region','dimension','grade','length_ft'], S_full))
miss.loc[mask_next, 'reason'] = np.where(
    [t in S_full for t in quad],
    'should_not_happen',           # would have matched if present
    'exact_combo_unpublished'
)

# Optional: summarize counts by reason
print(miss['reason'].value_counts(dropna=False))

# Optional: show a few examples per reason
for r in miss['reason'].unique():
    print(f"\n=== {r} ===")
    print(miss.loc[miss['reason']==r, ['region','dimension','grade','length_ft']].drop_duplicates().head(10))

# If you want this back on the main matched table:
matched = matched.merge(
    miss[['region','dimension','grade','length_ft','date','reason']],
    on=['region','dimension','grade','length_ft','date'],
    how='left'
)


# Reorder columns for readability
cols = [
    "region","mill","item_description","dimension","length_ft","grade",
    "date","delivered_cost_per_mbf",
    "rl_date","rl_price_per_mbf","days_to_rl_quote","match_flag",
    "basis_abs","item_description_key"
]
cols = [c for c in cols if c in matched.columns]
matched = matched[cols].sort_values(["region","mill","dimension","grade","length_ft","date"])

# Save
os.makedirs(os.path.dirname(OUT_CSV) or ".", exist_ok=True)
matched.to_csv(OUT_CSV, index=False)
print(f"Saved: {OUT_CSV}")
print(matched.head(10))
