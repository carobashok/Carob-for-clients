"""
pages/RTO_Data_Viewer.py
==========================
Viewer page for the uploaded Vahan RTO data: filter by RTO and vehicle
type, see year-wise bar charts of total registered vehicles.

Place this file inside a 'pages/' folder next to your main app file
(e.g. 'RTO Vehicles/pages/RTO_Data_Viewer.py' if your main module is
'RTO Vehicles/RTO_VEHICLE_INFO.py') — Streamlit auto-detects files in
'pages/' as additional navigable pages.
"""

import streamlit as st
import pandas as pd
from supabase import create_client

st.set_page_config(page_title="RTO Data Viewer", page_icon="📊", layout="wide")

st.title("📊 RTO Vehicle Data Viewer")
st.caption("Filter by RTO and vehicle type, view year-wise registration totals.")


# ── Supabase client ───────────────────────────────────────────────────────────

@st.cache_resource
def get_supabase_client():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
    except KeyError:
        st.error(
            "Supabase credentials not found in Streamlit secrets. "
            "Add a [supabase] section with 'url' and 'key' under "
            "Settings → Secrets."
        )
        st.stop()
    return create_client(url, key)


TABLE_NAME = "vahan_rto_data"


# ── Data loading (cached, with manual refresh) ─────────────────────────────────

@st.cache_data(ttl=600)
def load_data(table_name: str) -> pd.DataFrame:
    """
    Pull all rows from Supabase in pages (PostgREST default caps a
    single request's row count, so for larger datasets we page through
    using range headers until no more rows come back.
    """
    client = get_supabase_client()
    page_size = 1000
    all_rows = []
    start = 0

    while True:
        resp = (
            client.table(table_name)
            .select("*")
            .range(start, start + page_size - 1)
            .execute()
        )
        batch = resp.data
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    return df


# ── Load data ───────────────────────────────────────────────────────────────

col_refresh, _ = st.columns([1, 5])
with col_refresh:
    if st.button("🔄 Refresh data"):
        st.cache_data.clear()

with st.spinner("Loading data from Supabase…"):
    df = load_data(TABLE_NAME)

if df.empty:
    st.warning("No data found in the table yet. Upload data via the loader page first.")
    st.stop()

st.success(f"Loaded {len(df):,} rows covering {df['rto'].nunique()} RTOs, "
           f"{df['year'].nunique()} years, {df['category_group'].nunique()} category groups.")


# ── Filters ───────────────────────────────────────────────────────────────────

st.subheader("Filters")

filter_col_state, filter_col0, filter_col1, filter_col2, filter_col3 = st.columns(5)

with filter_col_state:
    state_options = sorted(df["state"].dropna().unique().tolist())
    selected_state = st.selectbox("State", options=["(All States)"] + state_options)

with filter_col0:
    dimension_options = sorted(df["dimension_name"].dropna().unique().tolist())
    default_idx = dimension_options.index("Vehicle Class") if "Vehicle Class" in dimension_options else 0
    selected_dimension = st.selectbox("Dimension", options=dimension_options, index=default_idx,
                                       help="Which Y-Axis dimension to view (Vehicle Class, Maker, etc.)")

# RTO options narrow down to whichever state is selected
rto_source_df = df if selected_state == "(All States)" else df[df["state"] == selected_state]

with filter_col1:
    rto_options = sorted(rto_source_df["rto"].dropna().unique().tolist())
    selected_rto = st.selectbox("RTO", options=["(All RTOs)"] + rto_options)

with filter_col2:
    category_options = sorted(df["category_group"].dropna().unique().tolist())
    selected_category = st.selectbox("Vehicle Category Group", options=["(All Categories)"] + category_options)

with filter_col3:
    dim_value_options = sorted(
        df[df["dimension_name"] == selected_dimension]["dimension_value"].dropna().unique().tolist()
    )
    selected_dim_value = st.selectbox(
        selected_dimension,
        options=[f"(All {selected_dimension})"] + dim_value_options
    )

# Apply filters
filtered_df = df[df["dimension_name"] == selected_dimension].copy()
if selected_state != "(All States)":
    filtered_df = filtered_df[filtered_df["state"] == selected_state]
if selected_rto != "(All RTOs)":
    filtered_df = filtered_df[filtered_df["rto"] == selected_rto]
if selected_category != "(All Categories)":
    filtered_df = filtered_df[filtered_df["category_group"] == selected_category]
if selected_dim_value != f"(All {selected_dimension})":
    filtered_df = filtered_df[filtered_df["dimension_value"] == selected_dim_value]

