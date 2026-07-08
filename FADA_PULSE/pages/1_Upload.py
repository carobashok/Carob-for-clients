import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd

from utils.extractor import extract_pdf_text, parse_with_claude, build_rows
from utils.annual_extractor import parse_annual_with_claude, build_annual_rows
from utils.oem_extractor import parse_oem_with_claude, build_oem_rows, OEM_CATEGORIES, CATEGORY_LABELS
from utils.db import (
    fetch_existing_keys, upsert_rows,
    fetch_existing_annual_keys, upsert_annual_rows, fetch_all_annual_rows,
    fetch_existing_oem_keys, upsert_oem_rows, fetch_all_oem_rows,
    CATEGORY_ORDER,
)

st.set_page_config(page_title="Upload — FADA Pulse", page_icon="📤", layout="wide")
st.title("📤 Upload FADA data")

# Native st.tabs() loses its selection whenever a widget inside a tab
# (e.g. the OEM category dropdown) triggers a rerun — the whole script
# re-executes and the tab strip snaps back to the first tab. A session_state
# -backed radio doesn't have that problem, so we use one styled as tabs.
tab_labels = ["Monthly", "Annual (FY)", "OEM (manufacturer)"]
if "upload_active_tab" not in st.session_state:
    st.session_state["upload_active_tab"] = tab_labels[0]
active_tab = st.radio(
    "Data type",
    tab_labels,
    horizontal=True,
    key="upload_active_tab",
    label_visibility="collapsed",
)
st.divider()

# ============================================================
# MONTHLY TAB
# ============================================================
if active_tab == "Monthly":
    st.subheader("Upload a FADA press release")

    uploaded_file = st.file_uploader("Drop a FADA monthly PDF", type=["pdf"], key="monthly_pdf")

    if uploaded_file is not None:
        if st.session_state.get("last_uploaded_name") != uploaded_file.name:
            # New file — reset any previous extraction state
            st.session_state.pop("extracted_rows", None)
            st.session_state["last_uploaded_name"] = uploaded_file.name

        if "extracted_rows" not in st.session_state:
            with st.spinner("Reading PDF..."):
                pdf_text = extract_pdf_text(uploaded_file)
            with st.spinner("Extracting category data..."):
                try:
                    parsed = parse_with_claude(pdf_text)
                    rows = build_rows(parsed, uploaded_file.name)
                    st.session_state["extracted_rows"] = rows
                except ValueError as e:
                    st.error(f"Extraction failed: {e}")
                    st.stop()

        rows = st.session_state["extracted_rows"]
        month = rows[0]["month"] if rows else None
        st.subheader(f"Extracted data for {month}")

        # Check what's already in the DB for this month
        existing = fetch_existing_keys([month]) if month else []
        existing_by_cat = {r["category"]: r for r in existing}

        df = pd.DataFrame(rows)
        df["status"] = df["category"].apply(
            lambda c: "⚠️ Already exists" if c in existing_by_cat else "New"
        )

        st.dataframe(df, use_container_width=True, hide_index=True)

        conflicts = [r for r in rows if r["category"] in existing_by_cat]
        if conflicts:
            st.warning(
                f"{len(conflicts)} categor{'y' if len(conflicts)==1 else 'ies'} for "
                f"{month} already exist in the database. Review the comparison below "
                f"before overwriting."
            )
            compare_data = []
            for r in conflicts:
                existing_row = existing_by_cat[r["category"]]
                compare_data.append(
                    {
                        "category": r["category"],
                        "existing_units": existing_row["current_month_units"],
                        "existing_source": existing_row.get("source_file"),
                        "new_units": r["current_month_units"],
                        "new_source": r["source_file"],
                        "match": existing_row["current_month_units"] == r["current_month_units"],
                    }
                )
            st.dataframe(pd.DataFrame(compare_data), use_container_width=True, hide_index=True)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Upsert to database", type="primary", key="monthly_upsert"):
                count = upsert_rows(rows)
                st.success(f"Upserted {count} rows for {month}.")
                st.session_state.pop("extracted_rows", None)
        with col2:
            if conflicts and st.button("Skip conflicting rows, add only new", key="monthly_skip"):
                new_only = [r for r in rows if r["category"] not in existing_by_cat]
                count = upsert_rows(new_only)
                st.success(f"Upserted {count} new rows (skipped {len(conflicts)} conflicts).")
                st.session_state.pop("extracted_rows", None)

