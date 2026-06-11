import streamlit as st
import json
from utils.supabase_client import get_supabase
from auth import get_current_profile


def my_tickets_page():
    profile  = get_current_profile()
    supabase = get_supabase()
    user_id  = profile.get("id")

    st.title("🏠 My Tickets")
    st.markdown(f"Welcome, **{profile.get('full_name','')}**. Here are all your submitted tickets.")
    st.markdown("---")

    # ── KPI row ────────────────────────────────────────────────────────────────
    try:
        all_mine = supabase.table("tickets").select("status,sla_status,priority") \
            .eq("reported_by", user_id).execute().data or []
        open_t   = len([t for t in all_mine if t["status"] not in ("resolved","closed")])
        resolved = len([t for t in all_mine if t["status"] in ("resolved","closed")])
        breached = len([t for t in all_mine if t["sla_status"] == "breached"])
        total    = len(all_mine)

        c1,c2,c3,c4 = st.columns(4)
        with c1: st.markdown(f"<div class='metric-card'><p>Total Tickets</p><h3>{total}</h3></div>", unsafe_allow_html=True)
        with c2: st.markdown(f"<div class='metric-card' style='border-left-color:#e67e22'><p>Open</p><h3 style='color:#e67e22'>{open_t}</h3></div>", unsafe_allow_html=True)
        with c3: st.markdown(f"<div class='metric-card' style='border-left-color:#27ae60'><p>Resolved</p><h3 style='color:#27ae60'>{resolved}</h3></div>", unsafe_allow_html=True)
        with c4: st.markdown(f"<div class='metric-card' style='border-left-color:#c0392b'><p>SLA Breached</p><h3 style='color:#c0392b'>{breached}</h3></div>", unsafe_allow_html=True)
    except:
        pass

    st.markdown("---")

    # ── Filters ────────────────────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        status_filter = st.multiselect("Filter by Status",
            ["new","assigned","in_progress","on_hold","resolved","closed"],
            default=["new","assigned","in_progress","on_hold"],
            format_func=lambda x: x.replace("_"," ").title(),
            key="mt_status")
    with col2:
        search = st.text_input("🔎 Search", placeholder="Ticket number or keyword", key="mt_search")

    # ── Fetch ──────────────────────────────────────────────────────────────────
    try:
        q = supabase.table("tickets").select(
            "*, categories(name), subcategories(name), "
            "assigned_agent:profiles!tickets_assigned_to_fkey(full_name), "
            "agent_teams(name)"
        ).eq("reported_by", user_id).order("created_at", desc=True)

        if status_filter:
            q = q.in_("status", status_filter)

        tickets = q.execute().data or []

        if search:
            term = search.lower()
            tickets = [t for t in tickets if
                term in (t.get("ticket_number") or "").lower() or
                term in (t.get("title") or "").lower()]
    except Exception as e:
        st.error(f"Could not load tickets: {e}")
        return

    if not tickets:
        st.info("No tickets found. Click **➕ Raise a Ticket** in the sidebar to get started.")
        return

    st.markdown(f"**{len(tickets)} ticket(s)**")

    for i, ticket in enumerate(tickets):
        tid      = ticket.get("id","")
        tnum     = ticket.get("ticket_number","")
        title    = ticket.get("title","")
        status   = ticket.get("status","new")
        priority = ticket.get("priority","P3")
        sla_st   = ticket.get("sla_status","on_track")
        ttype    = ticket.get("type","issue")
        category = (ticket.get("categories") or {}).get("name","—")
        agent    = (ticket.get("assigned_agent") or {}).get("full_name","Unassigned")
        created  = ticket.get("created_at","")[:16].replace("T"," ")
        sla_dl   = (ticket.get("sla_deadline") or "")[:16].replace("T"," ")

        sla_icon = {"on_track":"🟢","at_risk":"🟡","breached":"🔴"}.get(sla_st,"⚪")
        pri_icon = {"P1":"🔴","P2":"🟠","P3":"🔵","P4":"🟢"}.get(priority,"⚪")
        type_icon = "🔧" if ttype == "issue" else "📋"

        with st.container():
            c1,c2,c3,c4 = st.columns([3,1.5,1.2,1.5])
            with c1: st.markdown(f"**{tnum}** {type_icon}  \n{title}")
            with c2:
                st.markdown(f"📁 {category}")
                st.caption(f"🧑‍💻 {agent}")
            with c3:
                st.markdown(f"{pri_icon} **{priority}**")
                st.caption(f"{sla_icon} {sla_st.replace('_',' ').title()}")
            with c4:
                st.markdown(f"`{status.replace('_',' ').title()}`")
                st.caption(f"🕐 {created}")

            with st.expander(f"Details & Comments — {tnum}##{i}"):
                st.markdown(f"**Description:** {ticket.get('description','')}")
                if sla_dl:
                    st.caption(f"⏰ SLA Deadline: {sla_dl} UTC")
                st.markdown("---")
                st.markdown("**💬 Comments**")
                try:
                    comments = supabase.table("ticket_comments") \
                        .select("*, author:profiles!ticket_comments_author_id_fkey(full_name)") \
                        .eq("ticket_id", tid).eq("is_internal", False) \
                        .order("created_at").execute().data or []
                    if not comments:
                        st.caption("No updates yet.")
                    for c in comments:
                        author = (c.get("author") or {}).get("full_name","IT Team")
                        ts     = c.get("created_at","")[:16].replace("T"," ")
                        st.markdown(
                            f"<div style='background:#1e3a5f;padding:10px 14px;border-radius:8px;margin-bottom:8px;'>"
                            f"<strong>{author}</strong> <span style='color:#aaa;font-size:12px;'>{ts}</span>"
                            f"<br>{c.get('body','')}</div>", unsafe_allow_html=True)
                except:
                    st.caption("Could not load comments.")

                st.markdown("---")
                with st.form(key=f"emp_comment_{tid}_{i}"):
                    reply = st.text_area("Add a reply", height=80, key=f"emp_reply_{tid}_{i}")
                    if st.form_submit_button("💬 Send", type="primary"):
                        if reply.strip():
                            try:
                                supabase.table("ticket_comments").insert({
                                    "ticket_id": tid, "author_id": user_id,
                                    "body": reply.strip(), "is_internal": False
                                }).execute()
                                st.success("Reply sent!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                        else:
                            st.warning("Please enter a message.")

            st.markdown("---")
