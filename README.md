# Freight Intelligence Dashboard

Interactive Streamlit dashboard that surfaces three complementary views of the LaneOne + American Lumber dataset:

- **Freight Lane Analysis** – match LaneOne shipments to American Lumber purchase orders, measure transit time, carrier cost per mile, and DAT index comparisons, and highlight top-performing mills.
- **Mill Delivered Cost KPIs** – aggregate `fact_contract_loads.csv` by mill, vendor, product, and destination type to monitor delivered cost/MBF, RL price benchmarks, and gross-margin health.
- **Random Lengths Trends** – visualize `rl_reference_series.csv` and optional `trend_dataset.csv` to compare RL price movements across regions, dimensions, grades, and lengths.

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

All other analysis notebooks, PNG exports, and raw data stay outside the repo so the Streamlit app remains lightweight.

The sidebar file uploaders let analysts swap in fresh LaneOne, AL, KPI, and RL CSVs without editing any code. Keeping the bundled defaults up to date in `KP1/Dashboard/dash_inputs/` ensures the hosted dashboard always opens with the latest snapshot.



Link : https://american-lumber-kpi.streamlit.app
