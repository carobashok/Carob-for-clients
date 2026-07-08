import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px

from utils.db import get_client, fetch_all_oem_rows
from utils.oem_extractor import CATEGORY_LABELS

TABLE = "industry_production_summary"

st.set_page_config(page_title="Production — FADA Pulse", page_icon="🏭", layout="wide")
st.title("🏭 Production data (TMA / SIAM)")
st.caption(
    "Factory-side production and wholesale dispatch — a genuinely different measurement "
    "from the FADA retail pages (dealer registrations). Don't read these two series as "
    "directly comparable without accounting for that gap."
)


@st.cache_data(ttl=300)
def fetch_all_production_rows() -> list[dict]:
    """Fetch every row from industry_production_summary, paginating past
    Supabase's 1000-row default cap."""
    client = get_client()
    all_rows = []
    page_size = 1000
    start = 0
    while True:
        result = (
            client.table(TABLE)
            .select("*")
            .order("month")
            .range(start, start + page_size - 1)
            .execute()
        )
        batch = result.data or []
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return all_rows


with st.spinner("Loading data..."):
    rows = fetch_all_production_rows()

if not rows:
    st.info("No production data yet — upload a TMA/SIAM workbook on the Production Upload page to get started.")
    st.stop()

df = pd.DataFrame(rows)
df["month"] = pd.to_datetime(df["month"])
df = df.sort_values("month")
df["month_display"] = df["month"].dt.strftime("%b-%y")

st.caption(
    f"{df['month'].nunique()} months loaded across {df['category'].nunique()} categor"
    f"{'y' if df['category'].nunique() == 1 else 'ies'} "
    f"({df['month'].min().strftime('%b-%y')} to {df['month'].max().strftime('%b-%y')})."
)

categories = sorted(df["category"].unique())
selected_category = st.selectbox("Category", options=categories, key="prod_category")

cat_df = df[df["category"] == selected_category].sort_values("month")
month_order = cat_df["month_display"].tolist()

sources = sorted(cat_df["source"].dropna().unique())
st.caption(f"Source: {', '.join(sources) if sources else 'unspecified'}")

# ============================================================
# Production vs Domestic Sales vs Exports — FY-wise
# ============================================================


def to_fiscal_year(month: pd.Timestamp) -> str:
    """Indian FY convention: Apr-Mar. Apr'22-Mar'23 -> FY23."""
    fy_end_year = month.year + 1 if month.month >= 4 else month.year
    return f"FY{str(fy_end_year)[-2:]}"


def fy_sort_key(fy: str) -> int:
    digits = "".join(ch for ch in fy if ch.isdigit())
    return int(digits) if digits else 0


cat_df = cat_df.copy()
cat_df["fiscal_year"] = cat_df["month"].apply(to_fiscal_year)

fy_agg = cat_df.groupby("fiscal_year").agg(
    production=("production", "sum"),
    domestic_sales=("domestic_sales", "sum"),
    exports=("exports", "sum"),
    month_count=("month", "nunique"),
).reset_index()

# A full FY has 12 months of data; anything less (first year in coverage,
# or the current year still in progress) gets flagged with an asterisk
# rather than silently plotted as if it were a complete year.
fy_agg["is_partial"] = fy_agg["month_count"] < 12
fy_agg["fy_label"] = fy_agg["fiscal_year"] + fy_agg["is_partial"].map({True: "*", False: ""})

fy_order_keys = sorted(fy_agg["fiscal_year"].unique(), key=fy_sort_key)
fy_label_order = [
    fy_agg.loc[fy_agg["fiscal_year"] == fy, "fy_label"].iloc[0] for fy in fy_order_keys
]

fy_plot_df = fy_agg.melt(
    id_vars=["fy_label"],
    value_vars=["production", "domestic_sales", "exports"],
    var_name="series",
    value_name="units",
)
series_labels = {"production": "Production", "domestic_sales": "Domestic Sales", "exports": "Exports"}
fy_plot_df["series"] = fy_plot_df["series"].map(series_labels)

