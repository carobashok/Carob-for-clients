import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px

from utils.db import fetch_all_rows, CATEGORY_ORDER

st.set_page_config(page_title="Dashboard — FADA Pulse", page_icon="📈", layout="wide")
st.title("📈 Month-wise trends")

with st.spinner("Loading data..."):
    rows = fetch_all_rows()

if not rows:
    st.info("No data yet — upload a PDF on the Upload page to get started.")
    st.stop()

df = pd.DataFrame(rows)
df = df[["month", "category", "current_month_units"]].sort_values("month")

months_present = sorted(df["month"].unique())
st.caption(
    f"{len(months_present)} months loaded: {months_present[0]} to {months_present[-1]} "
    f"(not all months in between are necessarily present — see Data Table for the full list)"
)


def trend_chart(data: pd.DataFrame, title: str) -> None:
    """Line+marker chart on a categorical month axis, so gaps in coverage
    don't get visually smoothed over as if data were continuous."""
    data = data.copy()
    data["month_label"] = pd.to_datetime(data["month"], format="%Y-%m").dt.strftime("%b-%y")

    fig = px.line(
        data,
        x="month_label",
        y="current_month_units",
        markers=True,
        title=title,
    )
    fig.update_xaxes(
        type="category",
        title="Month",
        categoryorder="array",
        categoryarray=data["month_label"].tolist(),  # data is pre-sorted chronologically
    )
    fig.update_yaxes(title="Units", tickformat=",")
    fig.update_traces(hovertemplate="%{x}<br>%{y:,}<extra></extra>")
    fig.update_layout(height=400, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)


# --- Total vehicles trend, full width ---
total_df = df[df["category"] == "Total"]
if not total_df.empty:
    trend_chart(total_df, "Total vehicles")
else:
    st.warning("No 'Total' category rows found yet.")

# --- Category-wise trends, two per row ---
st.subheader("Category-wise trends")

other_categories = [c for c in CATEGORY_ORDER if c != "Total" and c in df["category"].unique()]

for category in other_categories:
    cat_df = df[df["category"] == category]
    trend_chart(cat_df, category)

missing_categories = [c for c in CATEGORY_ORDER if c not in df["category"].unique() and c != "Total"]
if missing_categories:
    st.caption(f"No data yet for: {', '.join(missing_categories)}")
