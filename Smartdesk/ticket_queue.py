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

    # ── Top KPI row ────────────────────────────────────────────────────────────
    _render_kpi_row(supabase, profile, role)
    st.markdown("---")

    # ── Filters ────────────────────────────────────────────────────────────────
    with st.expander("🔍 Filters", expanded=True):
        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            status_filter = st.multiselect(
                "Status",
                ["new", "assigned", "in_progress", "on_hold", "resolved", "closed"],
                default=["new", "assigned", "in_progress", "on_hold"],
                format_func=lambda x: x.replace("_", " ").title()
            )
        with col2:
            priority_filter = st.multiselect("Priority", ["P1", "P2", "P3", "P4"], default=[])
        with col3:
            type_filter = st.multiselect(
                "Type", ["issue", "service_request"],
                format_func=lambda x: "Issue" if x == "issue" else "Service Request"
            )
        with col4:
            try:
                cats = supabase.table("categories").select("name").eq("is_active", True).execute()
                cat_names = [c["name"] for c in cats.data] if cats.data else []
            except:
                cat_names = []
            cat_filter = st.multiselect("Category", cat_names)

        with col5:
            sla_filter = st.multiselect(
                "SLA Status", ["on_track", "at_risk", "breached"],
                format_func=lambda x: x.replace("_", " ").title()
            )

        col_a, col_b = st.columns([2, 1])
        with col_a:
            search_term = st.text_input("🔎 Search ticket number or title", placeholder="TKT-2026- or keyword")
        with col_b:
            my_tickets_only = st.checkbox(
                "My tickets only",
                value=False,
                help="Show only tickets assigned to me"
            )

    # ── Fetch tickets ──────────────────────────────────────────────────────────
    tickets = _fetch_tickets(
        supabase, profile, role,
        status_filter, priority_filter, type_filter,
        cat_filter, sla_filter, search_term, my_tickets_only
    )

    # ── Ticket count ───────────────────────────────────────────────────────────
    st.markdown(f"**{len(tickets)} ticket(s) found**")

    if not tickets:
        st.info("No tickets match the current filters.")
        return

    # ── Ticket list ────────────────────────────────────────────────────────────
    for ticket in tickets:
        _render_ticket_row(ticket, profile, supabase)


# ── KPI Row ────────────────────────────────────────────────────────────────────
def _render_kpi_row(supabase, profile, role):
    try:
        all_tickets = supabase.table("tickets").select("status, sla_status, priority").execute()
        data = all_tickets.data or []

        total_open     = len([t for t in data if t["status"] not in ("resolved", "closed")])
        total_breached = len([t for t in data if t["sla_status"] == "breached"])
        total_at_risk  = len([t for t in data if t["sla_status"] == "at_risk"])
        total_p1       = len([t for t in data if t["priority"] == "P1" and t["status"] not in ("resolved", "closed")])

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f"""<div class='metric-card'>
                <p>Open Tickets</p><h3>{total_open}</h3></div>""", unsafe_allow_html=True)
        with col2:
            st.markdown(f"""<div class='metric-card' style='border-left-color:#c0392b'>
                <p>SLA Breached</p><h3 style='color:#c0392b'>{total_breached}</h3></div>""",
                unsafe_allow_html=True)
        with col3:
            st.markdown(f"""<div class='metric-card' style='border-left-color:#e67e22'>
                <p>At Risk</p><h3 style='color:#e67e22'>{total_at_risk}</h3></div>""",
                unsafe_allow_html=True)
        with col4:
            st.markdown(f"""<div class='metric-card' style='border-left-color:#8e44ad'>
                <p>Open P1 Tickets</p><h3 style='color:#8e44ad'>{total_p1}</h3></div>""",
                unsafe_allow_html=True)
    except:
        pass


# ── Fetch Tickets ──────────────────────────────────────────────────────────────
def _fetch_tickets(supabase, profile, role, status_filter, priority_filter,
                   type_filter, cat_filter, sla_filter, search_term, my_tickets_only):
    try:
        query = supabase.table("tickets").select(
            "*, "
            "categories(name), "
            "subcategories(name), "
            "reported_by_profile:profiles!tickets_reported_by_fkey(full_name, email), "
            "assigned_agent:profiles!tickets_assigned_to_fkey(full_name), "
            "agent_teams(name)"
        ).order("created_at", desc=True)

        # Role-based scoping
        if role == "agent" and not my_tickets_only:
            team_id = profile.get("agent_team_id")
            if team_id:
                query = query.eq("assigned_team_id", team_id)
        elif my_tickets_only:
            query = query.eq("assigned_to", profile.get("id"))

        # Apply filters
        if status_filter:
            query = query.in_("status", status_filter)
        if priority_filter:
            query = query.in_("priority", priority_filter)
        if type_filter:
            query = query.in_("type", type_filter)
        if sla_filter:
            query = query.in_("sla_status", sla_filter)

        res = query.limit(100).execute()
        tickets = res.data or []

        # Category filter (client side — join field)
        if cat_filter:
            tickets = [t for t in tickets
                      if (t.get("categories") or {}).get("name") in cat_filter]

        # Search filter
        if search_term:
            term = search_term.lower()
            tickets = [t for t in tickets
                      if term in (t.get("ticket_number") or "").lower()
                      or term in (t.get("title") or "").lower()]

        return tickets

    except Exception as e:
        st.error(f"Error loading tickets: {e}")
        return []


