import streamlit as st
from auth import login_page, logout
from utils.supabase_client import get_supabase

st.set_page_config(
    page_title="IT Help Desk",
    page_icon="🎫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Sidebar styling */
    [data-testid="stSidebar"] {background-color: #1F4E79; color: white;}
    [data-testid="stSidebar"] .stRadio label {color: white !important;}
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3, [data-testid="stSidebar"] p {color: white !important;}

    /* Badge colours */
    .badge-p1 {background:#c0392b;color:white;padding:2px 8px;border-radius:4px;font-size:12px;}
    .badge-p2 {background:#e67e22;color:white;padding:2px 8px;border-radius:4px;font-size:12px;}
    .badge-p3 {background:#2980b9;color:white;padding:2px 8px;border-radius:4px;font-size:12px;}
    .badge-p4 {background:#27ae60;color:white;padding:2px 8px;border-radius:4px;font-size:12px;}

    .badge-on_track {background:#27ae60;color:white;padding:2px 8px;border-radius:4px;font-size:12px;}
    .badge-at_risk  {background:#e67e22;color:white;padding:2px 8px;border-radius:4px;font-size:12px;}
    .badge-breached {background:#c0392b;color:white;padding:2px 8px;border-radius:4px;font-size:12px;}

    .badge-new        {background:#8e44ad;color:white;padding:2px 8px;border-radius:4px;font-size:12px;}
    .badge-assigned   {background:#2980b9;color:white;padding:2px 8px;border-radius:4px;font-size:12px;}
    .badge-in_progress{background:#16a085;color:white;padding:2px 8px;border-radius:4px;font-size:12px;}
    .badge-on_hold    {background:#7f8c8d;color:white;padding:2px 8px;border-radius:4px;font-size:12px;}
    .badge-resolved   {background:#27ae60;color:white;padding:2px 8px;border-radius:4px;font-size:12px;}
    .badge-closed     {background:#2c3e50;color:white;padding:2px 8px;border-radius:4px;font-size:12px;}

    /* Metric cards */
    .metric-card {
        background: #f8f9fa; border-radius: 10px; padding: 16px 20px;
        border-left: 5px solid #2E75B6; margin-bottom: 12px;
    }
    .metric-card h3 {margin:0;font-size:28px;color:#1F4E79;}
    .metric-card p  {margin:0;font-size:13px;color:#666;}
</style>
""", unsafe_allow_html=True)


def main():
    # ── Not logged in ──────────────────────────────────────────────────────────
    if "user" not in st.session_state or st.session_state.user is None:
        login_page()
        return

    user    = st.session_state.user
    profile = st.session_state.profile
    role    = profile.get("role", "employee")

    # ── Sidebar ────────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(f"## 🎫 IT Help Desk")
        st.markdown("---")
        st.markdown(f"👤 **{profile.get('full_name', 'User')}**")
        st.markdown(f"🏷️ `{role.replace('_', ' ').title()}`")
        st.markdown("---")

        # Navigation per role
        if role == "employee":
            pages = {
                "🏠 My Tickets":      "my_tickets",
                "➕ Raise a Ticket":  "raise_ticket",
                "🔔 Notifications":   "notifications",
            }
        elif role in ("agent", "team_lead"):
    pages = {
        "📋 Ticket Queue":    "ticket_queue",
        "➕ Raise a Ticket":  "raise_ticket",
        "🔴 SLA Tracker":     "sla_tracker",
        "📊 Analytics":       "analytics",
        "💡 AI Insights":     "ai_insights",
        "🔔 Notifications":   "notifications",
    }
        else:  # admin
    pages = {
        "📋 All Tickets":     "ticket_queue",
        "➕ Raise a Ticket":  "raise_ticket",
        "🔴 SLA Tracker":     "sla_tracker",
        "📊 Analytics":       "analytics",
        "💡 AI Insights":     "ai_insights",
        "⚙️ Admin Panel":     "admin_panel",
        "🔔 Notifications":   "notifications",
    }

        selected_label = st.radio("Navigation", list(pages.keys()), label_visibility="collapsed")
        current_page   = pages[selected_label]

        st.markdown("---")
        if st.button("🚪 Logout", use_container_width=True):
            logout()
            st.rerun()

    # ── Page routing ───────────────────────────────────────────────────────────
    if current_page == "my_tickets":
        from pages.my_tickets import my_tickets_page
        my_tickets_page()

    elif current_page == "raise_ticket":
        from pages.raise_ticket import raise_ticket_page
        raise_ticket_page()

    elif current_page == "ticket_queue":
        from pages.ticket_queue import ticket_queue_page
        ticket_queue_page()

    elif current_page == "sla_tracker":
        from pages.sla_tracker import sla_tracker_page
        sla_tracker_page()

    elif current_page == "analytics":
        from pages.analytics import analytics_page
        analytics_page()

    elif current_page == "ai_insights":
        from pages.ai_insights import ai_insights_page
        ai_insights_page()

    elif current_page == "admin_panel":
        from pages.admin_panel import admin_panel_page
        admin_panel_page()

    elif current_page == "notifications":
        from pages.notifications import notifications_page
        notifications_page()


if __name__ == "__main__":
    main()
