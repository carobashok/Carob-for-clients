import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px

from utils.extractor import extract_pdf_text
from utils.annual_extractor import parse_annual_with_claude, build_annual_rows
from utils.db import fetch_existing_annual_keys, upsert_annual_rows, fetch_all_annual_rows, CATEGORY_ORDER

st.set_page_config(page_title="Annual Data — FADA Pulse", page_icon="🗓️", layout="wide")
st.title("🗓️ Annual (FY) data")

# ============================================================
# Upload
# ============================================================
st.subheader("Upload a FY press release / summary")
st.caption(
    "Most FADA annual releases show the current FY and previous FY side by side — "
    "one upload will capture both years, plus any sub-category rows (e.g. LCV/MCV/HCV) "
    "wherever they're present in the table."
)

uploaded_file = st.file_uploader("Drop a FADA annual PDF", type=["pdf"], key="annual_pdf")

if uploaded_file is not None:
    if st.session_state.get("last_annual_upload") != uploaded_file.name:
        st.session_state.pop("extracted_annual_rows", None)
        st.session_state["last_annual_upload"] = uploaded_file.name

    if "extracted_annual_rows" not in st.session_state:
        with st.spinner("Reading PDF..."):
            pdf_text = extract_pdf_text(uploaded_file)
        with st.spinner("Extracting fiscal year data..."):
            try:
                parsed = parse_annual_with_claude(pdf_text)
                rows = build_annual_rows(parsed, uploaded_file.name)
                st.session_state["extracted_annual_rows"] = rows
            except ValueError as e:
                st.error(f"Extraction failed: {e}")
                st.stop()

    rows = st.session_state["extracted_annual_rows"]
    fiscal_years = sorted({r["fiscal_year"] for r in rows})
    st.success(f"Extracted data for: {', '.join(fiscal_years)}")

    existing = fetch_existing_annual_keys(fiscal_years)
    existing_by_key = {(r["fiscal_year"], r["category"], r["subcategory"]): r for r in existing}

    df = pd.DataFrame(rows)
    df["status"] = df.apply(
        lambda r: "⚠️ Already exists"
        if (r["fiscal_year"], r["category"], r["subcategory"]) in existing_by_key
        else "New",
        axis=1,
    )
    display_df = df.copy()
    display_df["subcategory"] = display_df["subcategory"].replace("", "—")
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    conflicts = [
        r for r in rows
        if (r["fiscal_year"], r["category"], r["subcategory"]) in existing_by_key
    ]
    if conflicts:
        st.warning(f"{len(conflicts)} row(s) already exist. Review before overwriting.")
        compare_data = []
        for r in conflicts:
            key = (r["fiscal_year"], r["category"], r["subcategory"])
            existing_row = existing_by_key[key]
            compare_data.append(
                {
                    "fiscal_year": r["fiscal_year"],
                    "category": r["category"],
                    "subcategory": r["subcategory"] or "—",
                    "existing_units": existing_row["current_year_units"],
                    "existing_source": existing_row.get("source_file"),
                    "new_units": r["current_year_units"],
                    "match": existing_row["current_year_units"] == r["current_year_units"],
                }
            )
        st.dataframe(pd.DataFrame(compare_data), use_container_width=True, hide_index=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Upsert to database", type="primary"):
            count = upsert_annual_rows(rows)
            st.success(f"Upserted {count} rows.")
            st.session_state.pop("extracted_annual_rows", None)
    with col2:
        if conflicts and st.button("Skip conflicting rows, add only new"):
            key_set = set(existing_by_key.keys())
            new_only = [
                r for r in rows
                if (r["fiscal_year"], r["category"], r["subcategory"]) not in key_set
            ]
            count = upsert_annual_rows(new_only)
            st.success(f"Upserted {count} new rows (skipped {len(conflicts)} conflicts).")
            st.session_state.pop("extracted_annual_rows", None)

st.divider()

# ============================================================
# Browse
# ============================================================
st.subheader("Browse annual data")

with st.spinner("Loading data..."):
    all_rows = fetch_all_annual_rows()

if not all_rows:
    st.info("No annual data yet — upload a PDF above to get started.")
    st.stop()

all_df = pd.DataFrame(all_rows)
all_df["subcategory"] = all_df["subcategory"].fillna("")

col1, col2 = st.columns(2)
with col1:
    show_subcategories = st.checkbox("Show sub-category rows", value=False)
with col2:
    categories = st.multiselect(
        "Categories",
        options=[c for c in CATEGORY_ORDER if c in all_df["category"].unique()],
        default=list(all_df["category"].unique()),
    )

filtered = all_df[all_df["category"].isin(categories)]
if not show_subcategories:
    filtered = filtered[filtered["subcategory"] == ""]

display_filtered = filtered[["fiscal_year", "category", "subcategory", "current_year_units", "source_file"]].copy()
display_filtered["subcategory"] = display_filtered["subcategory"].replace("", "—")
st.dataframe(display_filtered, use_container_width=True, hide_index=True)

st.download_button(
    "Download filtered CSV",
    data=display_filtered.to_csv(index=False),
    file_name="fada_annual_summary_filtered.csv",
    mime="text/csv",
)

# ============================================================
# Chart — parent-level categories only
# ============================================================
st.subheader("Trend across fiscal years")
parent_df = all_df[all_df["subcategory"] == ""].sort_values("fiscal_year")

total_df = parent_df[parent_df["category"] == "Total"]
if not total_df.empty:
    fig = px.bar(total_df, x="fiscal_year", y="current_year_units", title="Total vehicles")
    fig.update_xaxes(type="category", title="Fiscal Year")
    fig.update_yaxes(title="Units", tickformat=",")
    fig.update_traces(hovertemplate="%{x}<br>%{y:,}<extra></extra>")
    fig.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)

other_categories = [c for c in CATEGORY_ORDER if c != "Total" and c in parent_df["category"].unique()]
for category in other_categories:
    cat_df = parent_df[parent_df["category"] == category]
    fig = px.bar(cat_df, x="fiscal_year", y="current_year_units", title=category)
    fig.update_xaxes(type="category", title="Fiscal Year")
    fig.update_yaxes(title="Units", tickformat=",")
    fig.update_traces(hovertemplate="%{x}<br>%{y:,}<extra></extra>")
    fig.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True)
