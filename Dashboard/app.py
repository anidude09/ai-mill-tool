# activate: .venv\Scripts\activate
# pip show streamlit
# To run: streamlit run Dashboard/app.py

import os
import numpy as np
import pandas as pd
import streamlit as st
from io import StringIO

st.set_page_config(page_title="Mill Dashboard", layout="wide")

@st.cache_data(show_spinner=False)
def load_csv(path_or_bytes):
    """Load CSV from a local path or uploaded bytes; try to parse date-ish columns."""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        data = path_or_bytes.decode("utf-8", errors="ignore")
        df = pd.read_csv(StringIO(data))
    else:
        df = pd.read_csv(path_or_bytes)

    for c in df.columns:
        if df[c].dtype == "object" and any(k in c.lower() for k in ["date", "time", "timestamp"]):
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def infer_types(df):
    """Guess categorical, numeric, and date columns."""
    cats, nums, dates = [], [], []
    for c in df.columns:
        if np.issubdtype(df[c].dtype, np.number):
            nums.append(c)
        elif np.issubdtype(df[c].dtype, np.datetime64):
            dates.append(c)
        else:
            if df[c].nunique(dropna=True) <= max(50, len(df)//20):
                cats.append(c)
    return cats, nums, dates


def find_col(df, keywords, want_numeric=None, default=None):
    """
    Find the first column whose name contains any of the keywords (case-insensitive).
    Optionally require numeric dtype (want_numeric=True) or non-numeric (False).
    """
    kws = [k.lower() for k in keywords]
    for c in df.columns:
        name = c.lower()
        if any(k in name for k in kws):
            if want_numeric is None:
                return c
            if want_numeric and np.issubdtype(df[c].dtype, np.number):
                return c
            if (want_numeric is False) and (not np.issubdtype(df[c].dtype, np.number)):
                return c
    return default


def sidebar_filters(df, cats, nums, dates):
    st.sidebar.header("Filters")
    mask = pd.Series(True, index=df.index)

    for c in cats:
        vals = sorted(df[c].dropna().unique().tolist())
        pick = st.sidebar.multiselect(c, vals, default=[], key=f"cat_{c}")
        if pick:
            mask &= df[c].isin(pick)

    for d in dates:
        min_d, max_d = pd.to_datetime(df[d].min()), pd.to_datetime(df[d].max())
        if pd.isna(min_d) or pd.isna(max_d):
            continue
        start, end = st.sidebar.date_input(f"{d} range", (min_d.date(), max_d.date()), key=f"date_{d}")
        if isinstance(start, tuple):
            start, end = start
        mask &= (df[d] >= pd.to_datetime(start)) & (df[d] <= pd.to_datetime(end))

    for i, n in enumerate(nums[:8]):
        col_min = float(np.nanmin(df[n].values))
        col_max = float(np.nanmax(df[n].values))
        if col_min == col_max:
            continue
        lo, hi = st.sidebar.slider(f"{n} range", col_min, col_max, (col_min, col_max), key=f"num_{i}_{n}")
        mask &= df[n].between(lo, hi)

    return df[mask]

def kpis(df, nums):
    st.subheader("KPIs")
    chosen = st.multiselect("Choose up to 4 numeric columns", nums, max_selections=4, key="kpis_cols")
    agg = st.selectbox("Aggregation", ["sum", "mean", "median", "min", "max", "count"], index=0, key="agg_kpis")

    cols = st.columns(max(1, len(chosen)))
    for i, c in enumerate(chosen):
        try:
            val = getattr(df[c], agg)()
        except Exception:
            val = np.nan
        fmt = "{:,.2f}" if pd.api.types.is_float_dtype(df[c]) else "{:,}"
        cols[i].metric(c, fmt.format(val) if pd.notna(val) else "—")


def trend(df, nums, dates, cats):
    st.subheader("Trends / Time Series")
    if dates:
        x = st.selectbox("Time column", dates, key="trend_time")
    else:
        st.info("No datetime column detected; using categorical x-axis.")
        x = st.selectbox("X-axis (categorical)", cats if cats else df.columns.tolist(), key="trend_catx")
    y = st.selectbox("Y value", nums, index=0 if nums else None, key="trend_y")
    agg = st.selectbox("Aggregation", ["sum", "mean", "median", "min", "max", "count"], index=0, key="agg_trend")

    by = df.groupby(x)[y].agg(agg).reset_index().sort_values(x)
    chart = st.line_chart if x in dates else st.bar_chart
    chart(by.set_index(x)[y])
    st.dataframe(by, use_container_width=True)


def supply_chain_tab(df):
    """Supply-chain view for the simple mill_kpis.csv schema (if those cols exist)."""
    st.subheader("Supply Chain — Mill Mix & Performance")

    COL_MILL = "Mill"
    COL_READY_DAYS = "AvgDaysOnReadyList"
    COL_PCT_TO_CUST = "PctShippedToCustomers"
    COL_PCT_TO_PLANTS = "PctShippedToPlants"
    COL_MARGIN = "AvgGrossMargin_Customers"            
    COL_LOADS = "TotalLoads"

    required = [COL_MILL, COL_READY_DAYS, COL_PCT_TO_CUST, COL_PCT_TO_PLANTS, COL_LOADS]
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.info("This view expects the mill_kpis.csv schema. Columns missing: " + ", ".join(missing))
        return

    base = df.copy()
    base["LoadsToCustomers"] = base[COL_LOADS] * (base[COL_PCT_TO_CUST] / 100.0)
    base["LoadsToPlants"]    = base[COL_LOADS] * (base[COL_PCT_TO_PLANTS] / 100.0)

    mills = sorted(base[COL_MILL].dropna().unique().tolist())
    picked_mills = st.multiselect("Mills", mills, default=mills, key="sc_mills")

    dfm = base[base[COL_MILL].isin(picked_mills)]
    if dfm.empty:
        st.info("No rows after filters.")
        return

    total_loads = float(dfm[COL_LOADS].sum())
    avg_ready = float(dfm[COL_READY_DAYS].mean())
    w_margin = (dfm[COL_MARGIN] * dfm[COL_LOADS]).sum() / max(dfm[COL_LOADS].sum(), 1) if COL_MARGIN in dfm.columns else np.nan

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Loads", f"{int(total_loads):,}")
    c2.metric("Avg Days on Ready List", f"{avg_ready:,.2f}")
    c3.metric("Weighted Avg Margin ($)", "—" if pd.isna(w_margin) else f"{w_margin:,.2f}")

    st.divider()

    mix = (
        dfm[[COL_PCT_TO_CUST, COL_PCT_TO_PLANTS]].mean(numeric_only=True)
        .rename({COL_PCT_TO_CUST: "To Customers %", COL_PCT_TO_PLANTS: "To Plants %"})
        .to_frame("Percent").reset_index().rename(columns={"index": "Destination"})
    )
    st.write("**Overall Shipment Mix** (filtered set)")
    st.bar_chart(mix.set_index("Destination"))

    st.divider()

    st.write("**Top Mills by Loads (filtered)**")
    by_loads = dfm.groupby(COL_MILL, as_index=False)[COL_LOADS].sum().sort_values(COL_LOADS, ascending=False)
    st.bar_chart(by_loads.set_index(COL_MILL))


def sankey_flow_tab(df):
    """
    Flow (Sankey) with styling controls and a smart fallback:
    - If you don't have a destination column (or pick same col), toggle
      'derive Customers/Plants' and we build Mill → Customers/Plants using
      TotalLoads * % splits. Otherwise we draw a standard Source → Destination Sankey.
    """
    st.subheader("Source → Destination Flow")

    try:
        import plotly.graph_objects as go
        import plotly.express as px
    except ImportError:
        st.error("Plotly not installed. In terminal run: pip install plotly")
        return

    with st.expander("🎨 Visual style", expanded=True):
        colA, colB, colC, colD = st.columns(4)
        font_size = colA.slider("Font size", 10, 22, 14, key="sk_font")
        boldish   = colB.toggle("Bold labels", True, key="sk_bold")   
        thickness = colC.slider("Node thickness", 8, 40, 20, key="sk_thick")
        padding   = colD.slider("Node padding", 6, 40, 18, key="sk_pad")

        colE, colF, colG = st.columns(3)
        link_alpha = colE.slider("Link opacity", 0.10, 0.90, 0.35, step=0.05, key="sk_alpha")
        palette_name = colF.selectbox(
            "Palette",
            ["Set3", "Bold", "Pastel1", "Dark24", "Vivid"],
            index=0,
            key="sk_palette"
        )
        shorten = colG.toggle("Shorten long labels", True, key="sk_shorten")

    def get_palette(name):
        pals = px.colors.qualitative
        return getattr(pals, name) if hasattr(pals, name) else pals.Set3

    def to_rgba_any(color, alpha):
        import re
        c = str(color).strip()
        if c.startswith("#"):
            h = c.lstrip("#")
            if len(h) == 3:  
                h = "".join([ch*2 for ch in h])
            r = int(h[0:2], 16); g = int(h[2:4], 16); b = int(h[4:6], 16)
            return f"rgba({r},{g},{b},{alpha})"
        if c.startswith("rgb"):
            nums = re.findall(r"[\d.]+", c)
            r = int(float(nums[0])); g = int(float(nums[1])); b = int(float(nums[2]))
            return f"rgba({r},{g},{b},{alpha})"
        
        return f"rgba(120,120,120,{alpha})"

    def compact(lbl):
        if not shorten or len(str(lbl)) <= 18:
            return str(lbl)
        return str(lbl)[:16] + "…"

    def draw_sankey(node_labels, sources, targets, values, src_index_for_link,
                    valueformat=",.2f", hover_suffix="", palette="Set3"):
        pal = get_palette(palette)
        node_colors = [pal[i % len(pal)] for i in range(len(node_labels))]

        totals = {}
        for s, v in zip(sources, values):
            totals[s] = totals.get(s, 0.0) + (0.0 if pd.isna(v) else float(v))
        pct_of_source = []
        for s, v in zip(sources, values):
            denom = totals.get(s, 0.0)
            pct = 0.0 if denom == 0 else float(v) / denom * 100.0
            pct_of_source.append(pct)

        link_colors = [to_rgba_any(node_colors[s], link_alpha) for s in sources]

        font_family = "Arial Black, Arial" if boldish else "Inter, Segoe UI, Arial"

        fig = go.Figure(data=[go.Sankey(
            arrangement="snap",
            valueformat=valueformat,
            node=dict(
                pad=padding,
                thickness=thickness,
                label=[compact(x) for x in node_labels],
                color=node_colors,
                line=dict(width=0.7, color="rgba(0,0,0,0.35)"),
                hovertemplate="%{label}<extra></extra>",
            ),
            link=dict(
                source=sources,
                target=targets,
                value=values,
                color=link_colors,
                customdata=np.array(pct_of_source),
                hovertemplate=(
                    "Flow: %{source.label} → %{target.label}"
                    "<br>Value: %{value}" + hover_suffix +
                    "<br>% of source: %{customdata:.1f}%<extra></extra>"
                ),
            ),
        )])

        fig.update_layout(
            template="plotly_white",
            margin=dict(l=10, r=10, t=10, b=10),
            font=dict(size=font_size, family=font_family),
            height=max(460, 26 * len(node_labels) + 180),
        )
        st.plotly_chart(fig, use_container_width=True)

    cols = list(df.columns)
    obj_cols = [c for c in cols if df[c].dtype == "object"]
    num_cols = [c for c in cols if np.issubdtype(df[c].dtype, np.number)]

    def guess(cands, keys):
        keys = [k.lower() for k in keys]
        for c in cands:
            if any(k in c.lower() for k in keys):
                return c
        return None

    src_guess = guess(obj_cols, ["mill", "source", "origin", "from"]) or (obj_cols[0] if obj_cols else None)
    dst_guess = guess(obj_cols, ["customer", "dest", "plant", "to", "receiver", "ship_to"]) or src_guess
    val_guess = guess(num_cols, ["load", "loads", "total_loads", "revenue", "amount", "qty", "volume", "cases", "count"]) \
                or (num_cols[0] if num_cols else None)

    c1, c2, c3 = st.columns(3)
    source_col = c1.selectbox("Source column", options=obj_cols or cols,
                              index=(obj_cols or cols).index(src_guess) if src_guess in (obj_cols or cols) else 0,
                              key="sk_src")
    dest_col   = c2.selectbox("Destination column", options=obj_cols or cols,
                              index=(obj_cols or cols).index(dst_guess) if dst_guess in (obj_cols or cols) else 0,
                              key="sk_dst")

    if num_cols:
        value_mode = c3.radio("Value", ["Use a numeric column", "Count rows"], horizontal=True, key="sk_value_mode")
        if value_mode == "Use a numeric column":
            value_col = c3.selectbox("Numeric column", options=num_cols,
                                     index=num_cols.index(val_guess) if val_guess in num_cols else 0,
                                     key="sk_value_col")
        else:
            value_col = None
    else:
        st.info("No numeric columns found; using row count as the flow value.")
        value_col = None

    need = {"Mill", "TotalLoads", "PctShippedToCustomers", "PctShippedToPlants"}
    can_derive = need.issubset(set(df.columns))
    default_derive = (source_col == dest_col) or (len(obj_cols) <= 1)
    use_derived = False
    if can_derive:
        use_derived = st.toggle(
            "No destination column? Build Customers/Plants from percentage columns",
            value=default_derive,
            key="sk_derive"
        )

    if use_derived:
        tmp = df[["Mill", "TotalLoads", "PctShippedToCustomers", "PctShippedToPlants"]].dropna().copy()
        if tmp.empty:
            st.info("Nothing to plot after filters.")
            return
        tmp["to_cust"] = tmp["TotalLoads"] * (tmp["PctShippedToCustomers"] / 100.0)
        tmp["to_plants"] = tmp["TotalLoads"] * (tmp["PctShippedToPlants"] / 100.0)

        agg = (tmp.groupby("Mill", as_index=False)
                 .agg(total_loads=("TotalLoads", "sum"),
                      to_cust=("to_cust", "sum"),
                      to_plants=("to_plants", "sum"))
                 .sort_values("total_loads", ascending=False))

        topn = st.slider("Top N mills", 3, min(30, len(agg)), min(12, len(agg)), key="sk_topn_mills")
        agg = agg.head(topn)
        mode = st.radio("Width represents", ["Absolute loads", "% share per mill"], horizontal=True, key="sk_mode_derived")
        if mode == "% share per mill":
            shown_c = np.where(agg["total_loads"] > 0, agg["to_cust"] / agg["total_loads"] * 100, 0)
            shown_p = np.where(agg["total_loads"] > 0, agg["to_plants"] / agg["total_loads"] * 100, 0)
            valuesuffix, valueformat = "%", ".2f"
        else:
            shown_c = agg["to_cust"].values
            shown_p = agg["to_plants"].values
            valuesuffix, valueformat = "", ",.2f"

        mills = agg["Mill"].tolist()
        labels = mills + ["Customers", "Plants"]
        idx = {l: i for i, l in enumerate(labels)}

        src, tgt, val, src_index = [], [], [], []
        for m, vc, vp in zip(mills, shown_c, shown_p):
            if vc > 0:
                src.append(idx[m]); tgt.append(idx["Customers"]); val.append(float(vc)); src_index.append(idx[m])
            if vp > 0:
                src.append(idx[m]); tgt.append(idx["Plants"]);    val.append(float(vp)); src_index.append(idx[m])

        draw_sankey(labels, src, tgt, val, src_index_for_link=src_index,
                    valueformat=valueformat, hover_suffix=valuesuffix, palette=palette_name)
        return

    if source_col == dest_col:
        st.error("Source and Destination must be different columns.")
        return

    tmp = df.copy()
    if value_col is None:
        tmp["_value"] = 1.0
        vcol = "_value"
    else:
        vcol = value_col

    agg = tmp.groupby([source_col, dest_col], dropna=False)[vcol].sum().reset_index().rename(columns={vcol: "value"})
    if agg.empty:
        st.info("Nothing to plot after filters.")
        return

    s_tot = agg.groupby(source_col)["value"].sum().sort_values(ascending=False)
    d_tot = agg.groupby(dest_col)["value"].sum().sort_values(ascending=False)
    c4, c5 = st.columns(2)
    top_src = c4.slider("Top N sources", 3, min(30, len(s_tot)), min(12, len(s_tot)), key="sk_top_src")
    top_dst = c5.slider("Top N destinations", 3, min(30, len(d_tot)), min(12, len(d_tot)), key="sk_top_dst")

    top_src_names = s_tot.head(top_src).index
    top_dst_names = d_tot.head(top_dst).index

    agg2 = agg.copy()
    agg2.loc[~agg2[source_col].isin(top_src_names), source_col] = "Other Sources"
    agg2.loc[~agg2[dest_col].isin(top_dst_names), dest_col] = "Other Destinations"
    agg2 = agg2.groupby([source_col, dest_col], dropna=False)["value"].sum().reset_index()

    mode = st.radio("Width represents", ["Absolute", "% share per source"], horizontal=True, key="sk_mode_std")
    if mode == "% share per source":
        agg2["value_plot"] = agg2["value"] / agg2.groupby(source_col)["value"].transform("sum") * 100.0
        valueformat = ".2f"; hover_suffix = "%"
    else:
        agg2["value_plot"] = agg2["value"]
        valueformat = ",.2f"; hover_suffix = ""

    src_labels = list(pd.Series(agg2[source_col].astype(str).unique()))
    dst_labels = list(pd.Series(agg2[dest_col].astype(str).unique()))
    node_labels = src_labels + dst_labels
    idx = {label: i for i, label in enumerate(node_labels)}

    sources = [idx[s] for s in agg2[source_col].astype(str)]
    targets = [idx[d] for d in agg2[dest_col].astype(str)]
    values  = agg2["value_plot"].astype(float).tolist()

    draw_sankey(node_labels, sources, targets, values,
                src_index_for_link=sources,
                valueformat=valueformat, hover_suffix=hover_suffix, palette=palette_name)


def main():
    st.title("📊 Mill Analysis")

    # Data source selector
    st.sidebar.write("### Data Source")
    root = os.path.dirname(__file__)
    default_kpi = os.path.abspath(os.path.join(root, "..", "mill_kpis.csv"))

    dataset = st.sidebar.radio(
        "Choose dataset",
        ["mill_kpis.csv", "Upload CSV"],
        index=0,
        key="dataset_selector",
    )

    df = None
    if dataset == "mill_kpis.csv":
        path = st.sidebar.text_input("CSV path", value=default_kpi, key="path_kpi")
        if os.path.exists(path):
            df = load_csv(path)
        else:
            st.sidebar.error("File not found. Adjust the path.")
    else:
        up = st.sidebar.file_uploader("Upload a CSV", type=["csv"], key="upload_csv")
        if up is not None:
            df = load_csv(up.getvalue())

    if df is None:
        st.info("👈 Load a dataset to begin.")
        st.stop()

    cats, nums, dates = infer_types(df)


    filtered = sidebar_filters(df, cats, nums, dates)
    st.success(f"Filters applied. Showing {len(filtered):,} / {len(df):,} rows.")

    t1, t2, t4, t5, t6 = st.tabs([
        "Overview", "Trends", "Data", "Supply Chain", "Flow (Sankey)"
    ])
    with t1:
        kpis(filtered, nums) if nums else st.info("No numeric columns for KPIs.")
    with t2:
        trend(filtered, nums, dates, cats) if nums else st.info("No numeric columns to chart.")
    with t4:
        st.dataframe(filtered, use_container_width=True, height=500)
        st.download_button(
            "Download filtered CSV",
            filtered.to_csv(index=False).encode("utf-8"),
            file_name="filtered.csv",
            mime="text/csv",
            key="dl_filtered",
        )
    with t5:
        supply_chain_tab(filtered)  
    with t6:
        sankey_flow_tab(filtered)


if __name__ == "__main__":
    main()
