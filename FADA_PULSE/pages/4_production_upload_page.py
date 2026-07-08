import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
from utils.db import get_client  # adjust if your client accessor has a different name

st.set_page_config(page_title="Production Data Upload", layout="wide")
st.title("Production Data Upload (TMA / SIAM)")
st.caption("Factory-side production, total sales and exports — complements the FADA retail tables.")

SHEET_CATEGORY_MAP = {
    "Tractor - TMA": ("TRAC", "TMA"),
    "2W - SIAM": ("2W", "SIAM"),
    "3W - SIAM": ("3W", "SIAM"),
    "PV - SIAM": ("PV", "SIAM"),
    "CV - SIAM": ("CV", "SIAM"),
    "CE - SIAM": ("CE", "SIAM"),
}

EXPECTED_COLS = ["month", "production", "total_sales", "exports"]


def normalize_sheet(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    rename = {}
    for c in df.columns:
        if "month" in c:
            rename[c] = "month"
        elif "production" in c:
            rename[c] = "production"
        elif "sales" in c:
            rename[c] = "total_sales"
        elif "export" in c:
            rename[c] = "exports"
    df = df.rename(columns=rename)
    missing = [c for c in EXPECTED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing expected columns: {missing}. Found: {list(df.columns)}")
    df["month"] = pd.to_datetime(df["month"])
    df = df.dropna(subset=["month"])
    for c in ["production", "total_sales", "exports"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    return df[EXPECTED_COLS]


def build_rows(df: pd.DataFrame, category: str, source: str, source_file: str) -> list[dict]:
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "month": r["month"].strftime("%Y-%m-%d"),
            "month_label": r["month"].strftime("%b-%y"),
            "category": category,
            "production": None if pd.isna(r["production"]) else int(r["production"]),
            "total_sales": None if pd.isna(r["total_sales"]) else int(r["total_sales"]),
            "exports": None if pd.isna(r["exports"]) else int(r["exports"]),
            "source": source,
            "source_file": source_file,
        })
    return rows


uploaded = st.file_uploader("Upload TMA / SIAM workbook (.xlsx)", type=["xlsx"])

if uploaded:
    xls = pd.ExcelFile(uploaded)
    all_rows = []
    parse_errors = []

    st.subheader("Sheets found")
    for sheet in xls.sheet_names:
        mapped = SHEET_CATEGORY_MAP.get(sheet)
        cols = st.columns([3, 2, 2, 3])
        cols[0].write(f"**{sheet}**")

        if mapped:
            category, source = mapped
        else:
            category = cols[1].selectbox(
                f"Category for '{sheet}'", ["2W", "3W", "PV", "CV", "TRAC", "CE"], key=f"cat_{sheet}"
            )
            source = cols[2].selectbox(
                f"Source for '{sheet}'", ["TMA", "SIAM"], key=f"src_{sheet}"
            )

        try:
            raw = pd.read_excel(xls, sheet_name=sheet)
            parsed = normalize_sheet(raw)
            rows = build_rows(parsed, category, source, uploaded.name)
            all_rows.extend(rows)
            cols[3].success(f"{len(rows)} rows parsed -> {category} ({source})")
        except Exception as e:
            parse_errors.append((sheet, str(e)))
            cols[3].error(f"Parse error: {e}")

    if parse_errors:
        st.warning(f"{len(parse_errors)} sheet(s) failed to parse — fix and re-upload, or they'll be skipped.")

    if all_rows:
        preview_df = pd.DataFrame(all_rows)
        st.subheader(f"Preview — {len(preview_df)} rows across {preview_df['category'].nunique()} categor(y/ies)")
        st.dataframe(preview_df, use_container_width=True, height=300)

        # Conflict check against existing rows for the same (month, category) keys
        client = get_client()
        existing_keys = set()
        for cat in preview_df["category"].unique():
            resp = client.table("industry_production_summary").select("month,category").eq("category", cat).execute()
            existing_keys.update((r["month"], r["category"]) for r in resp.data)

        new_keys = set((r["month"], r["category"]) for r in all_rows)
        overlap = new_keys & existing_keys
        if overlap:
            st.info(f"{len(overlap)} of these rows already exist and will be **overwritten** (upsert on month + category).")

        if st.button("Upsert to Supabase", type="primary"):
            with st.spinner("Upserting..."):
                resp = client.table("industry_production_summary").upsert(
                    all_rows, on_conflict="month,category"
                ).execute()
            st.success(f"Upserted {len(all_rows)} rows into industry_production_summary.")
else:
    st.info("Upload a workbook to begin. Sheet names matching the known map (e.g. 'Tractor - TMA') are auto-detected; unknown sheet names prompt you for category and source.")
