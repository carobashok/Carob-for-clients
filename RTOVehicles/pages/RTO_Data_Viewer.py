"""
pages/RTO_Data_Viewer.py
==========================
Viewer page for Vahan RTO vehicle registration data stored in Supabase.

Two-level view driven by filter selections:
  1. State selected (no RTO) → trend chart + Maker × Vehicle Group pivot
  2. RTO selected → trend chart + Maker × Sub-Column pivot

Filters: State, Dimension, RTO, Category Group, Year
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client

st.set_page_config(page_title="RTO Data Viewer", page_icon="📊", layout="wide")

st.title("📊 RTO Vehicle Data Viewer")


# ── Supabase client ───────────────────────────────────────────────────────────

@st.cache_resource
def get_supabase_client():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
    except KeyError:
        st.error("Supabase credentials not found. Add [supabase] section with url and key in Secrets.")
        st.stop()
    return create_client(url, key)


TABLE_NAME = "vahan_rto_data"


@st.cache_data(ttl=600)
def load_data(table_name: str) -> pd.DataFrame:
    client = get_supabase_client()
    page_size = 1000
    all_rows = []
    start = 0
    while True:
        resp = client.table(table_name).select("*").range(start, start + page_size - 1).execute()
        batch = resp.data
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return pd.DataFrame(all_rows) if all_rows else pd.DataFrame()


# ── Load data ─────────────────────────────────────────────────────────────────

col_refresh, _ = st.columns([1, 6])
with col_refresh:
    if st.button("🔄 Refresh data"):
        st.cache_data.clear()

with st.spinner("Loading from Supabase …"):
    df = load_data(TABLE_NAME)

if df.empty:
    st.warning("No data found. Upload data via the loader page first.")
    st.stop()


# ── Filters ───────────────────────────────────────────────────────────────────

st.subheader("Filters")
fc1, fc2, fc3, fc4, fc5 = st.columns(5)

with fc1:
    state_opts = sorted(df["state"].dropna().unique())
    selected_state = st.selectbox("State", ["(All States)"] + list(state_opts))

with fc2:
    dim_opts = sorted(df["dimension_name"].dropna().unique())
    default_dim = dim_opts.index("Maker") if "Maker" in dim_opts else 0
    selected_dim = st.selectbox("Dimension", dim_opts, index=default_dim)

# RTO options narrow to selected state
rto_source = df if selected_state == "(All States)" else df[df["state"] == selected_state]
with fc3:
    rto_opts = sorted(rto_source["rto"].dropna().unique())
    selected_rto = st.selectbox("RTO", ["(All RTOs — State Summary)"] + list(rto_opts))

with fc4:
    cat_opts = sorted(df["category_group"].dropna().unique())
    selected_cat = st.selectbox("Category Group", ["(All)"] + list(cat_opts))

with fc5:
    year_source = df[df["dimension_name"] == selected_dim].copy()
    if selected_state != "(All States)":
        year_source = year_source[year_source["state"] == selected_state]
    if selected_rto != "(All RTOs — State Summary)":
        year_source = year_source[year_source["rto"] == selected_rto]
    year_opts = sorted(year_source["year"].dropna().unique(), reverse=True)
    selected_year = st.selectbox("Year", ["(All Years)"] + list(year_opts))


# ── Apply base filters ────────────────────────────────────────────────────────

view_df = df[df["dimension_name"] == selected_dim].copy()

if selected_state != "(All States)":
    view_df = view_df[view_df["state"] == selected_state]
if selected_rto != "(All RTOs — State Summary)":
    view_df = view_df[view_df["rto"] == selected_rto]
if selected_cat != "(All)":
    view_df = view_df[view_df["category_group"] == selected_cat]

# Keep unfiltered-by-year copy for the trend chart
trend_df = view_df.copy()

# Apply year filter only for the pivot table below
if selected_year != "(All Years)":
    view_df = view_df[view_df["year"] == selected_year]

if view_df.empty:
    st.info("No data matches the current filter selection.")
    st.stop()

rto_selected = selected_rto != "(All RTOs — State Summary)"
scope_label = selected_rto.split("-")[0].strip() if rto_selected else (
    selected_state if selected_state != "(All States)" else "All States"
)


# ── Metrics row ───────────────────────────────────────────────────────────────

totals_df = view_df[view_df["sub_column"].str.upper() == "TOTAL"]

# Separate "Till Today" from annual totals for the metric card
till_today_total = (
    trend_df[
        (trend_df["sub_column"].str.upper() == "TOTAL") &
        (trend_df["year"].str.lower() == "till today")
    ]["value"].sum()
)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Vehicles (filtered view)", f"{int(totals_df['value'].sum()):,}")
if till_today_total > 0:
    m2.metric("📌 Till Today (cumulative)", f"{int(till_today_total):,}")
else:
    m2.metric("Unique Makers / Classes", view_df["dimension_value"].nunique())
m3.metric("RTOs covered", view_df["rto"].nunique())
m4.metric("Years in view", view_df["year"].nunique())

st.divider()


# ── Year-wise Trend Chart ─────────────────────────────────────────────────────

st.subheader(f"📈 Year-wise Registration Trend — {scope_label}")

# Build yearly totals from trend_df (ignores dimension/maker filter, ignores year filter)
# Exclude 'Till Today' from the trend since it's cumulative, not a single year
yearly_src = trend_df[
    (trend_df["sub_column"].str.upper() == "TOTAL") &
    (trend_df["year"].str.lower() != "till today")
]

yearly_totals = (
    yearly_src.groupby("year", as_index=False)["value"]
    .sum()
    .rename(columns={"value": "Total Vehicles"})
    .sort_values("year")
)

if yearly_totals.empty:
    st.info("No year-wise data available for the current State/RTO selection.")
else:
    fig = go.Figure()

    # Bars — absolute count per year
    fig.add_trace(go.Bar(
        x=yearly_totals["year"],
        y=yearly_totals["Total Vehicles"],
        name="Registered Vehicles",
        marker_color="#2563EB",
        opacity=0.75,
        text=yearly_totals["Total Vehicles"].apply(lambda v: f"{int(v):,}"),
        textposition="outside",
    ))

    # Line — trend overlay
    fig.add_trace(go.Scatter(
        x=yearly_totals["year"],
        y=yearly_totals["Total Vehicles"],
        name="Trend",
        mode="lines+markers",
        line=dict(color="#F59E0B", width=2.5),
        marker=dict(size=7, color="#F59E0B"),
    ))

    fig.update_layout(
        xaxis_title="Year",
        yaxis_title="Total Registered Vehicles",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(gridcolor="rgba(0,0,0,0.07)"),
        xaxis=dict(type="category"),
        margin=dict(t=40, b=40),
        height=420,
    )

    st.plotly_chart(fig, use_container_width=True)

st.divider()


# ── VIEW 1: State-level — Maker × Vehicle Group pivot ─────────────────────────

if not rto_selected:
    st.subheader(f"{scope_label} Summary — {selected_dim} × Vehicle Group")
    st.caption(
        "Rows = Makers/Classes  |  Columns = Vehicle Category Groups  |  "
        "Values = Total registered vehicles  |  "
        "Select an RTO above to drill into sub-column breakdown."
    )

    pivot_src = view_df[view_df["sub_column"].str.upper() == "TOTAL"]

    if pivot_src.empty:
        st.info("No TOTAL rows found for this filter combination.")
    else:
        pivot = (
            pivot_src
            .groupby(["dimension_value", "category_group"])["value"]
            .sum()
            .reset_index()
            .pivot(index="dimension_value", columns="category_group", values="value")
            .fillna(0)
            .astype(int)
        )
        pivot.index.name = selected_dim
        pivot["TOTAL"] = pivot.sum(axis=1)
        pivot = pivot.sort_values("TOTAL", ascending=False)
        cols = [c for c in pivot.columns if c != "TOTAL"] + ["TOTAL"]
        pivot = pivot[cols]

        st.dataframe(pivot, use_container_width=True)
        csv = pivot.reset_index().to_csv(index=False).encode()
        st.download_button("⬇️ Download as CSV", csv, "state_summary.csv", "text/csv")


# ── VIEW 2: RTO-level — Maker × Sub-column pivot ─────────────────────────────

else:
    st.subheader(f"{scope_label} — {selected_dim} × Sub-Column Breakdown")
    st.caption(
        "Rows = Makers/Classes  |  Columns = Sub-types (e.g. 4WIC / LMV / MMV / HMV / TOTAL)  |  "
        "Filter by Category Group above to narrow down."
    )

    pivot_src = view_df.copy()

    if pivot_src.empty:
        st.info("No data found for this RTO with the current filters.")
    else:
        pivot = (
            pivot_src
            .groupby(["dimension_value", "category_group", "sub_column"])["value"]
            .sum()
            .reset_index()
            .pivot_table(
                index=["dimension_value", "category_group"],
                columns="sub_column",
                values="value",
                aggfunc="sum",
                fill_value=0,
            )
            .astype(int)
        )
        pivot.index.names = [selected_dim, "Category Group"]
        sub_cols = [c for c in pivot.columns if c != "TOTAL"]
        if "TOTAL" in pivot.columns:
            pivot = pivot[sub_cols + ["TOTAL"]]
        sort_col = "TOTAL" if "TOTAL" in pivot.columns else (pivot.columns[0] if len(pivot.columns) else None)
        if sort_col:
            pivot = pivot.sort_values(sort_col, ascending=False)

        st.dataframe(pivot, use_container_width=True)
        csv = pivot.reset_index().to_csv(index=False).encode()
        st.download_button("⬇️ Download as CSV", csv, f"{scope_label}_breakdown.csv", "text/csv")


# ── Detailed raw rows (collapsible) ──────────────────────────────────────────

with st.expander("📋 Show raw data rows"):
    display_df = view_df[["state", "rto", "year", "category_group",
                           "dimension_value", "sub_column", "value"]].rename(columns={
        "state": "State", "rto": "RTO", "year": "Year",
        "category_group": "Category Group", "dimension_value": selected_dim,
        "sub_column": "Sub Column", "value": "Value",
    })
    st.dataframe(
        display_df.sort_values(["Year", "Category Group", selected_dim]),
        use_container_width=True, hide_index=True,
    )
    st.caption(f"{len(display_df):,} rows for current filter selection.")
    raw_csv = display_df.to_csv(index=False).encode()
    st.download_button("⬇️ Download raw rows", raw_csv, "rto_raw_data.csv",
                       "text/csv", key="raw_dl")
