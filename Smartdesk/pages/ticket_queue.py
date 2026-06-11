import streamlit as st
import json
from datetime import datetime, timezone
from utils.supabase_client import get_supabase
from auth import get_current_profile, require_role


def ticket_queue_page():
    require_role("agent", "team_lead", "admin")
    profile  = get_current_profile()
    supabase = get_supabase()
    role     = profile.get("role")

    st.title("📋 Ticket Queue")
    _render_kpi_row(supabase)
    st.markdown("---")

    with st.expander("🔍 Filters", expanded=True):
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            status_filter = st.multiselect("Status",
                ["new","assigned","in_progress","on_hold","resolved","closed"],
                default=["new","assigned","in_progress","on_hold"],
                format_func=lambda x: x.replace("_"," ").title())
        with col2:
            priority_filter = st.multiselect("Priority", ["P1","P2","P3","P4"])
        with col3:
            type_filter = st.multiselect("Type", ["issue","service_request"],
                format_func=lambda x: "Issue" if x=="issue" else "Service Request")
        with col4:
            try:
                cats = supabase.table("categories").select("name").eq("is_active",True).execute()
                cat_names = [c["name"] for c in cats.data] if cats.data else []
            except:
                cat_names = []
            cat_filter = st.multiselect("Category", cat_names)
        with col5:
            sla_filter = st.multiselect("SLA Status", ["on_track","at_risk","breached"],
                format_func=lambda x: x.replace("_"," ").title())

        col_a, col_b = st.columns([2,1])
        with col_a:
            search_term = st.text_input("🔎 Search", placeholder="Ticket number or keyword")
        with col_b:
            my_only = st.checkbox("My tickets only", key="my_only_chk")

    tickets = _fetch_tickets(supabase, profile, role,
        status_filter, priority_filter, type_filter,
        cat_filter, sla_filter, search_term, my_only)

    st.markdown(f"**{len(tickets)} ticket(s) found**")
    if not tickets:
        st.info("No tickets match the current filters.")
        return

    for i, ticket in enumerate(tickets):
        _render_ticket_card(ticket, profile, supabase, i)


def _render_kpi_row(supabase):
    try:
        data = supabase.table("tickets").select("status,sla_status,priority").execute().data or []
        open_t    = len([t for t in data if t["status"] not in ("resolved","closed")])
        breached  = len([t for t in data if t["sla_status"] == "breached"])
        at_risk   = len([t for t in data if t["sla_status"] == "at_risk"])
        p1_open   = len([t for t in data if t["priority"]=="P1" and t["status"] not in ("resolved","closed")])
        c1,c2,c3,c4 = st.columns(4)
        with c1: st.markdown(f"<div class='metric-card'><p>Open Tickets</p><h3>{open_t}</h3></div>", unsafe_allow_html=True)
        with c2: st.markdown(f"<div class='metric-card' style='border-left-color:#c0392b'><p>SLA Breached</p><h3 style='color:#c0392b'>{breached}</h3></div>", unsafe_allow_html=True)
        with c3: st.markdown(f"<div class='metric-card' style='border-left-color:#e67e22'><p>At Risk</p><h3 style='color:#e67e22'>{at_risk}</h3></div>", unsafe_allow_html=True)
        with c4: st.markdown(f"<div class='metric-card' style='border-left-color:#8e44ad'><p>Open P1</p><h3 style='color:#8e44ad'>{p1_open}</h3></div>", unsafe_allow_html=True)
    except:
        pass


