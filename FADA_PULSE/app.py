import streamlit as st

st.set_page_config(page_title="FADA Pulse", page_icon="🚗", layout="wide")

st.title("🚗 FADA Pulse")
st.caption("CarobInsights — FADA vehicle retail data, tracked over time")

st.markdown(
    """
Use the pages in the sidebar:

- **Upload** — drop in a FADA monthly press-release PDF, review the extracted
  numbers, and push them to the database. Conflicts with existing data are
  flagged before anything is overwritten.
- **Data Table** — browse, filter, and search all monthly data loaded so far.
- **Dashboard** — trend charts across all three granularities: monthly
  (category-wise, gaps shown as gaps), annual/FY (bar charts by category),
  and OEM (manufacturer trend + OEM × fiscal-year breakdown table).
- **Annual & OEM** — upload FY press releases and OEM market-share tables.
  Each has its own tab with an upload/preview/conflict-check flow and a
  browsable, filterable, downloadable data table.
"""
)