# ── Single Ticket Row ──────────────────────────────────────────────────────────
def _render_ticket_row(ticket, profile, supabase):
    ticket_id     = ticket.get("id")
    ticket_number = ticket.get("ticket_number", "")
    title         = ticket.get("title", "No title")
    status        = ticket.get("status", "new")
    priority      = ticket.get("priority", "P3")
    sla_status    = ticket.get("sla_status", "on_track")
    ticket_type   = ticket.get("type", "issue")
    category      = (ticket.get("categories") or {}).get("name", "—")
    subcategory   = (ticket.get("subcategories") or {}).get("name", "")
    reporter      = (ticket.get("reported_by_profile") or {}).get("full_name", "—")
    agent         = (ticket.get("assigned_agent") or {}).get("full_name", "Unassigned")
    team          = (ticket.get("agent_teams") or {}).get("name", "Unassigned")
    created_at    = ticket.get("created_at", "")[:16].replace("T", " ")
    sla_deadline  = (ticket.get("sla_deadline") or "")[:16].replace("T", " ")
    ai_conf       = ticket.get("ai_confidence", "")
    is_travelling = ticket.get("is_travelling", False)

    # SLA badge colour
    sla_colours = {"on_track": "🟢", "at_risk": "🟡", "breached": "🔴"}
    sla_icon    = sla_colours.get(sla_status, "⚪")

    priority_colours = {"P1": "🔴", "P2": "🟠", "P3": "🔵", "P4": "🟢"}
    pri_icon = priority_colours.get(priority, "⚪")

    type_icon = "🔧" if ticket_type == "issue" else "📋"

    with st.container():
        # Header row
        col1, col2, col3, col4, col5 = st.columns([3, 1.2, 1, 1.2, 1.2])
        with col1:
            travel_flag = " ✈️" if is_travelling else ""
            st.markdown(f"**{ticket_number}** {type_icon} {travel_flag}  \n{title}")
        with col2:
            st.markdown(f"📁 {category}" + (f" / {subcategory}" if subcategory else ""))
            st.caption(f"👤 {reporter}")
        with col3:
            st.markdown(f"{pri_icon} **{priority}**")
            st.caption(f"{sla_icon} {sla_status.replace('_', ' ').title()}")
        with col4:
            st.markdown(f"`{status.replace('_', ' ').title()}`")
            st.caption(f"🧑‍💻 {agent}")
        with col5:
            st.caption(f"🕐 {created_at}")
            if sla_deadline:
                st.caption(f"⏰ SLA: {sla_deadline}")

        # Expand for detail/actions
        with st.expander(f"View / Act on {ticket_number}"):
            _render_ticket_detail(ticket, profile, supabase)

        st.markdown("---")


# ── Ticket Detail & Actions ────────────────────────────────────────────────────
def _render_ticket_detail(ticket, profile, supabase):
    ticket_id   = ticket.get("id")
    role        = profile.get("role")
    status      = ticket.get("status")
    description = ticket.get("description", "")
    ai_conf     = ticket.get("ai_confidence", "")
    ai_suggested = ticket.get("ai_suggested_fields")

    tab1, tab2, tab3 = st.tabs(["📄 Details", "💬 Comments", "⚡ Actions"])

    # ── Tab 1: Details ─────────────────────────────────────────────────────────
    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Description:**  \n{description}")
            if ai_conf:
                conf_icons = {"high": "✅", "medium": "⚠️", "low": "❓"}
                st.caption(f"AI Confidence: {conf_icons.get(ai_conf, '')} {ai_conf.title()}")
            if ai_suggested:
                try:
                    ai_data = json.loads(ai_suggested) if isinstance(ai_suggested, str) else ai_suggested
                    with st.expander("🤖 AI Suggested Classification"):
                        st.json(ai_data)
                except:
                    pass
        with col2:
            st.markdown(f"**Type:** {ticket.get('type', '').replace('_', ' ').title()}")
            st.markdown(f"**Priority:** {ticket.get('priority', '—')}")
            st.markdown(f"**Status:** {status.replace('_', ' ').title()}")
            st.markdown(f"**Category:** {(ticket.get('categories') or {}).get('name', '—')}")
            st.markdown(f"**Subcategory:** {(ticket.get('subcategories') or {}).get('name', '—')}")
            st.markdown(f"**Team:** {(ticket.get('agent_teams') or {}).get('name', 'Unassigned')}")
            st.markdown(f"**Assigned To:** {(ticket.get('assigned_agent') or {}).get('full_name', 'Unassigned')}")
            created = ticket.get("created_at", "")[:16].replace("T", " ")
            resolved = (ticket.get("resolved_at") or "")[:16].replace("T", " ")
            st.markdown(f"**Created:** {created}")
            if resolved:
                st.markdown(f"**Resolved:** {resolved}")

    # ── Tab 2: Comments ────────────────────────────────────────────────────────
    with tab2:
        _render_comments(ticket_id, profile, supabase)

    # ── Tab 3: Actions ─────────────────────────────────────────────────────────
    with tab3:
        if role in ("agent", "team_lead", "admin"):
            _render_actions(ticket, profile, supabase)
        else:
            st.info("Only agents and admins can perform actions on tickets.")