def _fetch_tickets(supabase, profile, role, status_filter, priority_filter,
                   type_filter, cat_filter, sla_filter, search_term, my_only):
    try:
        q = supabase.table("tickets").select(
            "*, categories(name), subcategories(name), "
            "reported_by_profile:profiles!tickets_reported_by_fkey(full_name,email), "
            "assigned_agent:profiles!tickets_assigned_to_fkey(full_name), "
            "agent_teams(name)"
        ).order("created_at", desc=True)

        if my_only:
            q = q.eq("assigned_to", profile.get("id"))
        elif role == "agent":
            team_id = profile.get("agent_team_id")
            if team_id:
                q = q.eq("assigned_team_id", team_id)

        if status_filter:   q = q.in_("status", status_filter)
        if priority_filter: q = q.in_("priority", priority_filter)
        if type_filter:     q = q.in_("type", type_filter)
        if sla_filter:      q = q.in_("sla_status", sla_filter)

        tickets = q.limit(100).execute().data or []

        if cat_filter:
            tickets = [t for t in tickets if (t.get("categories") or {}).get("name") in cat_filter]
        if search_term:
            term = search_term.lower()
            tickets = [t for t in tickets if
                term in (t.get("ticket_number") or "").lower() or
                term in (t.get("title") or "").lower()]
        return tickets
    except Exception as e:
        st.error(f"Error loading tickets: {e}")
        return []


def _render_ticket_card(ticket, profile, supabase, idx):
    tid       = ticket.get("id","")
    tnum      = ticket.get("ticket_number","")
    title     = ticket.get("title","No title")
    status    = ticket.get("status","new")
    priority  = ticket.get("priority","P3")
    sla_st    = ticket.get("sla_status","on_track")
    ttype     = ticket.get("type","issue")
    category  = (ticket.get("categories") or {}).get("name","—")
    subcat    = (ticket.get("subcategories") or {}).get("name","")
    reporter  = (ticket.get("reported_by_profile") or {}).get("full_name","—")
    agent     = (ticket.get("assigned_agent") or {}).get("full_name","Unassigned")
    team      = (ticket.get("agent_teams") or {}).get("name","Unassigned")
    created   = ticket.get("created_at","")[:16].replace("T"," ")
    sla_dl    = (ticket.get("sla_deadline") or "")[:16].replace("T"," ")
    travelling = ticket.get("is_travelling", False)

    sla_icon  = {"on_track":"🟢","at_risk":"🟡","breached":"🔴"}.get(sla_st,"⚪")
    pri_icon  = {"P1":"🔴","P2":"🟠","P3":"🔵","P4":"🟢"}.get(priority,"⚪")
    type_icon = "🔧" if ttype == "issue" else "📋"
    travel_flag = " ✈️" if travelling else ""

    c1,c2,c3,c4,c5 = st.columns([3,1.2,1,1.2,1.2])
    with c1: st.markdown(f"**{tnum}** {type_icon}{travel_flag}  \n{title}")
    with c2:
        st.markdown(f"📁 {category}" + (f" / {subcat}" if subcat else ""))
        st.caption(f"👤 {reporter}")
    with c3:
        st.markdown(f"{pri_icon} **{priority}**")
        st.caption(f"{sla_icon} {sla_st.replace('_',' ').title()}")
    with c4:
        st.markdown(f"`{status.replace('_',' ').title()}`")
        st.caption(f"🧑‍💻 {agent}")
    with c5:
        st.caption(f"🕐 {created}")
        if sla_dl: st.caption(f"⏰ SLA: {sla_dl}")

    with st.expander(f"View / Act on {tnum} ##{idx}"):
        _render_details_tab(ticket, tid, idx)
        st.markdown("---")
        _render_comments_section(tid, idx, profile, supabase)
        st.markdown("---")
        _render_actions_section(ticket, tid, idx, profile, supabase)

    st.markdown("---")