fig = px.bar(
    fy_plot_df,
    x="fy_label",
    y="units",
    color="series",
    barmode="group",
    title=f"{selected_category} — Production, Domestic Sales & Exports (FY-wise)",
)
fig.update_xaxes(type="category", title="Fiscal Year", categoryorder="array", categoryarray=fy_label_order)
fig.update_yaxes(title="Units", tickformat=",")
fig.update_traces(hovertemplate="%{x}<br>%{y:,}<extra></extra>")
fig.update_layout(height=450, margin=dict(l=10, r=10, t=40, b=10), legend_title="Series")
st.plotly_chart(fig, use_container_width=True)

if fy_agg["is_partial"].any():
    partial_years = fy_agg.loc[fy_agg["is_partial"], "fiscal_year"].tolist()
    st.caption(f"* Partial year — fewer than 12 months of data loaded so far: {', '.join(partial_years)}")

# ============================================================
# Total Sales (incl. exports), as reported by source — month-wise,
# windowed 12 months at a time so the axis stays readable as data grows
# ============================================================
st.subheader(f"{selected_category} — Production, Total Sales & Exports (month-wise)")

window_size = 12
n_months = len(cat_df)
max_start = max(n_months - window_size, 0)

window_key = f"prod_window_start_{selected_category}"
if window_key not in st.session_state:
    st.session_state[window_key] = max_start  # default: latest 12 months

# Clamp in case the underlying data changed (new upload) since last run
st.session_state[window_key] = min(max(st.session_state[window_key], 0), max_start)

nav_prev, nav_label, nav_next = st.columns([1, 3, 1])
with nav_prev:
    if st.button("⬅ Previous 12", disabled=st.session_state[window_key] <= 0, key=f"prod_prev_{selected_category}"):
        st.session_state[window_key] = max(st.session_state[window_key] - window_size, 0)
with nav_next:
    if st.button(
        "Next 12 ➡", disabled=st.session_state[window_key] >= max_start, key=f"prod_next_{selected_category}"
    ):
        st.session_state[window_key] = min(st.session_state[window_key] + window_size, max_start)

start_idx = st.session_state[window_key]
window_df = cat_df.iloc[start_idx: start_idx + window_size]

with nav_label:
    if not window_df.empty:
        st.markdown(
            f"<div style='text-align:center; padding-top:0.5rem'>"
            f"<b>{window_df['month_display'].iloc[0]} to {window_df['month_display'].iloc[-1]}</b>"
            f" ({n_months} months total)</div>",
            unsafe_allow_html=True,
        )

window_plot_df = window_df.melt(
    id_vars=["month_display"],
    value_vars=["production", "total_sales", "exports"],
    var_name="series",
    value_name="units",
)
window_series_labels = {"production": "Production", "total_sales": "Total Sales (incl. Exports)", "exports": "Exports"}
window_plot_df["series"] = window_plot_df["series"].map(window_series_labels)

fig2 = px.bar(
    window_plot_df,
    x="month_display",
    y="units",
    color="series",
    barmode="group",
    title=None,
)
fig2.update_xaxes(
    type="category", title="Month", categoryorder="array", categoryarray=window_df["month_display"].tolist()
)
fig2.update_yaxes(title="Units", tickformat=",")
fig2.update_traces(hovertemplate="%{x}<br>%{y:,}<extra></extra>")
fig2.update_layout(height=400, margin=dict(l=10, r=10, t=20, b=10), legend_title="Series")
st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ============================================================
# OEM-wise retail data (FADA) — same category, for cross-reference
# alongside the TMA/SIAM production series above. Note this is retail
# (dealer registrations, FY granularity) vs. production (factory dispatch,
# monthly) — different measurements, shown side by side, not merged.
# ============================================================
st.subheader(f"{selected_category} — OEM-wise retail data (FADA)")

with st.spinner("Loading OEM data..."):
    all_oem_rows = fetch_all_oem_rows()

if not all_oem_rows:
    st.info("No FADA OEM data loaded yet — upload it on the Upload page's OEM tab.")
