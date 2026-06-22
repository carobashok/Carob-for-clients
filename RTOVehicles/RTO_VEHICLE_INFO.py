"""
streamlit_app.py
==================
Streamlit app to upload the consolidated Vahan RTO CSV data into
Supabase, avoiding the local IPv4/IPv6 connectivity issue by running
on Streamlit Cloud and using Supabase's REST API (via supabase-py)
rather than a direct Postgres connection.

SETUP (Streamlit Cloud):
    1. Add this to your app's Secrets (Settings > Secrets):

        [supabase]
        url = "https://yourproject.supabase.co"
        key = "your-service-role-key"

    2. requirements.txt should include:
        streamlit
        supabase
        pandas

RUN LOCALLY (optional, for testing):
    Create .streamlit/secrets.toml with the same [supabase] block,
    then: streamlit run streamlit_app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import math
from supabase import create_client

st.set_page_config(page_title="Vahan RTO Data Loader", page_icon="🚗", layout="wide")

st.title("🚗 Vahan RTO Data → Supabase Loader")
st.caption("Upload the consolidated rto_full_data.csv and push it into your Supabase table.")


# ── Supabase client setup ────────────────────────────────────────────────────

@st.cache_resource
def get_supabase_client():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
    except KeyError:
        st.error(
            "Supabase credentials not found in Streamlit secrets. "
            "Add a [supabase] section with 'url' and 'key' under "
            "Settings → Secrets."
        )
        st.stop()
    return create_client(url, key)


TABLE_NAME = "vahan_rto_data"

# Core columns every scraped CSV must have, regardless of which Y-Axis
# dimension was scraped (Vehicle_Class, Maker, Fuel, Norms, etc.)
CORE_COLUMNS = {"State", "RTO", "Year", "Category_Group", "Sub_Column", "Value"}

# Known dimension column names the scraper can produce (matches the
# Vahan dashboard's own Y-Axis dropdown labels with spaces replaced by
# underscores, e.g. --yaxis "Vehicle Class" → CSV column 'Vehicle_Class').
KNOWN_DIMENSION_COLUMNS = {
    "Vehicle_Class": "Vehicle Class",
    "Maker": "Maker",
    "Fuel": "Fuel",
    "Norms": "Norms",
    "Vehicle_Category": "Vehicle Category",
    # Note: 'State' is a valid Y-Axis choice on the dashboard, but is
    # deliberately excluded here since it collides with the core 'State'
    # column (the state being scraped). A --yaxis State scrape isn't
    # currently distinguishable from the core column and would need the
    # scraper to emit it under a different column name to support.
}


# ── CSV loading & cleaning ───────────────────────────────────────────────────

def detect_dimension_column(df_columns: set[str]) -> tuple[str, str]:
    """
    Figure out which column in the uploaded CSV holds the Y-Axis
    dimension's row-category values, and what its proper dimension_name
    label should be. Returns (csv_column_name, dimension_name_label).
    Raises ValueError if no recognized dimension column is found.

    Note: 'State' appears in KNOWN_DIMENSION_COLUMNS because it's a
    valid Y-Axis choice on the dashboard, but it's also always present
    as a CORE_COLUMNS field (the state being scraped). We exclude core
    columns from dimension candidacy to avoid this collision — a CSV
    scraped with --yaxis State would need a differently-named column
    (e.g. the scraper would need to emit it as something other than
    bare 'State') to be distinguishable, which isn't yet supported.
    """
    candidates = [
        col for col in KNOWN_DIMENSION_COLUMNS
        if col in df_columns and col not in CORE_COLUMNS
    ]
    if not candidates:
        raise ValueError(
            f"Could not find a recognized dimension column in the CSV. "
            f"Expected one of: {list(KNOWN_DIMENSION_COLUMNS.keys())}. "
            f"Found columns: {sorted(df_columns)}"
        )
    if len(candidates) > 1:
        raise ValueError(
            f"CSV has multiple possible dimension columns: {candidates}. "
            f"Expected exactly one Y-Axis dimension column per file."
        )
    csv_col = candidates[0]
    return csv_col, KNOWN_DIMENSION_COLUMNS[csv_col]


def load_and_clean_csv(uploaded_file) -> pd.DataFrame:
    df = pd.read_csv(uploaded_file)

    missing = CORE_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing expected columns: {missing}")

    dimension_csv_col, dimension_name_label = detect_dimension_column(set(df.columns))
    st.caption(f"Detected dimension column: **{dimension_csv_col}** → will be stored as "
               f"dimension_name = '{dimension_name_label}'")

    df = df.rename(columns={
        "State": "state",
        "RTO": "rto",
        "Year": "year",
        "Category_Group": "category_group",
        "Sub_Column": "sub_column",
        "Value": "value",
        dimension_csv_col: "dimension_value",
    })
    df["dimension_name"] = dimension_name_label

    df["year"] = df["year"].astype(str)

    before = len(df)

    # Filter out placeholder/no-data rows that the scraper captured as if
    # they were real table data. Pattern observed: when a category group
    # genuinely has no data for an RTO/year, the page shows a "No records
    # found." message which got scraped into the dimension column, with
    # the category group's own label leaking into Sub_Column, and Value
    # left blank/NaN. These are not real vehicle counts and should not
    # be loaded.
    no_data_mask = df["dimension_value"].astype(str).str.contains("no records found", case=False, na=False)
    no_data_count = no_data_mask.sum()
    if no_data_count:
        df = df[~no_data_mask]

    df = df.dropna(subset=["state", "rto", "year", "category_group", "dimension_name", "dimension_value", "sub_column"])
    after = len(df)
    dropped = before - after

    if no_data_count:
        st.info(f"Filtered out {no_data_count} placeholder 'No records found' rows (genuinely empty category groups, not real data)")

    # Coerce 'value' to numeric explicitly first (catches stray blanks/text
    # that might have leaked in from placeholder rows), then replace any
    # resulting NaN with None so it serializes as JSON null, not NaN
    # (which is invalid JSON and would break the insert).
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["value"] = df["value"].where(pd.notna(df["value"]), None)

    return df, dropped


def sanitize_records_for_json(records: list[dict]) -> list[dict]:
    """
    Replace any NaN/inf float values with None across ALL fields in
    every record, right before sending to Supabase. This is the final
    safety net — pandas' df.where(notna(), None) at the column level
    can still leak NaN through in edge cases (mixed dtypes, numpy
    float types that aren't caught by pd.notna in to_dict() output),
    so we sanitize the actual dicts that will be JSON-serialized.
    """
    clean_records = []
    for rec in records:
        clean_rec = {}
        for k, v in rec.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                clean_rec[k] = None
            elif isinstance(v, (np.floating,)) and (np.isnan(v) or np.isinf(v)):
                clean_rec[k] = None
            elif pd.isna(v) if not isinstance(v, (list, dict)) else False:
                clean_rec[k] = None
            else:
                clean_rec[k] = v
        clean_records.append(clean_rec)
    return clean_records


def upload_in_batches(client, df: pd.DataFrame, table_name: str, batch_size: int,
                       progress_bar, status_box):
    records = df.to_dict(orient="records")
    records = sanitize_records_for_json(records)
    total = len(records)

    success_count = 0
    error_count = 0
    errors = []

    n_batches = (total + batch_size - 1) // batch_size

    for batch_idx in range(n_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, total)
        batch = records[start:end]

        try:
            client.table(table_name).upsert(
                batch,
                on_conflict="state,rto,year,category_group,dimension_name,dimension_value,sub_column"
            ).execute()
            success_count += len(batch)
        except Exception as e:
            error_count += len(batch)
            errors.append(f"Batch {batch_idx + 1} ({start}-{end}): {type(e).__name__}: {e}")

        progress_bar.progress((batch_idx + 1) / n_batches)
        status_box.text(f"Batch {batch_idx + 1}/{n_batches} — {success_count} succeeded, {error_count} failed so far")

    return success_count, error_count, errors


# ── Admin authentication via sidebar ─────────────────────────────────────────

def is_admin() -> bool:
    """Check if the entered sidebar password matches the one in secrets."""
    try:
        admin_password = st.secrets["ADMIN_PASSWORD"]
    except KeyError:
        return False
    entered = st.session_state.get("admin_password_input", "")
    if entered == admin_password:
        st.session_state["admin_authenticated"] = True
    return st.session_state.get("admin_authenticated", False)


with st.sidebar:
    st.markdown("### 🔐 Admin Access")
    if st.session_state.get("admin_authenticated"):
        st.success("✅ Admin access granted")
        if st.button("🔓 Logout"):
            st.session_state["admin_authenticated"] = False
            st.rerun()
    else:
        st.text_input(
            "Admin password",
            type="password",
            key="admin_password_input",
            placeholder="Enter password to unlock upload",
        )
        is_admin()  # trigger the check so typing immediately authenticates
        if not st.session_state.get("admin_authenticated"):
            st.caption("Upload functionality is restricted to admins.")


# ── Main UI ───────────────────────────────────────────────────────────────────

if not st.session_state.get("admin_authenticated"):
    st.info("🔒 Data upload is restricted to administrators. "
            "Enter the admin password in the sidebar to unlock.")
    st.stop()

# ── Admin-only upload UI ──────────────────────────────────────────────────────

uploaded_file = st.file_uploader("Upload rto_full_data.csv", type=["csv"])

if uploaded_file is not None:
    try:
        df, dropped_rows = load_and_clean_csv(uploaded_file)
    except ValueError as e:
        st.error(str(e))
        st.stop()

    st.success(f"Loaded {len(df):,} rows from CSV" + (f" ({dropped_rows} rows dropped due to missing fields)" if dropped_rows else ""))

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total rows", f"{len(df):,}")
    col2.metric("Unique RTOs", df["rto"].nunique())
    col3.metric("Unique Years", df["year"].nunique())
    col4.metric("Category Groups", df["category_group"].nunique())

    st.subheader("Preview")
    st.dataframe(df.head(20), use_container_width=True)

    st.subheader("Upload to Supabase")
    table_name = st.text_input("Target table name", value=TABLE_NAME)
    batch_size = st.slider("Batch size", min_value=50, max_value=1000, value=500, step=50)

    st.warning(
        f"This will upsert {len(df):,} rows into table **{table_name}**. "
        "Existing rows with the same (state, rto, year, category_group, "
        "dimension_name, dimension_value, sub_column) combination will be "
        "updated; new combinations will be inserted."
    )

    if st.button("🚀 Start Upload", type="primary"):
        client = get_supabase_client()

        progress_bar = st.progress(0)
        status_box = st.empty()

        with st.spinner("Uploading…"):
            success_count, error_count, errors = upload_in_batches(
                client, df, table_name, batch_size, progress_bar, status_box
            )

        if error_count == 0:
            st.success(f"✅ Upload complete! All {success_count:,} rows uploaded successfully.")
        else:
            st.warning(f"⚠ Upload finished with issues: {success_count:,} succeeded, {error_count:,} failed.")
            with st.expander("Show errors"):
                for err in errors:
                    st.text(err)
else:
    st.info("Upload your rto_full_data.csv file above to get started.")

    with st.expander("ℹ️ Expected CSV format"):
        st.write("The CSV should have these core columns (long/tidy format):")
        st.code(", ".join(sorted(CORE_COLUMNS)))
        st.write("Plus exactly ONE of these dimension columns, depending on which "
                 "--yaxis was used when scraping:")
        st.code(", ".join(sorted(KNOWN_DIMENSION_COLUMNS.keys())))
        st.write("Example rows:")
        st.code(
            "Vehicle Class scrape:\n"
            "  State: Puducherry(8) | RTO: BAHOUR - PY11(...) | Year: 2026 | "
            "Category_Group: FOUR WHEELER | Vehicle_Class: ADAPTED VEHICLE | "
            "Sub_Column: 4WIC | Value: 1\n\n"
            "Maker scrape:\n"
            "  State: Puducherry(8) | RTO: BAHOUR - PY11(...) | Year: 2024 | "
            "Category_Group: TWO WHEELER | Maker: BAJAJ AUTO LTD | "
            "Sub_Column: 2WN | Value: 546"
        )