def _render_details_tab(ticket, tid, idx):
    st.markdown("**📄 Details**")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Description:**  \n{ticket.get('description','')}")
        ai_conf = ticket.get("ai_confidence","")
        if ai_conf:
            icons = {"high":"✅","medium":"⚠️","low":"❓"}
            st.caption(f"AI Confidence: {icons.get(ai_conf,'')} {ai_conf.title()}")
        ai_sug = ticket.get("ai_suggested_fields")
        if ai_sug:
            with st.expander(f"🤖 AI Classification##{tid}"):
                try:
                    st.json(json.loads(ai_sug) if isinstance(ai_sug, str) else ai_sug)
                except:
                    st.write(ai_sug)
    with col2:
        st.markdown(f"**Type:** {ticket.get('type','').replace('_',' ').title()}")
        st.markdown(f"**Priority:** {ticket.get('priority','—')}")
        st.markdown(f"**Status:** {ticket.get('status','').replace('_',' ').title()}")
        st.markdown(f"**Category:** {(ticket.get('categories') or {}).get('name','—')}")
        st.markdown(f"**Subcategory:** {(ticket.get('subcategories') or {}).get('name','—')}")
        st.markdown(f"**Team:** {(ticket.get('agent_teams') or {}).get('name','Unassigned')}")
        st.markdown(f"**Assigned To:** {(ticket.get('assigned_agent') or {}).get('full_name','Unassigned')}")
        st.markdown(f"**Created:** {ticket.get('created_at','')[:16].replace('T',' ')}")
        resolved = (ticket.get("resolved_at") or "")[:16].replace("T"," ")
        if resolved: st.markdown(f"**Resolved:** {resolved}")