# ============================================================
# ANNUAL TAB
# ============================================================
elif active_tab == "Annual (FY)":
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
            if st.button("✅ Upsert to database", type="primary", key="annual_upsert"):
                count = upsert_annual_rows(rows)
                st.success(f"Upserted {count} rows.")
                st.session_state.pop("extracted_annual_rows", None)
        with col2:
            if conflicts and st.button("Skip conflicting rows, add only new", key="annual_skip"):
                key_set = set(existing_by_key.keys())
                new_only = [
                    r for r in rows
                    if (r["fiscal_year"], r["category"], r["subcategory"]) not in key_set
                ]
                count = upsert_annual_rows(new_only)
                st.success(f"Upserted {count} new rows (skipped {len(conflicts)} conflicts).")
                st.session_state.pop("extracted_annual_rows", None)

    st.divider()

    st.subheader("Browse annual data")

    with st.spinner("Loading data..."):
        all_annual_rows = fetch_all_annual_rows()

    if not all_annual_rows:
        st.info("No annual data yet — upload a PDF above to get started.")
    else:
        all_annual_df = pd.DataFrame(all_annual_rows)
        all_annual_df["subcategory"] = all_annual_df["subcategory"].fillna("")

        col1, col2 = st.columns(2)
        with col1:
            show_subcategories = st.checkbox("Show sub-category rows", value=False, key="annual_show_sub")
        with col2:
            annual_categories = st.multiselect(
                "Categories",
                options=[c for c in CATEGORY_ORDER if c in all_annual_df["category"].unique()],
                default=list(all_annual_df["category"].unique()),
                key="annual_cat_filter",
            )

        filtered = all_annual_df[all_annual_df["category"].isin(annual_categories)]
        if not show_subcategories:
            filtered = filtered[filtered["subcategory"] == ""]

        display_filtered = filtered[
            ["fiscal_year", "category", "subcategory", "current_year_units", "source_file"]
        ].copy()
        display_filtered["subcategory"] = display_filtered["subcategory"].replace("", "—")
        st.dataframe(display_filtered, use_container_width=True, hide_index=True)

        st.download_button(
            "Download filtered CSV",
            data=display_filtered.to_csv(index=False),
            file_name="fada_annual_summary_filtered.csv",
            mime="text/csv",
            key="annual_download",
        )

# ============================================================
# OEM TAB
# ============================================================
else:
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
            if st.button("✅ Upsert to database", type="primary", key="oem_upsert"):
                count = upsert_oem_rows(rows)
                st.success(f"Upserted {count} rows.")
                st.session_state.pop("extracted_oem_rows", None)
        with col2:
            if conflicts and st.button("Skip conflicting rows, add only new", key="oem_skip"):
                key_set = set(existing_by_key.keys())
                new_only = [
                    r for r in rows
                    if (r["fiscal_year"], r["category"], r["oem_name"], r["parent_oem"]) not in key_set
                ]
                count = upsert_oem_rows(new_only)
                st.success(f"Upserted {count} new rows (skipped {len(conflicts)} conflicts).")
                st.session_state.pop("extracted_oem_rows", None)

    st.divider()

    st.subheader("Browse OEM data")

    with st.spinner("Loading data..."):
        all_oem_rows = fetch_all_oem_rows()

    if not all_oem_rows:
        st.info("No OEM data yet — upload a table above to get started.")
    else:
        all_oem_df = pd.DataFrame(all_oem_rows)
        all_oem_df["parent_oem"] = all_oem_df["parent_oem"].fillna("")

        col1, col2 = st.columns(2)
        with col1:
            show_sub_entities = st.checkbox("Show sub-entity rows", value=False, key="oem_show_sub")
        with col2:
            oem_categories = st.multiselect(
                "Categories",
                options=sorted(all_oem_df["category"].unique()),
                default=list(all_oem_df["category"].unique()),
                key="oem_cat_filter",
                format_func=lambda c: f"{CATEGORY_LABELS.get(c, c)} ({c})",
            )

        filtered_oem = all_oem_df[all_oem_df["category"].isin(oem_categories)]
        if not show_sub_entities:
            filtered_oem = filtered_oem[filtered_oem["parent_oem"] == ""]

        display_oem = filtered_oem[
            ["fiscal_year", "category", "oem_name", "parent_oem", "current_year_units", "source_file"]
        ].copy()
        display_oem["parent_oem"] = display_oem["parent_oem"].replace("", "—")
        st.dataframe(display_oem, use_container_width=True, hide_index=True)

        st.download_button(
            "Download filtered CSV",
            data=display_oem.to_csv(index=False),
            file_name="fada_oem_summary_filtered.csv",
            mime="text/csv",
            key="oem_download",
        )
