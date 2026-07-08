import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px

from utils.extractor import extract_pdf_text
from utils.oem_extractor import parse_oem_with_claude, build_oem_rows, OEM_CATEGORIES
from utils.db import fetch_existing_oem_keys, upsert_oem_rows, fetch_all_oem_rows

st.set_page_config(page_title="OEM Data — FADA Pulse", page_icon="🏭", layout="wide")
st.title("🏭 OEM (manufacturer) data")

# ============================================================
# Upload
# ============================================================
st.subheader("Upload a category OEM table")
st.caption(
    "e.g. \"Tractor OEM\", \"Three-Wheeler OEM\" — the category is inferred from the "
    "table title. Current + previous FY are both captured in one upload, same as the "
    "Annual page."
)

uploaded_file = st.file_uploader("Drop a FADA OEM table PDF", type=["pdf"], key="oem_pdf")

if uploaded_file is not None:
    if st.session_state.get("last_oem_upload") != uploaded_file.name:
        st.session_state.pop("extracted_oem_rows", None)
        st.session_state["last_oem_upload"] = uploaded_file.name

    if "extracted_oem_rows" not in st.session_state:
        with st.spinner("Reading PDF..."):
            pdf_text = extract_pdf_text(uploaded_file)
        with st.spinner("Extracting OEM data (scanning for all category tables)..."):
            try:
                parsed = parse_oem_with_claude(pdf_text)
                rows = build_oem_rows(parsed, uploaded_file.name)
                st.session_state["extracted_oem_rows"] = rows
                st.session_state["extracted_oem_categories"] = [
                    t["category"] for t in parsed["tables"]
                ]
            except ValueError as e:
                st.error(f"Extraction failed: {e}")
                st.stop()

    rows = st.session_state["extracted_oem_rows"]
    categories_found = st.session_state["extracted_oem_categories"]
    fiscal_years = sorted({r["fiscal_year"] for r in rows})
    st.success(
        f"Extracted **{', '.join(categories_found)}** OEM data for: {', '.join(fiscal_years)} "
        f"({len(rows)} rows total)"
    )

    existing = fetch_existing_oem_keys(fiscal_years)
    existing_by_key = {
        (r["fiscal_year"], r["category"], r["oem_name"], r["parent_oem"]): r for r in existing
    }

    df = pd.DataFrame(rows)
    df["status"] = df.apply(
        lambda r: "⚠️ Already exists"
        if (r["fiscal_year"], r["category"], r["oem_name"], r["parent_oem"]) in existing_by_key
        else "New",
        axis=1,
    )

    preview_category = st.selectbox(
        "Preview category", options=["All"] + categories_found, key="oem_preview_category"
    )
    display_df = df if preview_category == "All" else df[df["category"] == preview_category]
    display_df = display_df.copy()
    display_df["parent_oem"] = display_df["parent_oem"].replace("", "—")
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    conflicts = [
        r for r in rows
        if (r["fiscal_year"], r["category"], r["oem_name"], r["parent_oem"]) in existing_by_key
    ]
    if conflicts:
        st.warning(f"{len(conflicts)} row(s) already exist. Review before overwriting.")
        compare_data = []
        for r in conflicts:
            key = (r["fiscal_year"], r["category"], r["oem_name"], r["parent_oem"])
            existing_row = existing_by_key[key]
            compare_data.append(
                {
                    "fiscal_year": r["fiscal_year"],
                    "oem_name": r["oem_name"],
                    "parent_oem": r["parent_oem"] or "—",
                    "existing_units": existing_row["current_year_units"],
                    "new_units": r["current_year_units"],
                    "match": existing_row["current_year_units"] == r["current_year_units"],
                }
            )
        st.dataframe(pd.DataFrame(compare_data), use_container_width=True, hide_index=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Upsert to database", type="primary"):
            count = upsert_oem_rows(rows)
            st.success(f"Upserted {count} rows.")
            st.session_state.pop("extracted_oem_rows", None)
    with col2:
        if conflicts and st.button("Skip conflicting rows, add only new"):
            key_set = set(existing_by_key.keys())
            new_only = [
                r for r in rows
                if (r["fiscal_year"], r["category"], r["oem_name"], r["parent_oem"]) not in key_set
            ]
            count = upsert_oem_rows(new_only)
            st.success(f"Upserted {count} new rows (skipped {len(conflicts)} conflicts).")
            st.session_state.pop("extracted_oem_rows", None)

st.divider()

# ============================================================
# Browse
# ============================================================
st.subheader("Browse OEM data")

with st.spinner("Loading data..."):
    all_rows = fetch_all_oem_rows()

if not all_rows:
    st.info("No OEM data yet — upload a table above to get started.")
    st.stop()

all_df = pd.DataFrame(all_rows)
all_df["parent_oem"] = all_df["parent_oem"].fillna("")

col1, col2 = st.columns(2)
with col1:
    category_filter = st.selectbox(
        "Category",
        options=sorted(all_df["category"].unique()),
    )
with col2:
    fy_options = sorted(all_df["fiscal_year"].unique())
    fy_filter = st.selectbox("Fiscal year", options=fy_options, index=len(fy_options) - 1)

show_sub_entities = st.checkbox("Show sub-entity rows", value=False)

filtered = all_df[(all_df["category"] == category_filter) & (all_df["fiscal_year"] == fy_filter)]
if not show_sub_entities:
    filtered = filtered[filtered["parent_oem"] == ""]

filtered = filtered.sort_values("current_year_units", ascending=False)
category_total = filtered["current_year_units"].sum()
filtered_display = filtered.copy()
filtered_display["market_share_%"] = (
    filtered_display["current_year_units"] / category_total * 100
).round(2) if category_total else 0
filtered_display["parent_oem"] = filtered_display["parent_oem"].replace("", "—")

st.dataframe(
    filtered_display[["oem_name", "parent_oem", "current_year_units", "market_share_%", "source_file"]],
    use_container_width=True,
    hide_index=True,
)

st.download_button(
    "Download filtered CSV",
    data=filtered_display.to_csv(index=False),
    file_name=f"fada_oem_{category_filter}_{fy_filter}.csv",
    mime="text/csv",
)

# Market share pie for the selected category + FY (top-level OEMs only)
top_level = filtered[filtered["parent_oem"] == ""].sort_values("current_year_units", ascending=False)
if not top_level.empty:
    fig = px.pie(
        top_level,
        names="oem_name",
        values="current_year_units",
        title=f"{category_filter} market share — {fy_filter}",
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(height=500)
    st.plotly_chart(fig, use_container_width=True)
