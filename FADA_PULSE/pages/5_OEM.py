import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px

from utils.extractor import extract_pdf_text
from utils.oem_extractor import parse_oem_with_claude, build_oem_rows, OEM_CATEGORIES, CATEGORY_LABELS
from utils.db import fetch_existing_oem_keys, upsert_oem_rows, fetch_all_oem_rows

st.set_page_config(page_title="OEM Data — FADA Pulse", page_icon="🏭", layout="wide")
st.title("🏭 OEM (manufacturer) data")

# ============================================================
# Upload
# ============================================================
st.subheader("Upload a category OEM table")
st.caption(
    "Pick the category first — the document may contain OEM tables for several "
    "categories, but only the one you select here will be extracted. Current + "
    "previous FY are both captured in one pass."
)

category_options = sorted(OEM_CATEGORIES)
selected_category = st.selectbox(
    "Category to extract",
    options=category_options,
    format_func=lambda c: f"{CATEGORY_LABELS[c]} ({c})",
    key="oem_category_select",
)

uploaded_file = st.file_uploader("Drop a FADA OEM table PDF", type=["pdf"], key="oem_pdf")

if uploaded_file is not None:
    cache_key = (uploaded_file.name, selected_category)
    if st.session_state.get("last_oem_upload_key") != cache_key:
        st.session_state.pop("extracted_oem_rows", None)
        st.session_state["last_oem_upload_key"] = cache_key

    if "extracted_oem_rows" not in st.session_state:
        with st.spinner("Reading PDF..."):
            pdf_text = extract_pdf_text(uploaded_file)
        with st.spinner(f"Extracting {CATEGORY_LABELS[selected_category]} OEM data..."):
            try:
                parsed = parse_oem_with_claude(pdf_text, selected_category)
                rows = build_oem_rows(parsed, uploaded_file.name)
                st.session_state["extracted_oem_rows"] = rows
            except ValueError as e:
                st.error(f"Extraction failed: {e}")
                st.stop()

    rows = st.session_state["extracted_oem_rows"]
    fiscal_years = sorted({r["fiscal_year"] for r in rows})
    st.success(
        f"Extracted **{CATEGORY_LABELS[selected_category]} ({selected_category})** OEM "
        f"data for: {', '.join(fiscal_years)} ({len(rows)} rows)"
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
    display_df = df.copy()
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
# Browse — trend + OEM x fiscal-year table, same layout regardless of scope
# ============================================================
st.subheader("OEM trends")

with st.spinner("Loading data..."):
    all_rows = fetch_all_oem_rows()

if not all_rows:
    st.info("No OEM data yet — upload a table above to get started.")
    st.stop()

all_df = pd.DataFrame(all_rows)
all_df["parent_oem"] = all_df["parent_oem"].fillna("")


def fy_sort_key(fy: str) -> int:
    """Sort 'FY23', 'FY26' etc. chronologically rather than alphabetically."""
    digits = "".join(ch for ch in fy if ch.isdigit())
    return int(digits) if digits else 0


category_filter = st.selectbox(
    "Category",
    options=["All"] + sorted(all_df["category"].unique()),
    format_func=lambda c: c if c == "All" else f"{CATEGORY_LABELS.get(c, c)} ({c})",
)

scope_df = all_df if category_filter == "All" else all_df[all_df["category"] == category_filter]
top_level = scope_df[scope_df["parent_oem"] == ""]  # exclude sub-entities to avoid double counting

fy_order = sorted(top_level["fiscal_year"].unique(), key=fy_sort_key)

# --- Overall trend ---
trend_df = (
    top_level.groupby("fiscal_year", as_index=False)["current_year_units"].sum()
)
trend_df["fiscal_year"] = pd.Categorical(trend_df["fiscal_year"], categories=fy_order, ordered=True)
trend_df = trend_df.sort_values("fiscal_year")

title = "Total units — all categories" if category_filter == "All" else f"Total units — {CATEGORY_LABELS.get(category_filter, category_filter)}"
fig = px.bar(trend_df, x="fiscal_year", y="current_year_units", title=title)
fig.update_xaxes(type="category", title="Fiscal Year", categoryorder="array", categoryarray=fy_order)
fig.update_yaxes(title="Units", tickformat=",")
fig.update_traces(hovertemplate="%{x}<br>%{y:,}<extra></extra>")
fig.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10))
st.plotly_chart(fig, use_container_width=True)

# --- OEM x fiscal-year table ---
st.subheader("OEM breakdown by fiscal year")

pivot = top_level.pivot_table(
    index="oem_name", columns="fiscal_year", values="current_year_units", aggfunc="sum", fill_value=0
)
pivot = pivot[fy_order]  # chronological column order
pivot["Total"] = pivot.sum(axis=1)
pivot = pivot.sort_values("Total", ascending=False).drop(columns="Total")

st.dataframe(pivot, use_container_width=True)

st.download_button(
    "Download OEM x FY table (CSV)",
    data=pivot.to_csv(),
    file_name=f"fada_oem_by_year_{category_filter}.csv",
    mime="text/csv",
)
