"""
Shared Supabase client for FADA Pulse.

Reads credentials from Streamlit secrets (.streamlit/secrets.toml):
    [supabase]
    url = "https://xxxx.supabase.co"
    key = "service_role_key_here"
"""

import streamlit as st
from supabase import create_client, Client

TABLE = "fada_category_summary"

CATEGORY_ORDER = ["2W", "3W", "PV", "TRAC", "CE", "CV", "Total"]


@st.cache_resource
def get_client() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)


def fetch_all_rows() -> list[dict]:
    """Fetch every row from the table, paginating past Supabase's 1000-row default cap."""
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


def fetch_existing_keys(months: list[str]) -> set[tuple[str, str]]:
    """Return the set of (month, category) already in the DB for the given months,
    used to detect conflicts before an upsert."""
    if not months:
        return set()
    client = get_client()
    result = (
        client.table(TABLE)
        .select("month,category,current_month_units,source_file")
        .in_("month", months)
        .execute()
    )
    return result.data or []


def upsert_rows(rows: list[dict]) -> int:
    """Upsert rows on (month, category). Returns count of rows sent."""
    if not rows:
        return 0
    client = get_client()
    client.table(TABLE).upsert(rows, on_conflict="month,category").execute()
    return len(rows)
