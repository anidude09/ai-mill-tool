#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Sep 28 20:57:22 2025

@author: nitaishah
"""
import pandas as pd
import pgeocode
import requests
import folium

# ---- Example Data ----
example = {
    "Mill": "Vicksburg Forest Products, LLC",
    "OriginCity": "Vicksburg",
    "OriginST": "MS",
    "OriginZip": "39183",
    "CustomerName": "Apache Products, Inc",
    "DestAddress1": "1910 US Hwy 96 N",
    "DestCity": "Silsbee",
    "DestST": "TX",
    "DestZip": "77656",
    "poRecordID": 478039,
    "ShipDate": "2025-01-01"
}
df = pd.DataFrame([example])

# ---- Supplier geocode via ZIP (pgeocode) ----
nomi = pgeocode.Nominatim('us')
def zip_to_coords(zipcode):
    try:
        info = nomi.query_postal_code(str(zipcode))
        if info is not None and not pd.isna(info.latitude) and not pd.isna(info.longitude):
            return (info.latitude, info.longitude)
    except:
        return None
    return None

# ---- Customer geocode via Census ----
def census_geocode(address):
    url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
    params = {"address": address, "benchmark": "Public_AR_Current", "format": "json"}
    r = requests.get(url, params=params)
    try:
        result = r.json()["result"]["addressMatches"]
        if result:
            coords = result[0]["coordinates"]
            return (coords["y"], coords["x"])  # (lat, lon)
    except:
        return None
    return None

# ---- Build addresses ----
df["Origin_Coords"] = df["OriginZip"].apply(zip_to_coords)
df["Dest_Full"] = df["DestAddress1"] + ", " + df["DestCity"] + ", " + df["DestST"] + " " + df["DestZip"]
df["Dest_Coords"] = df["Dest_Full"].apply(census_geocode)

print(df[["Origin_Coords","Dest_Coords"]])

# ---- Create Map ----
m = folium.Map(location=[39.8283, -98.5795], zoom_start=4)

if df["Origin_Coords"].iloc[0] and df["Dest_Coords"].iloc[0]:
    folium.CircleMarker(
        location=df["Origin_Coords"].iloc[0],
        radius=6, color="green", fill=True,
        popup=f"Supplier: {df['Mill'].iloc[0]}"
    ).add_to(m)

    folium.CircleMarker(
        location=df["Dest_Coords"].iloc[0],
        radius=6, color="red", fill=True,
        popup=f"Customer: {df['CustomerName'].iloc[0]}"
    ).add_to(m)

    folium.PolyLine(
        locations=[df["Origin_Coords"].iloc[0], df["Dest_Coords"].iloc[0]],
        color="blue", weight=3, opacity=0.7,
        tooltip=f"Order {df['poRecordID'].iloc[0]} on {df['ShipDate'].iloc[0]}"
    ).add_to(m)

m.save("single_order_map.html")
print("✅ Example map saved as single_order_map.html")
