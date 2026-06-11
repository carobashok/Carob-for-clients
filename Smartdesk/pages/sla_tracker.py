import streamlit as st
from datetime import datetime, timezone
from utils.supabase_client import get_supabase
from auth import get_current_profile, require_role


def sla_tracker_page():
    require_role("agent","team_lead","admin")
    profile  = get_current_profile()
    supabase = get_supabase()

    st.title("🔴 SLA Tracker")
    st.markdown("Live view of tickets at risk or in breach of SLA.")
    st.markdown("---")

    # ── Summary KPIs ───────────────────────────────────────────────────────────
    try:
        data = supabase.table("tickets").select("sla_status,priority,status") \
            .not_.in_("status", ["resolved","closed"]).execute().data or []

        breached = [t for t in data if t["sla_status"] == "breached"]
        at_risk  = [t for t in data if t["sla_status"] == "at_risk"]
        on_track = [t for t in data if t["sla_status"] == "on_track"]

        c1,c2,c3,c4 = st.columns(4)
        with c1: st.markdown(f"<div class='metric-card' style='border-left-color:#c0392b'><p>🔴 Breached</p><h3 style='color:#c0392b'>{len(breached)}</h3></div>", unsafe_allow_html=True)
        with c2: st.markdown(f"<div class='metric-card' style='border-left-color:#e67e22'><p>🟡 At Risk</p><h3 style='color:#e67e22'>{len(at_risk)}</h3></div>", unsafe_allow_html=True)
        with c3: st.markdown(f"<div class='metric-card' style='border-left-color:#27ae60'><p>🟢 On Track</p><h3 style='color:#27ae60'>{len(on_track)}</h3></div>", unsafe_allow_html=True)
        with c4:
            p1_breach = len([t for t in breached if t["priority"] == "P1"])
            st.markdown(f"<div class='metric-card' style='border-left-color:#8e44ad'><p>🔴 P1 Breached</p><h3 style='color:#8e44ad'>{p1_breach}</h3></div>", unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Could not load summary: {e}")

    st.markdown("---")

    # ── Fetch SLA tickets ──────────────────────────────────────────────────────
    tab1, tab2 = st.tabs(["🔴 Breached & At Risk", "📋 All Open Tickets"])

    with tab1:
        _render_sla_table(supabase, ["breached","at_risk"], "breached_atrisk")

    with tab2:
        _render_sla_table(supabase, ["breached","at_risk","on_track"], "all_open")


def _render_sla_table(supabase, sla_statuses, key_prefix):
    try:
        tickets = supabase.table("tickets").select(
            "ticket_number, title, type, priority, status, sla_status, "
            "sla_deadline, sla_hours, created_at, "
            "categories(name), "
            "reported_by_profile:profiles!tickets_reported_by_fkey(full_name), "
            "assigned_agent:profiles!tickets_assigned_to_fkey(full_name), "
            "agent_teams(name)"
        ).in_("sla_status", sla_statuses) \
         .not_.in_("status", ["resolved","closed"]) \
         .order("sla_deadline").execute().data or []

        if not tickets:
            st.info("No tickets in this category.")
            return

        now = datetime.now(timezone.utc)

        for i, t in enumerate(tickets):
            tnum      = t.get("ticket_number","")
            title     = t.get("title","")
            priority  = t.get("priority","P3")
            sla_st    = t.get("sla_status","on_track")
            status    = t.get("status","new")
            category  = (t.get("categories") or {}).get("name","—")
            reporter  = (t.get("reported_by_profile") or {}).get("full_name","—")
            agent     = (t.get("assigned_agent") or {}).get("full_name","Unassigned")
            team      = (t.get("agent_teams") or {}).get("name","—")
            sla_dl    = t.get("sla_deadline","")
            created   = t.get("created_at","")[:16].replace("T"," ")

            # Calculate time overdue or remaining
            time_info = ""
            if sla_dl:
                try:
                    from datetime import datetime as dt
                    import re
                    dl = dt.fromisoformat(sla_dl.replace("Z","+00:00"))
                    diff = (dl - now).total_seconds() / 3600
                    if diff < 0:
                        time_info = f"⏱️ **{abs(diff):.1f}h overdue**"
                    else:
                        time_info = f"⏱️ {diff:.1f}h remaining"
                except:
                    time_info = sla_dl[:16].replace("T"," ")

            sla_colour = {"breached":"#c0392b","at_risk":"#e67e22","on_track":"#27ae60"}.get(sla_st,"#888")
            pri_icon   = {"P1":"🔴","P2":"🟠","P3":"🔵","P4":"🟢"}.get(priority,"⚪")

            st.markdown(
                f"<div style='border-left:4px solid {sla_colour};padding:10px 16px;"
                f"background:#1a1a2e;border-radius:6px;margin-bottom:8px;'>"
                f"<strong>{tnum}</strong> {pri_icon} &nbsp; {title}<br>"
                f"<span style='color:#aaa;font-size:13px;'>"
                f"📁 {category} &nbsp;|&nbsp; 👤 {reporter} &nbsp;|&nbsp; "
                f"🧑‍💻 {agent} &nbsp;|&nbsp; 🏢 {team} &nbsp;|&nbsp; "
                f"`{status.replace('_',' ').title()}` &nbsp;|&nbsp; {time_info}"
                f"</span></div>",
                unsafe_allow_html=True
            )

    except Exception as e:
        st.error(f"Could not load SLA data: {e}")
