"""
Carob Inventory Manager — Main App
Manufacturing Inventory POC by Carob Technologies
"""
import streamlit as st

st.set_page_config(
    page_title="Carob Inventory Manager",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600;700&family=DM+Sans:wght@300;400;500;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #0D1B2A;
    }
    [data-testid="stSidebar"] * {
        color: #E8E8E8 !important;
    }
    [data-testid="stSidebar"] .stRadio label {
        font-size: 0.95rem;
        padding: 4px 0;
    }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: #F7F9FC;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 16px 20px;
    }
    [data-testid="stMetric"] label {
        font-size: 0.78rem !important;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #64748B !important;
        font-weight: 500;
    }
    [data-testid="stMetricValue"] {
        font-family: 'Cormorant Garamond', serif !important;
        font-size: 2rem !important;
        font-weight: 700 !important;
        color: #0D1B2A !important;
    }

    /* Page title */
    .carob-title {
        font-family: 'Cormorant Garamond', serif;
        font-size: 2rem;
        font-weight: 700;
        color: #0D1B2A;
        margin-bottom: 4px;
    }
    .carob-subtitle {
        font-size: 0.85rem;
        color: #94A3B8;
        margin-bottom: 24px;
    }

    /* Status badges */
    .badge-ok { background: #DCFCE7; color: #166534; padding: 2px 10px; border-radius: 99px; font-size: 0.78rem; font-weight: 600; }
    .badge-warn { background: #FEF9C3; color: #854D0E; padding: 2px 10px; border-radius: 99px; font-size: 0.78rem; font-weight: 600; }
    .badge-danger { background: #FEE2E2; color: #991B1B; padding: 2px 10px; border-radius: 99px; font-size: 0.78rem; font-weight: 600; }
    .badge-info { background: #DBEAFE; color: #1E40AF; padding: 2px 10px; border-radius: 99px; font-size: 0.78rem; font-weight: 600; }

    /* Divider */
    hr { border: none; border-top: 1px solid #E2E8F0; margin: 20px 0; }

    /* Button overrides */
    .stButton > button {
        background: #0D1B2A;
        color: white;
        border: none;
        border-radius: 6px;
        font-family: 'DM Sans', sans-serif;
        font-weight: 500;
        font-size: 0.88rem;
    }
    .stButton > button:hover {
        background: #1E3A5F;
    }

    /* Tab styling */
    .stTabs [data-baseweb="tab"] {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.9rem;
    }

    /* DataFrame */
    .stDataFrame { border-radius: 8px; overflow: hidden; }

    /* Hide Streamlit branding */
    #MainMenu, footer { visibility: hidden; }
    header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='padding: 8px 0 20px 0;'>
        <div style='font-family: Cormorant Garamond, serif; font-size: 1.5rem;
                    font-weight: 700; color: #C9A84C; line-height: 1.2;'>
            Carob Inventory
        </div>
        <div style='font-size: 0.7rem; color: #94A3B8; letter-spacing: 0.1em;
                    text-transform: uppercase; margin-top: 2px;'>
            Manufacturing Manager
        </div>
    </div>
    <hr style='border-color: #1E3A5F; margin-bottom: 16px;'/>
    """, unsafe_allow_html=True)

    page = st.radio(
        "Navigation",
        ["📊 Dashboard", "📦 Inventory", "🛒 Purchase Orders", "🏭 Production", "📋 Stock Ledger"],
        label_visibility="collapsed"
    )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("""
    <div style='font-size: 0.72rem; color: #475569; border-top: 1px solid #1E3A5F;
                padding-top: 12px; margin-top: 8px;'>
        Carob Technologies · POC v1.0<br>
        Manufacturing Inventory System
    </div>
    """, unsafe_allow_html=True)

# ── Route pages ──────────────────────────────────────────────────────────────
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if page == "📊 Dashboard":
    from pages.dashboard import show
    show()
elif page == "📦 Inventory":
    from pages.inventory import show
    show()
elif page == "🛒 Purchase Orders":
    from pages.purchase_orders import show
    show()
elif page == "🏭 Production":
    from pages.production import show
    show()
elif page == "📋 Stock Ledger":
    from pages.stock_ledger import show
    show()
