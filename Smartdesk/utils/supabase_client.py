import streamlit as st
from supabase import create_client, Client

@st.cache_resource
def get_supabase() -> Client:
    url  = st.secrets["SUPABASE_URL"]
    key  = st.secrets["SUPABASE_ANON_KEY"]
    return create_client(url, key)

@st.cache_resource
def get_supabase_admin() -> Client:
    """Service role client — server-side only, never expose to browser."""
    url  = st.secrets["SUPABASE_URL"]
    key  = st.secrets["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)
