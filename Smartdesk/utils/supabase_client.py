import streamlit as st
from supabase import create_client, Client

@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

@st.cache_resource
def get_supabase_admin() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"].get("service_key", st.secrets["supabase"]["key"])
    return create_client(url, key)