# ── Comments ───────────────────────────────────────────────────────────────────
def _render_comments(ticket_id, profile, supabase):
    role = profile.get("role")

    try:
        comments_res = supabase.table("ticket_comments") \
            .select("*, author:profiles!ticket_comments_author_id_fkey(full_name)") \
            .eq("ticket_id", ticket_id) \
            .order("created_at").execute()

        comments = comments_res.data or []

        if not comments:
            st.caption("No comments yet.")
        else:
            for c in comments:
                author    = (c.get("author") or {}).get("full_name", "Unknown")
                body      = c.get("body", "")
                ts        = c.get("created_at", "")[:16].replace("T", " ")
                internal  = c.get("is_internal", False)

                if internal and role not in ("agent", "team_lead", "admin"):
                    continue

                bg = "#2c2c2c" if internal else "#1e3a5f"
                label = " 🔒 Internal" if internal else ""
                st.markdown(f"""
                <div style='background:{bg};padding:10px 14px;border-radius:8px;margin-bottom:8px;'>
                    <strong>{author}</strong>{label} <span style='color:#aaa;font-size:12px;'>{ts}</span><br>
                    {body}
                </div>""", unsafe_allow_html=True)

    except Exception as e:
        st.error(f"Could not load comments: {e}")

    # Add comment
    st.markdown("---")
    with st.form(f"comment_form_{ticket_id}"):
        comment_text = st.text_area("Add a comment", height=80, placeholder="Type your comment here...", key=f"comment_text_{ticket_id}")
        is_internal  = False
        if role in ("agent", "team_lead", "admin"):
            is_internal = st.checkbox("🔒 Internal note (not visible to employee)", key=f"internal_{ticket_id}")

        if st.form_submit_button("💬 Post Comment", type="primary"):
            if comment_text.strip():
                try:
                    supabase.table("ticket_comments").insert({
                        "ticket_id":   ticket_id,
                        "author_id":   profile.get("id"),
                        "body":        comment_text.strip(),
                        "is_internal": is_internal
                    }).execute()
                    supabase.table("ticket_activity").insert({
                        "ticket_id": ticket_id,
                        "actor_id":  profile.get("id"),
                        "action":    "comment_added",
                        "new_value": "internal" if is_internal else "public"
                    }).execute()
                    st.success("Comment posted!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not post comment: {e}")
            else:
                st.warning("Please enter a comment.")