def _render_comments_section(tid, idx, profile, supabase):
    st.markdown("**💬 Comments**")
    role = profile.get("role")
    try:
        comments = supabase.table("ticket_comments") \
            .select("*, author:profiles!ticket_comments_author_id_fkey(full_name)") \
            .eq("ticket_id", tid).order("created_at").execute().data or []

        if not comments:
            st.caption("No comments yet.")
        for c in comments:
            if c.get("is_internal") and role not in ("agent","team_lead","admin"):
                continue
            author   = (c.get("author") or {}).get("full_name","Unknown")
            ts       = c.get("created_at","")[:16].replace("T"," ")
            internal = c.get("is_internal", False)
            bg       = "#2c2c2c" if internal else "#1e3a5f"
            label    = " 🔒 Internal" if internal else ""
            st.markdown(f"<div style='background:{bg};padding:10px 14px;border-radius:8px;margin-bottom:8px;'>"
                        f"<strong>{author}</strong>{label} <span style='color:#aaa;font-size:12px;'>{ts}</span>"
                        f"<br>{c.get('body','')}</div>", unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Could not load comments: {e}")

    with st.form(key=f"cform_{tid}_{idx}"):
        comment_text = st.text_area("Add a comment", height=80, key=f"ctxt_{tid}_{idx}")
        is_internal  = False
        if role in ("agent","team_lead","admin"):
            is_internal = st.checkbox("🔒 Internal note", key=f"cint_{tid}_{idx}")
        if st.form_submit_button("💬 Post Comment", type="primary"):
            if comment_text.strip():
                try:
                    supabase.table("ticket_comments").insert({
                        "ticket_id": tid, "author_id": profile.get("id"),
                        "body": comment_text.strip(), "is_internal": is_internal
                    }).execute()
                    supabase.table("ticket_activity").insert({
                        "ticket_id": tid, "actor_id": profile.get("id"),
                        "action": "comment_added",
                        "new_value": "internal" if is_internal else "public"
                    }).execute()
                    st.success("Comment posted!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("Please enter a comment.")


def _render_actions_section(ticket, tid, idx, profile, supabase):
    role   = profile.get("role")
    status = ticket.get("status")
    if role not in ("agent","team_lead","admin"):
        st.info("Only agents and admins can perform actions.")
        return

    st.markdown("**⚡ Actions**")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Update Status**")
        next_map = {
            "new":         ["assigned","in_progress","on_hold","closed"],
            "assigned":    ["in_progress","on_hold","resolved","closed"],
            "in_progress": ["on_hold","resolved","closed"],
            "on_hold":     ["in_progress","resolved","closed"],
            "resolved":    ["closed"],
            "closed":      []
        }
        next_statuses = next_map.get(status, [])
        if not next_statuses:
            st.info("Ticket is closed.")
        else:
            new_status = st.selectbox("Move to", next_statuses,
                key=f"ns_{tid}_{idx}",
                format_func=lambda x: x.replace("_"," ").title())
            resolution_note = ""
            if new_status == "resolved":
                resolution_note = st.text_area("Resolution notes *",
                    key=f"rn_{tid}_{idx}",
                    placeholder="Describe how this was resolved...")
            if st.button("✅ Update Status", key=f"us_{tid}_{idx}", type="primary"):
                if new_status == "resolved" and not resolution_note.strip():
                    st.warning("Please add resolution notes.")
                else:
                    _do_status_update(tid, status, new_status, resolution_note, profile, supabase)

    with col2:
        st.markdown("**Assign Agent**")
        try:
            team_id = ticket.get("assigned_team_id")
            if team_id:
                agents = supabase.table("profiles").select("id,full_name") \
                    .eq("agent_team_id", team_id).in_("role",["agent","team_lead"]).execute().data or []
            else:
                agents = supabase.table("profiles").select("id,full_name") \
                    .in_("role",["agent","team_lead"]).execute().data or []

            if agents:
                agent_map   = {a["full_name"]: a["id"] for a in agents}
                curr_agent  = (ticket.get("assigned_agent") or {}).get("full_name","")
                names       = list(agent_map.keys())
                def_idx     = names.index(curr_agent) if curr_agent in names else 0
                sel_agent   = st.selectbox("Assign to", names, index=def_idx, key=f"asel_{tid}_{idx}")
                if st.button("👤 Assign", key=f"abtn_{tid}_{idx}"):
                    try:
                        supabase.table("tickets").update({
                            "assigned_to": agent_map[sel_agent],
                            "status": "assigned" if status == "new" else status,
                            "assigned_at": datetime.now(timezone.utc).isoformat()
                        }).eq("id", tid).execute()
                        supabase.table("ticket_activity").insert({
                            "ticket_id": tid, "actor_id": profile.get("id"),
                            "action": "assigned", "new_value": sel_agent
                        }).execute()
                        st.success(f"Assigned to {sel_agent}!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Assignment failed: {e}")
            else:
                st.info("No agents found for this team.")
        except Exception as e:
            st.error(f"Could not load agents: {e}")

        if role in ("admin","team_lead") and ticket.get("ai_confidence") in ("low", None):
            st.markdown("---")
            st.markdown("**🏷️ Reclassify**")
            try:
                cats    = supabase.table("categories").select("id,name").eq("is_active",True).execute().data or []
                cat_map = {c["name"]: c["id"] for c in cats}
                new_cat = st.selectbox("Category", list(cat_map.keys()), key=f"rc_{tid}_{idx}")
                if st.button("🏷️ Update", key=f"rcbtn_{tid}_{idx}"):
                    supabase.table("tickets").update({
                        "category_id": cat_map[new_cat],
                        "classification_verified": True
                    }).eq("id", tid).execute()
                    st.success(f"Reclassified to {new_cat}!")
                    st.rerun()
            except Exception as e:
                st.error(f"Reclassification failed: {e}")


def _do_status_update(tid, old_status, new_status, resolution_note, profile, supabase):
    try:
        update = {"status": new_status}
        if new_status == "resolved":
            update["resolved_at"] = datetime.now(timezone.utc).isoformat()
        supabase.table("tickets").update(update).eq("id", tid).execute()
        activity = {
            "ticket_id": tid, "actor_id": profile.get("id"),
            "action": "status_changed", "old_value": old_status, "new_value": new_status
        }
        if resolution_note:
            activity["metadata"] = json.dumps({"resolution_note": resolution_note})
        supabase.table("ticket_activity").insert(activity).execute()
        if resolution_note:
            supabase.table("ticket_comments").insert({
                "ticket_id": tid, "author_id": profile.get("id"),
                "body": f"✅ **Resolved:** {resolution_note}", "is_internal": False
            }).execute()
        st.success(f"Status updated to **{new_status.replace('_',' ').title()}**!")
        st.rerun()
    except Exception as e:
        st.error(f"Status update failed: {e}")
