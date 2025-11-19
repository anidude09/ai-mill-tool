# Freight Intelligence Dashboard

Interactive Streamlit app for comparing LaneOne shipment activity with American Lumber contract loads, mill KPIs, and random-length trends.

## Repo Layout
- `Dashboard/Freight_analysis.py` – Streamlit entry point (all logic lives here).
- `KP1/Dashboard/dash_inputs/` – bundled CSVs used as default data sources:
  - `fact_contract_loads.csv`
  - `summary_tiles.csv`
  - `route_summary.csv`
  - `mill_rankings.csv`
  - `rl_reference_series.csv`
- `KP1/analysis_outputs/trend_dataset.csv` – optional trend series for the RL tab.
- `requirements.txt` – pinned Python dependencies for the hosted app.

All other analysis notebooks, large PNG exports, and raw data are ignored to keep this repo lightweight for Streamlit Cloud.

## Local Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Place refreshed CSVs in the paths above (or upload them manually via the sidebar once the app is running).

## Run Locally
```bash
streamlit run Dashboard/Freight_analysis.py
```

The sidebar uploaders are still available if you want to override the bundled data with ad‑hoc LaneOne/AL files.

## Deploy to Streamlit Cloud
1. Push this branch to GitHub (e.g., `dashboard_updates` → `main`).
2. Go to [share.streamlit.io](https://share.streamlit.io) and create a new app pointing to the repo, branch, and `Dashboard/Freight_analysis.py`.
3. Streamlit Cloud reads `runtime.txt` and builds the app with Python 3.10 so the prebuilt `pyarrow` wheel installs cleanly.
4. Streamlit Cloud installs `requirements.txt` automatically and caches the bundled CSVs.
5. After deploy, exercise each tab (with and without uploads) to confirm the fallback CSVs load correctly.

## Refreshing Data
When new KPI or RL datasets are produced:
1. Overwrite the CSVs inside `KP1/Dashboard/dash_inputs/` (and `KP1/analysis_outputs/trend_dataset.csv` if applicable).
2. Re-run the app locally to verify.
3. Commit the updated CSVs and push; Streamlit Cloud will redeploy with the latest numbers.