# Only sum the TOTAL sub-column for headline totals (avoids double-counting
# sub-type breakdowns like 4WIC/LMV/MMV/HMV alongside their own TOTAL row)
totals_df = filtered_df[filtered_df["sub_column"].str.upper() == "TOTAL"].copy()

if totals_df.empty:
    st.info(
        "No 'TOTAL' rows match this filter combination — showing all matching "
        "sub-columns instead (this can happen if you've filtered down to a "
        "specific sub-type that has no TOTAL row of its own)."
    )
    totals_df = filtered_df.copy()


# ── Summary table: State | RTO | Dimension Value | Category Group | Count ────

st.subheader("Summary Table")

show_breakdown = st.checkbox(
    "Show sub-column breakdown (e.g. 4WIC / LMV / MMV / HMV) instead of totals only",
    value=False,
)

if show_breakdown:
    st.caption(
        f"Vehicle counts by State, RTO, {selected_dimension}, and Category Group, "
        "broken down by sub-column (summed across all years currently in scope)."
    )

    # Pivot the full filtered data (not just TOTAL rows) so each sub_column
    # becomes its own column — e.g. 4WIC, LMV, MMV, HMV, TOTAL side by side.
    pivot_source = filtered_df.copy()

    summary_table = (
        pivot_source
        .pivot_table(
            index=["state", "rto", "dimension_value", "category_group"],
            columns="sub_column",
            values="value",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
        .rename(columns={
            "state": "State",
            "rto": "RTO",
            "dimension_value": selected_dimension,
            "category_group": "Vehicle Group",
        })
    )

    # Put TOTAL as the last column if present, for readability
    fixed_cols = ["State", "RTO", selected_dimension, "Vehicle Group"]
    sub_cols = [c for c in summary_table.columns if c not in fixed_cols]
    if "TOTAL" in sub_cols:
        sub_cols = [c for c in sub_cols if c != "TOTAL"] + ["TOTAL"]
    summary_table = summary_table[fixed_cols + sub_cols]

    sort_by_col = "TOTAL" if "TOTAL" in summary_table.columns else (sub_cols[0] if sub_cols else None)
    if sort_by_col:
        summary_table = summary_table.sort_values(
            ["State", "RTO", sort_by_col], ascending=[True, True, False]
        )

else:
    st.caption(
        f"Total vehicle counts by State, RTO, {selected_dimension}, and Category Group "
        "(summed across all years currently in scope for the filters above)."
    )

    summary_table = (
        totals_df.groupby(["state", "rto", "dimension_value", "category_group"], as_index=False)["value"]
        .sum()
        .rename(columns={
            "state": "State",
            "rto": "RTO",
            "dimension_value": selected_dimension,
            "category_group": "Vehicle Group",
            "value": "Count",
        })
        .sort_values(["State", "RTO", "Count"], ascending=[True, True, False])
    )

if summary_table.empty:
    st.info("No data matches the current filter selection.")
else:
    st.dataframe(summary_table, use_container_width=True, hide_index=True)

    summary_csv = summary_table.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download summary table as CSV",
        data=summary_csv,
        file_name="rto_summary_table.csv",
        mime="text/csv",
        key="summary_download",
    )


# ── Year-wise bar chart ─────────────────────────────────────────────────────

st.subheader("Year-wise Totals")

yearly_totals = (
    totals_df.groupby("year", as_index=False)["value"]
    .sum()
    .sort_values("year")
)

if yearly_totals.empty:
    st.info("No data matches the current filter selection.")
else:
    st.bar_chart(yearly_totals.set_index("year")["value"], use_container_width=True)

    with st.expander("View underlying year-wise totals (table)"):
        st.dataframe(yearly_totals.rename(columns={"year": "Year", "value": "Total Vehicles"}),
                     use_container_width=True, hide_index=True)


# ── Detailed table ───────────────────────────────────────────────────────────

st.subheader("Detailed Data")

display_cols = ["state", "rto", "year", "category_group", "dimension_name", "dimension_value", "sub_column", "value"]
display_df = filtered_df[display_cols].rename(columns={
    "state": "State",
    "rto": "RTO",
    "year": "Year",
    "category_group": "Category Group",
    "dimension_name": "Dimension",
    "dimension_value": selected_dimension,
    "sub_column": "Sub Column",
    "value": "Value",
})

st.dataframe(
    display_df.sort_values(["Year", "Category Group", selected_dimension]),
    use_container_width=True,
    hide_index=True,
)

st.caption(f"Showing {len(display_df):,} rows for current filter selection.")

# Download filtered data
csv_bytes = display_df.to_csv(index=False).encode("utf-8")
st.download_button(
    "⬇️ Download filtered data as CSV",
    data=csv_bytes,
    file_name="rto_data_filtered.csv",
    mime="text/csv",
)
