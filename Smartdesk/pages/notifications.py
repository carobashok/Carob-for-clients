import streamlit as st
from utils.supabase_client import get_supabase
from auth import get_current_profile


def notifications_page():
    profile  = get_current_profile()
    supabase = get_supabase()
    user_id  = profile.get("id")

    st.title("🔔 Notifications")

    try:
        notifs = supabase.table("notifications") \
            .select("*").eq("user_id", user_id) \
            .order("created_at", desc=True).limit(50).execute().data or []

        unread = [n for n in notifs if not n.get("is_read")]

        col1, col2 = st.columns([3,1])
        with col1:
            st.markdown(f"**{len(unread)} unread** of {len(notifs)} total")
        with col2:
            if unread and st.button("✅ Mark all read", use_container_width=True):
                supabase.table("notifications").update({"is_read": True}) \
                    .eq("user_id", user_id).execute()
                st.rerun()

        st.markdown("---")

        if not notifs:
            st.info("No notifications yet.")
            return

        for n in notifs:
            is_read = n.get("is_read", False)
            title   = n.get("title","Notification")
            body    = n.get("body","")
            ts      = n.get("created_at","")[:16].replace("T"," ")
            bg      = "#1a1a2e" if is_read else "#1e3a5f"
            dot     = "" if is_read else "🔵 "

            st.markdown(
                f"<div style='background:{bg};padding:12px 16px;border-radius:8px;"
                f"margin-bottom:8px;border-left:3px solid {'#555' if is_read else '#2E75B6'};'>"
                f"<strong>{dot}{title}</strong> "
                f"<span style='color:#aaa;font-size:12px;float:right;'>{ts}</span><br>"
                f"<span style='color:#ccc;font-size:13px;'>{body}</span></div>",
                unsafe_allow_html=True
            )

    except Exception as e:
        st.error(f"Could not load notifications: {e}")
