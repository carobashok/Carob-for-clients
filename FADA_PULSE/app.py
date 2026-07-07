import streamlit as st

st.set_page_config(page_title="FADA Pulse", page_icon="🚗", layout="wide")

st.title("🚗 FADA Pulse")
st.caption("CarobInsights — FADA monthly vehicle retail data, tracked over time")

st.markdown(
    """
Use the pages in the sidebar:

- **Upload** — drop in a FADA monthly press-release PDF, review the extracted
  numbers, and push them to the database. Conflicts with existing data are
  flagged before anything is overwritten.
- **Data Table** — browse, filter, and search everything that's been loaded
  so far.
"""
)
