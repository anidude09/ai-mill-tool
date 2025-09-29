#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Sep 28 22:45:00 2025

@author: nitaishah
"""

import pandas as pd
import requests
import folium
import pgeocode
from tqdm import tqdm

# ---------- Load AL Data ----------
df = pd.read_csv("/Users/nitaishah/Desktop/STAT-683/Data/Data_Split/AL/AL Data .csv")

# ---------- Geocoders ----------
nomi = pgeocode.Nominatim("us")

def zip_to_coords(zipcode):
    """Supplier geocode by ZIP."""
    try:
        info = nomi.query_postal_code(str(zipcode))
        if info is not None and not pd.isna(info.latitude) and not pd.isna(info.longitude):
            return (info.latitude, info.longitude)
    except:
        return None
    return None

def census_geocode(address):
    """Customer geocode via Census API (full address)."""
    url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
    params = {"address": address, "benchmark": "Public_AR_Current", "format": "json"}
    try:
        r = requests.get(url, params=params, timeout=10)
        result = r.json()["result"]["addressMatches"]
        if result:
            coords = result[0]["coordinates"]
            return (coords["y"], coords["x"])  # (lat, lon)
    except:
        return None
    return None

# ---------- Build addresses ----------
df["Origin_Full"] = df["OriginCity"].astype(str) + ", " + df["OriginST"].astype(str) + " " + df["OriginZip"].astype(str)
df["Dest_Full"]   = df["DestAddress1"].astype(str) + ", " + df["DestCity"].astype(str) + ", " + df["DestST"].astype(str) + " " + df["DestZip"].astype(str)

# ---------- Geocode origins (by ZIP) ----------
tqdm.pandas()
df["Origin_Coords"] = df["OriginZip"].progress_apply(zip_to_coords)

# ---------- Geocode unique destinations (street addresses) ----------
unique_dests = df["Dest_Full"].dropna().unique()
dest_to_coords = {}

for addr in tqdm(unique_dests, desc="Geocoding destinations"):
    dest_to_coords[addr] = census_geocode(addr)

df["Dest_Coords"] = df["Dest_Full"].map(dest_to_coords)

# ---------- Drop rows with missing coords ----------
df = df[df["Origin_Coords"].notna() & df["Dest_Coords"].notna()]

# ---------- Aggregate flows ----------
flows = (
    df.groupby(["Origin_Full", "Dest_Full", "Origin_Coords", "Dest_Coords"])
    .size()
    .reset_index(name="num_shipments")
)

# ---------- Create Map ----------
m = folium.Map(location=[39.8283, -98.5795], zoom_start=4)

for _, row in flows.iterrows():
    if row["Origin_Coords"] and row["Dest_Coords"]:
        folium.PolyLine(
            locations=[row["Origin_Coords"], row["Dest_Coords"]],
            color="blue",
            weight=1 + row["num_shipments"] * 0.3,  # line thickness by shipment count
            opacity=0.6,
            tooltip=f"{row['num_shipments']} shipments\n{row['Origin_Full']} → {row['Dest_Full']}"
        ).add_to(m)

# Optional: markers for suppliers and customers
for _, row in flows.iterrows():
    # Supplier marker
    folium.CircleMarker(
        location=row["Origin_Coords"],
        radius=4, color="green", fill=True, fill_opacity=0.7,
        popup=f"Supplier: {row['Origin_Full']}"
    ).add_to(m)
    
    # Customer marker
    folium.CircleMarker(
        location=row["Dest_Coords"],
        radius=4, color="red", fill=True, fill_opacity=0.7,
        popup=f"Customer: {row['Dest_Full']}"
    ).add_to(m)

# ---------- Save map ----------
m.save("AL_orders_flow_map.html")
print("✅ Flow map saved as AL_orders_flow_map.html")
