#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Sep 29 23:51:11 2025

@author: nitaishah
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score

# ---------------- Load Data ----------------
df = pd.read_csv("/Users/nitaishah/Desktop/STAT-683/Data_Processing/AL_LaneOne_Merged_inner.csv", low_memory=False)

# ---------------- Target ----------------
# Convert to numeric (some columns may be strings with mixed dtypes)
df["LOT Profit %"] = pd.to_numeric(df["LOT Profit %"], errors="coerce")
df["LOT Gross Profit"] = pd.to_numeric(df["LOT Gross Profit"], errors="coerce")

# Drop rows with missing target
df = df.dropna(subset=["LOT Profit %"])

# ---------------- Feature Engineering ----------------
# Parse dates
for col in ["Ship Date", "Delivered Date", "Mill Ready Dt"]:
    df[col] = pd.to_datetime(df[col], errors="coerce")

# Create time features
df["ship_month"] = df["Ship Date"].dt.month
df["ship_weekday"] = df["Ship Date"].dt.weekday
df["lead_time_days"] = (df["Delivered Date"] - df["Ship Date"]).dt.days

# Numerical features to keep
num_features = [
    "Miles/Class", "SalePrice", "LumberCost", "CarrierCost",
    "DATRate", "EstFreight", "ActFreightCost",
    "BF", "ConvBF", "ship_month", "ship_weekday", "lead_time_days"
]

# Convert numeric features safely
for col in num_features:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# Fill NaN with 0 for costs/distances
df[num_features] = df[num_features].fillna(0)

# Categorical features to encode
cat_features = ["Grade", "Species", "OriginST", "DestST", "Carrier Name", "ShipVia", "Mill"]

# Keep only selected columns
X = df[num_features + cat_features]
y = df["LOT Profit %"]

# ---------------- Train/Test Split ----------------
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# ---------------- Preprocessing ----------------
# One-hot encode categorical variables
preprocessor = ColumnTransformer(
    transformers=[
        ("num", "passthrough", num_features),
        ("cat", OneHotEncoder(handle_unknown="ignore"), cat_features)
    ]
)

# ---------------- Model Pipeline ----------------
model = Pipeline(steps=[
    ("preprocessor", preprocessor),
    ("regressor", RandomForestRegressor(
        n_estimators=200,
        max_depth=12,
        random_state=42,
        n_jobs=-1
    ))
])

# ---------------- Train ----------------
model.fit(X_train, y_train)

# ---------------- Evaluate ----------------
y_pred = model.predict(X_test)

mae = mean_absolute_error(y_test, y_pred)
r2 = r2_score(y_test, y_pred)

print(f"MAE: {mae:.2f}")
print(f"R²: {r2:.2f}")

# ---------------- Feature Importance ----------------

ohe = model.named_steps["preprocessor"].named_transformers_["cat"]
cat_names = ohe.get_feature_names_out(cat_features)
all_features = num_features + list(cat_names)

importances = model.named_steps["regressor"].feature_importances_
feat_imp = pd.Series(importances, index=all_features).sort_values(ascending=False)

print("\nTop 15 Important Features for Margin % Prediction:")
print(feat_imp.head(15))

import matplotlib.pyplot as plt
import seaborn as sns

# Assuming you already have feat_imp (pd.Series with feature importances)
plt.figure(figsize=(8, 6))
sns.barplot(x=feat_imp.values[:15], y=feat_imp.index[:15], palette="Blues_r")
plt.title("Top 15 Feature Importances")
plt.xlabel("Importance")
plt.ylabel("Feature")
plt.tight_layout()
plt.show()

import matplotlib.pyplot as plt
import seaborn as sns

# Assuming you have y_test and y_pred from your model
plt.figure(figsize=(6, 6))
sns.scatterplot(x=y_test, y=y_pred, alpha=0.6)
plt.plot([y_test.min(), y_test.max()], [y_test.min(), y_test.max()],
         color="red", linestyle="--", label="Perfect Prediction")
plt.title("Predicted vs Actual Margin %")
plt.xlabel("Actual Margin %")
plt.ylabel("Predicted Margin %")
plt.legend()
plt.tight_layout()
plt.show()

