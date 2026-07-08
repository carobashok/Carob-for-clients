import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px

from utils.db import get_client

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
# Total Sales (incl. exports), as reported by source
# ============================================================
fig2 = px.bar(
    cat_df,
    x="month_display",
    y="total_sales",
    title=f"{selected_category} — Total Sales (incl. Exports)",
)
fig2.update_xaxes(type="category", title="Month", categoryorder="array", categoryarray=month_order)
fig2.update_yaxes(title="Units", tickformat=",")
fig2.update_traces(hovertemplate="%{x}<br>%{y:,}<extra></extra>")
fig2.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10))
st.plotly_chart(fig2, use_container_width=True)

# ============================================================
# Browse
# ============================================================
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
