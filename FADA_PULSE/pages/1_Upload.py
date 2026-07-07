import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd

from utils.extractor import extract_pdf_text, parse_with_claude, build_rows
from utils.db import fetch_existing_keys, upsert_rows

st.set_page_config(page_title="Upload — FADA Pulse", page_icon="📤", layout="wide")
st.title("📤 Upload a FADA press release")

uploaded_file = st.file_uploader("Drop a FADA monthly PDF", type=["pdf"])

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
        if st.button("✅ Upsert to database", type="primary"):
            count = upsert_rows(rows)
            st.success(f"Upserted {count} rows for {month}.")
            st.session_state.pop("extracted_rows", None)
    with col2:
        if conflicts and st.button("Skip conflicting rows, add only new"):
            new_only = [r for r in rows if r["category"] not in existing_by_cat]
            count = upsert_rows(new_only)
            st.success(f"Upserted {count} new rows (skipped {len(conflicts)} conflicts).")
            st.session_state.pop("extracted_rows", None)