else:
    oem_df = pd.DataFrame(all_oem_rows)
    oem_df["parent_oem"] = oem_df["parent_oem"].fillna("")
    oem_df = oem_df[oem_df["category"] == selected_category]

    if oem_df.empty:
        st.info(
            f"No FADA OEM data loaded yet for category '{selected_category}' "
            f"— upload it on the Upload page's OEM tab."
        )
    else:
        oem_top_level = oem_df[oem_df["parent_oem"] == ""]  # exclude sub-entities to avoid double counting
        oem_fy_order = sorted(oem_top_level["fiscal_year"].unique(), key=fy_sort_key)

        oem_totals = (
            oem_top_level.groupby("oem_name")["current_year_units"].sum().sort_values(ascending=False)
        )
        oem_names = list(oem_totals.index)

        col1, col2, col3 = st.columns([1.2, 2, 1.2])
        with col1:
            oem_top_n = st.selectbox(
                "Show top", options=[5, 8, 10, 15, "All"], index=1, key="prod_oem_top_n"
            )
        with col2:
            oem_manual_pick = st.multiselect(
                "Or pick specific OEMs (overrides Top N)",
                options=oem_names,
                default=[],
                key="prod_oem_manual_pick",
            )
        with col3:
            oem_show_share = st.checkbox("Show as % market share", value=False, key="prod_oem_as_share")

        if oem_manual_pick:
            oem_selected = oem_manual_pick
        elif oem_top_n == "All":
            oem_selected = oem_names
        else:
            oem_selected = list(oem_totals.head(oem_top_n).index)

        oem_trend = oem_top_level[oem_top_level["oem_name"].isin(oem_selected)].copy()

        if oem_show_share:
            oem_fy_totals = oem_top_level.groupby("fiscal_year")["current_year_units"].sum()
            oem_trend["value"] = oem_trend.apply(
                lambda r: (r["current_year_units"] / oem_fy_totals[r["fiscal_year"]] * 100)
                if oem_fy_totals[r["fiscal_year"]] else 0,
                axis=1,
            )
            oem_y_col, oem_y_title, oem_hover = "value", "Market share (%)", "%{x}<br>%{y:.2f}%<extra></extra>"
        else:
            oem_trend["value"] = oem_trend["current_year_units"]
            oem_y_col, oem_y_title, oem_hover = "value", "Units", "%{x}<br>%{y:,}<extra></extra>"

        oem_trend["fiscal_year"] = pd.Categorical(oem_trend["fiscal_year"], categories=oem_fy_order, ordered=True)
        oem_trend = oem_trend.sort_values("fiscal_year")

        oem_fig = px.line(
            oem_trend, x="fiscal_year", y=oem_y_col, color="oem_name", markers=True,
        )
        oem_fig.update_xaxes(
            type="category", title="Fiscal Year", categoryorder="array", categoryarray=oem_fy_order
        )
        oem_fig.update_yaxes(title=oem_y_title, tickformat="," if not oem_show_share else None)
        oem_fig.update_traces(hovertemplate=oem_hover)
        oem_fig.update_layout(height=450, margin=dict(l=10, r=10, t=20, b=10), legend_title="OEM")
        st.plotly_chart(oem_fig, use_container_width=True)

        if not oem_manual_pick and oem_top_n != "All" and len(oem_names) > oem_top_n:
            st.caption(f"Showing top {oem_top_n} of {len(oem_names)} OEMs by total volume.")

        oem_pivot = oem_top_level.pivot_table(
            index="oem_name", columns="fiscal_year", values="current_year_units", aggfunc="sum", fill_value=0
        )
        oem_pivot = oem_pivot[oem_fy_order]
        oem_pivot["Total"] = oem_pivot.sum(axis=1)
        oem_pivot = oem_pivot.sort_values("Total", ascending=False).drop(columns="Total")
        st.dataframe(oem_pivot, use_container_width=True)

st.divider()


st.subheader("Browse production data")

display_df = cat_df[
    ["month_display", "category", "production", "total_sales", "exports", "domestic_sales", "source", "source_file"]
].rename(columns={"month_display": "month"})
st.dataframe(display_df, use_container_width=True, hide_index=True)

st.download_button(
    "Download filtered CSV",
    data=display_df.to_csv(index=False),
    file_name=f"industry_production_{selected_category}.csv",
    mime="text/csv",
)