# ── Actions ────────────────────────────────────────────────────────────────────
def _render_actions(ticket, profile, supabase):
    ticket_id = ticket.get("id")
    status    = ticket.get("status")
    role      = profile.get("role")

    col1, col2 = st.columns(2)

    # ── Status Update ──────────────────────────────────────────────────────────
    with col1:
        st.subheader("Update Status")
        status_options = {
            "new":         ["assigned", "in_progress", "on_hold", "closed"],
            "assigned":    ["in_progress", "on_hold", "resolved", "closed"],
            "in_progress": ["on_hold", "resolved", "closed"],
            "on_hold":     ["in_progress", "resolved", "closed"],
            "resolved":    ["closed"],
            "closed":      []
        }
        next_statuses = status_options.get(status, [])

        if not next_statuses:
            st.info("This ticket is closed — no further status changes.")
        else:
            new_status = st.selectbox(
                "Move to status",
                next_statuses,
                format_func=lambda x: x.replace("_", " ").title(),
                key=f"new_status_{ticket_id}"
            )
            resolution_note = ""
            if new_status == "resolved":
                resolution_note = st.text_area(
                    "Resolution notes *",
                    placeholder="Describe how the issue was resolved...",
                    key=f"resolution_{ticket_id}"
                )

            if st.button("✅ Update Status", type="primary", key=f"status_{ticket_id}"):
                if new_status == "resolved" and not resolution_note.strip():
                    st.warning("Please add resolution notes before resolving.")
                else:
                    _update_status(ticket_id, status, new_status, resolution_note, profile, supabase)

    # ── Assign Agent ──────────────────────────────────────────────────────────
    with col2:
        st.subheader("Assign Agent")
        try:
            team_id = ticket.get("assigned_team_id")
            if team_id:
                agents_res = supabase.table("profiles").select("id, full_name") \
                    .eq("agent_team_id", team_id) \
                    .in_("role", ["agent", "team_lead"]).execute()
                agents = agents_res.data or []
            else:
                agents_res = supabase.table("profiles").select("id, full_name") \
                    .in_("role", ["agent", "team_lead"]).execute()
                agents = agents_res.data or []

            if agents:
                agent_map     = {a["full_name"]: a["id"] for a in agents}
                current_agent = (ticket.get("assigned_agent") or {}).get("full_name", "")
                agent_names   = list(agent_map.keys())
                default_idx   = agent_names.index(current_agent) if current_agent in agent_names else 0

                selected_agent = st.selectbox("Assign to agent", agent_names, index=default_idx, key=f"agent_sel_{ticket_id}")

                if st.button("👤 Assign", key=f"assign_{ticket_id}"):
                    agent_id = agent_map[selected_agent]
                    try:
                        old_agent = (ticket.get("assigned_agent") or {}).get("full_name", "Unassigned")
                        supabase.table("tickets").update({
                            "assigned_to": agent_id,
                            "status":      "assigned" if status == "new" else status,
                            "assigned_at": datetime.now(timezone.utc).isoformat()
                        }).eq("id", ticket_id).execute()

                        supabase.table("ticket_activity").insert({
                            "ticket_id": ticket_id,
                            "actor_id":  profile.get("id"),
                            "action":    "assigned",
                            "old_value": old_agent,
                            "new_value": selected_agent
                        }).execute()
                        st.success(f"Assigned to {selected_agent}!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Assignment failed: {e}")
            else:
                st.info("No agents found for this team.")

        except Exception as e:
            st.error(f"Could not load agents: {e}")

        # ── Reclassify (Admin/Team Lead only) ─────────────────────────────────
        if role in ("admin", "team_lead") and ticket.get("ai_confidence") in ("low", None):
            st.markdown("---")
            st.subheader("🏷️ Reclassify Ticket")
            try:
                cats    = supabase.table("categories").select("id, name").eq("is_active", True).execute()
                cat_map = {c["name"]: c["id"] for c in cats.data} if cats.data else {}
                new_cat = st.selectbox("Category", list(cat_map.keys()), key=f"recat_{ticket_id}")

                if st.button("🏷️ Update Category", key=f"update_cat_{ticket_id}"):
                    supabase.table("tickets").update({
                        "category_id":             cat_map[new_cat],
                        "classification_verified": True
                    }).eq("id", ticket_id).execute()
                    supabase.table("ticket_activity").insert({
                        "ticket_id": ticket_id,
                        "actor_id":  profile.get("id"),
                        "action":    "reclassified",
                        "new_value": new_cat
                    }).execute()
                    st.success(f"Reclassified to {new_cat}!")
                    st.rerun()
            except Exception as e:
                st.error(f"Reclassification failed: {e}")


# ── Status Update ──────────────────────────────────────────────────────────────
def _update_status(ticket_id, old_status, new_status, resolution_note, profile, supabase):
    try:
        update_data = {"status": new_status}

        if new_status == "resolved":
            update_data["resolved_at"] = datetime.now(timezone.utc).isoformat()

        supabase.table("tickets").update(update_data).eq("id", ticket_id).execute()

        # Log activity
        activity = {
            "ticket_id": ticket_id,
            "actor_id":  profile.get("id"),
            "action":    "status_changed",
            "old_value": old_status,
            "new_value": new_status,
        }
        if resolution_note:
            activity["metadata"] = json.dumps({"resolution_note": resolution_note})
        supabase.table("ticket_activity").insert(activity).execute()

        # Add resolution note as comment if provided
        if resolution_note:
            supabase.table("ticket_comments").insert({
                "ticket_id":   ticket_id,
                "author_id":   profile.get("id"),
                "body":        f"✅ **Resolved:** {resolution_note}",
                "is_internal": False
            }).execute()

        st.success(f"Status updated to **{new_status.replace('_', ' ').title()}**!")
        st.rerun()

    except Exception as e:
        st.error(f"Status update failed: {e}")
