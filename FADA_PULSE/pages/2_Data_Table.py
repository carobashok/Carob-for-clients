import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd

from utils.db import fetch_all_rows, CATEGORY_ORDER

st.set_page_config(page_title="Data Table — FADA Pulse", page_icon="📊", layout="wide")
st.title("📊 FADA data")

with st.spinner("Loading data..."):
    rows = fetch_all_rows()

if not rows:
    st.info("No data yet — upload a PDF on the Upload page to get started.")
    st.stop()

df = pd.DataFrame(rows)
df = df[["month", "category", "current_month_units", "source_file"]]

# Filters
col1, col2, col3 = st.columns([2, 2, 3])
with col1:
    months = sorted(df["month"].unique())
    month_range = st.select_slider(
        "Month range", options=months, value=(months[0], months[-1])
    )
with col2:
    categories = st.multiselect(
        "Categories",
        options=[c for c in CATEGORY_ORDER if c in df["category"].unique()],
        default=list(df["category"].unique()),
    )
with col3:
    search = st.text_input("Search source file")

filtered = df[
    (df["month"] >= month_range[0])
    & (df["month"] <= month_range[1])
    & (df["category"].isin(categories))
]
if search:
    filtered = filtered[filtered["source_file"].str.contains(search, case=False, na=False)]

filtered = filtered.sort_values(
    by=["month", "category"],
    key=lambda col: col.map({c: i for i, c in enumerate(CATEGORY_ORDER)}) if col.name == "category" else col,
)

st.caption(f"{len(filtered)} of {len(df)} rows")
st.dataframe(filtered, use_container_width=True, hide_index=True)

st.download_button(
    "Download filtered CSV",
    data=filtered.to_csv(index=False),
    file_name="fada_category_summary_filtered.csv",
    mime="text/csv",
)

st.subheader("Months loaded so far")
months_present = sorted(df["month"].unique())
st.write(", ".join(months_present))
