#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov  3 21:08:18 2025

@author: nitaishah
"""

import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt
import seaborn as sns

# ====== INPUT / OUTPUT PATHS ======
file_path = "/Users/nitaishah/Desktop/STAT-683/FINAL_PROJECT/output_sheets/Random Lengths (Grade 1&2).xlsx"
output_dir = "./analysis_outputs"
os.makedirs(output_dir, exist_ok=True)

# ====== 1️⃣ LOAD DATA ======
df = pd.read_excel(file_path)
df.columns = df.columns.str.strip().str.replace(" ", "").str.replace("\n", "")

# Rename for easier use
rename_map = {
    'Region': 'region',
    'ItemDescription': 'item_desc',
    'TransactionDate': 'transaction_date'
}
df = df.rename(columns=rename_map)

# Melt to long format: Length, Price
length_cols = [c for c in df.columns if c.lower().startswith("length")]
df_long = df.melt(
    id_vars=['region', 'item_desc', 'transaction_date'],
    value_vars=length_cols,
    var_name='length',
    value_name='price'
)

# Clean length names (e.g., Length8Foot -> 8)
df_long['length'] = df_long['length'].str.extract(r'(\d+)').astype(int)

# Extract grade and dimension from item description (e.g., "2x4 #1")
df_long[['dimension', 'grade']] = df_long['item_desc'].str.extract(r'(\d+[xX]\d+)\s*#?(\d+)')

# Clean and convert
df_long['transaction_date'] = pd.to_datetime(df_long['transaction_date'])
df_long['price'] = pd.to_numeric(df_long['price'], errors='coerce')

# ====== 2️⃣ DETECT INTERVALS ======
df_long = df_long.sort_values('transaction_date')
intervals = df_long['transaction_date'].drop_duplicates().sort_values().diff().dt.days.dropna()
interval_summary = {
    "most_common_interval_days": int(intervals.mode()[0]),
    "mean_interval_days": round(intervals.mean(), 2),
    "min_interval": int(intervals.min()),
    "max_interval": int(intervals.max())
}
print("Interval summary:", interval_summary)

pd.DataFrame([interval_summary]).to_csv(os.path.join(output_dir, "interval_summary.csv"), index=False)

# ====== 3️⃣ GROUPED DATASETS ======
# Average price by region, grade, dimension, length, and date
group_cols = ['region', 'grade', 'dimension', 'length', 'transaction_date']
agg_df = df_long.groupby(group_cols, as_index=False)['price'].mean()
agg_df.to_csv(os.path.join(output_dir, "grouped_prices.csv"), index=False)

# Rolling 4-period average (weekly/monthly smoothing)
agg_df['rolling_avg'] = agg_df.groupby(['region', 'grade', 'dimension', 'length'])['price'].transform(
    lambda x: x.rolling(4, min_periods=1).mean()
)
agg_df.to_csv(os.path.join(output_dir, "trend_dataset.csv"), index=False)

# ====== 4️⃣ VISUALIZE SAMPLE TRENDS ======
sns.set(style="whitegrid")

for (r, g, d), subdf in agg_df.groupby(['region', 'grade', 'dimension']):
    plt.figure(figsize=(10, 5))
    sns.lineplot(data=subdf, x='transaction_date', y='rolling_avg', hue='length', marker='o')
    plt.title(f"Lumber Price Trend | Region: {r} | Grade: {g} | Dim: {d}")
    plt.xlabel("Transaction Date")
    plt.ylabel("Price ($/MBF)")
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f"trend_{r}_{g}_{d}.png"))
    plt.close()

print("✅ All datasets and plots saved in:", output_dir)
