import streamlit as st
import json
import anthropic
from utils.supabase_client import get_supabase
from auth import get_current_profile, get_current_user_id


def raise_ticket_page():
    st.title("➕ Raise a Ticket")
    st.markdown("Describe your issue or request in plain English — our AI will classify it automatically.")
    st.markdown("---")

    profile = get_current_profile()
    supabase = get_supabase()

    # ── Location check (travelling employee) ──────────────────────────────────
    home_loc    = (profile.get("locations") or {}).get("name", "your home location")
    current_loc_id = profile.get("current_location_id")
    home_loc_id    = profile.get("home_location_id")

    if current_loc_id and home_loc_id and current_loc_id != home_loc_id:
        st.info(f"📍 You are currently away from **{home_loc}**. Ticket will be routed based on your current location.")
    else:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.info(f"🏠 Your home location: **{home_loc}**. Are you currently at a different location?")
        with col2:
            if st.button("📍 Update Location", use_container_width=True):
                st.session_state["show_location_update"] = True

    # Location update widget
    if st.session_state.get("show_location_update"):
        _location_update_widget(profile, supabase)

    st.markdown("---")

    # ── Main ticket form ───────────────────────────────────────────────────────
    st.subheader("📝 Describe Your Issue or Request")

    description = st.text_area(
        "What's happening? What do you need?",
        placeholder="e.g. My laptop is not connecting to the office WiFi since this morning...\n"
                    "or: I need access to the Salesforce CRM for my new role in Sales.",
        height=150,
        key="ticket_description"
    )

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        classify_btn = st.button("🤖 Classify with AI", type="primary", use_container_width=True,
                                  disabled=len(description.strip()) < 10)
    with col2:
        if st.button("🔄 Clear", use_container_width=True):
            st.session_state.pop("ai_classification", None)
            st.session_state.pop("ticket_description", None)
            st.rerun()

    if len(description.strip()) < 10 and description.strip():
        st.caption("Please provide a bit more detail (at least 10 characters).")

    # ── AI Classification ──────────────────────────────────────────────────────
    if classify_btn and description.strip():
        with st.spinner("🤖 AI is analysing your description..."):
            classification = _classify_with_ai(description, supabase)
            st.session_state["ai_classification"] = classification
            st.session_state["saved_description"] = description

    # ── Show classification result & submission form ───────────────────────────
    if st.session_state.get("ai_classification"):
        cls = st.session_state["ai_classification"]
        desc = st.session_state.get("saved_description", description)
        _show_classification_and_submit(cls, desc, profile, supabase)


# ── AI Classification Function ─────────────────────────────────────────────────
def _classify_with_ai(description: str, supabase) -> dict:
    """Call Claude API to classify the ticket."""
    try:
        # Fetch active categories for context
        cats = supabase.table("categories").select("name, code, description").eq("is_active", True).execute()
        cat_list = "\n".join([f"- {c['name']} ({c['code']}): {c['description']}" for c in cats.data]) if cats.data else ""

        # Fetch SR types
        sr_types = supabase.table("sr_types").select("name").eq("is_active", True).execute()
        sr_list = "\n".join([f"- {s['name']}" for s in sr_types.data]) if sr_types.data else ""

        client = anthropic.Anthropic(api_key=st.secrets["anthropic"]["api_key"])

        prompt = f"""You are an IT Help Desk ticket classification assistant.

Analyse the following user description and classify it accurately.

Available Categories:
{cat_list}

Available Service Request Types:
{sr_list}

User Description:
\"{description}\"

Respond ONLY with a valid JSON object — no explanation, no markdown, no backticks.

JSON format:
{{
  "ticket_type": "issue" or "service_request",
  "category": "<category name from the list above>",
  "category_code": "<category code>",
  "subcategory": "<most relevant subcategory>",
  "priority": "P1" or "P2" or "P3" or "P4",
  "sr_type": "<SR type name if service_request, else null>",
  "confidence": "high" or "medium" or "low",
  "reasoning": "<one sentence explaining your classification>",
  "suggested_title": "<a concise ticket title, max 10 words>"
}}

Priority guide:
- P1: Critical — complete work stoppage, major outage, security breach
- P2: High — significant impact, workaround exists but difficult
- P3: Medium — partial impact, reasonable workaround available
- P4: Low — minor issue, cosmetic, general query

If you cannot classify with reasonable confidence, set confidence to "low" and category to "Others"."""

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = response.content[0].text.strip()
        # Strip markdown fences if present
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        return {"success": True, "data": result}

    except json.JSONDecodeError:
        return {"success": False, "error": "AI returned an unexpected response. Please try again."}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Classification Result + Submit Form ────────────────────────────────────────
def _show_classification_and_submit(cls: dict, description: str, profile: dict, supabase):

    if not cls.get("success"):
        st.error(f"Classification failed: {cls.get('error', 'Unknown error')}")
        return

    data = cls["data"]
    confidence = data.get("confidence", "low")

    st.markdown("---")
    st.subheader("🤖 AI Classification Result")

    # Confidence banner
    if confidence == "high":
        st.success("✅ High Confidence — AI is confident about this classification.")
    elif confidence == "medium":
        st.warning("⚠️ Medium Confidence — Please review and correct if needed.")
    else:
        st.error("❓ Low Confidence — AI could not classify reliably. Ticket will go to IT Admin for review.")

    # Classification display
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Type", "🔧 Issue" if data.get("ticket_type") == "issue" else "📋 Service Request")
    with col2:
        st.metric("Category", data.get("category", "Others"))
    with col3:
        st.metric("Subcategory", data.get("subcategory", "—"))
    with col4:
        priority_icons = {"P1": "🔴", "P2": "🟠", "P3": "🔵", "P4": "🟢"}
        p = data.get("priority", "P3")
        st.metric("Priority", f"{priority_icons.get(p, '')} {p}")

    st.caption(f"💬 AI reasoning: *{data.get('reasoning', '')}*")

    st.markdown("---")
    st.subheader("✏️ Review & Submit")
    st.markdown("You can modify any field before submitting.")

    with st.form("ticket_submit_form"):

        # Title
        title = st.text_input(
            "Ticket Title *",
            value=data.get("suggested_title", ""),
            help="A concise summary of your issue or request"
        )

        # Description (read-only recap)
        st.text_area("Your Description", value=description, disabled=True, height=100)

        col1, col2 = st.columns(2)

        with col1:
            # Ticket type
            ticket_type = st.selectbox(
                "Ticket Type *",
                ["issue", "service_request"],
                index=0 if data.get("ticket_type") == "issue" else 1,
                format_func=lambda x: "🔧 Issue" if x == "issue" else "📋 Service Request"
            )

            # Priority
            priority_options = ["P1", "P2", "P3", "P4"]
            priority = st.selectbox(
                "Priority *",
                priority_options,
                index=priority_options.index(data.get("priority", "P3")),
                help="P1=Critical, P2=High, P3=Medium, P4=Low"
            )

        with col2:
            # Category from DB
            try:
                cats = supabase.table("categories").select("id, name").eq("is_active", True).execute()
                cat_map = {c["name"]: c["id"] for c in cats.data} if cats.data else {}
                cat_names = list(cat_map.keys())
                default_cat = data.get("category", "Others")
                cat_index = cat_names.index(default_cat) if default_cat in cat_names else 0
                selected_cat_name = st.selectbox("Category *", cat_names, index=cat_index)
                selected_cat_id = cat_map.get(selected_cat_name)
            except:
                selected_cat_name = data.get("category", "Others")
                selected_cat_id = None
                st.text_input("Category", value=selected_cat_name, disabled=True)

            # Subcategory from DB
            try:
                if selected_cat_id:
                    subcats = supabase.table("subcategories").select("id, name") \
                        .eq("category_id", selected_cat_id).eq("is_active", True).execute()
                    subcat_map = {s["name"]: s["id"] for s in subcats.data} if subcats.data else {}
                    subcat_names = ["-- Not sure --"] + list(subcat_map.keys())
                    ai_sub = data.get("subcategory", "")
                    sub_index = subcat_names.index(ai_sub) if ai_sub in subcat_names else 0
                    selected_sub_name = st.selectbox("Subcategory", subcat_names, index=sub_index)
                    selected_sub_id = subcat_map.get(selected_sub_name)
                else:
                    selected_sub_id = None
                    st.selectbox("Subcategory", ["-- Not sure --"])
            except:
                selected_sub_id = None

        # SR Type (only if service request)
        sr_type_id = None
        if ticket_type == "service_request":
            try:
                sr_types = supabase.table("sr_types").select("id, name").eq("is_active", True).execute()
                sr_map = {s["name"]: s["id"] for s in sr_types.data} if sr_types.data else {}
                sr_names = ["-- Select SR Type --"] + list(sr_map.keys())
                ai_sr = data.get("sr_type", "")
                sr_index = sr_names.index(ai_sr) if ai_sr in sr_names else 0
                selected_sr = st.selectbox("Service Request Type *", sr_names, index=sr_index)
                sr_type_id = sr_map.get(selected_sr)
            except:
                pass

        submitted = st.form_submit_button("🎫 Submit Ticket", type="primary", use_container_width=True)

        if submitted:
            if not title.strip():
                st.error("Please provide a ticket title.")
                return

            _submit_ticket(
                title=title,
                description=description,
                ticket_type=ticket_type,
                priority=priority,
                category_id=selected_cat_id,
                subcategory_id=selected_sub_id,
                sr_type_id=sr_type_id,
                ai_confidence=confidence,
                ai_suggested=data,
                profile=profile,
                supabase=supabase
            )


# ── Submit Ticket to Supabase ──────────────────────────────────────────────────
def _submit_ticket(title, description, ticket_type, priority, category_id,
                   subcategory_id, sr_type_id, ai_confidence, ai_suggested,
                   profile, supabase):
    try:
        user_id      = profile.get("id")
        location_id  = profile.get("current_location_id") or profile.get("home_location_id")
        is_travelling = profile.get("current_location_id") != profile.get("home_location_id")

        # Get SLA hours from category
        sla_hours = 24  # default
        if category_id:
            cat = supabase.table("categories").select("sla_hours").eq("id", category_id).single().execute()
            if cat.data:
                sla_hours = float(cat.data["sla_hours"])

        # Calculate SLA deadline
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        sla_deadline = (now + timedelta(hours=sla_hours)).isoformat()

        # Get auto-routing team
        team_id = _get_routing_team(category_id, location_id, supabase)

        # Determine initial status
        if ticket_type == "service_request" and sr_type_id:
            sr = supabase.table("sr_types").select("requires_approval, auto_fulfill") \
                .eq("id", sr_type_id).single().execute()
            if sr.data and sr.data.get("auto_fulfill"):
                initial_status = "in_progress"
            elif sr.data and sr.data.get("requires_approval"):
                initial_status = "pending_approval"
            else:
                initial_status = "new"
        else:
            initial_status = "new"

        # Build ticket payload — status uses correct enum value
        ticket = {
            "type":                     ticket_type,
            "title":                    title.strip(),
            "description":              description.strip(),
            "priority":                 priority,
            "status":                   initial_status if ticket_type == "issue" else "new",
            "category_id":              category_id,
            "subcategory_id":           subcategory_id,
            "sr_type_id":               sr_type_id,
            "ai_confidence":            ai_confidence,
            "ai_suggested_fields":      json.dumps(ai_suggested),
            "classification_verified":  False,
            "reported_by":              user_id,
            "assigned_team_id":         team_id,
            "raised_from_location_id":  location_id,
            "is_travelling":            is_travelling,
            "sla_hours":                sla_hours,
            "sla_deadline":             sla_deadline,
            "sla_status":               "on_track",
        }

        res = supabase.table("tickets").insert(ticket).execute()

        if res.data:
            ticket_number = res.data[0].get("ticket_number", "")
            ticket_id     = res.data[0].get("id")

            # Log activity
            supabase.table("ticket_activity").insert({
                "ticket_id":  ticket_id,
                "actor_id":   user_id,
                "action":     "ticket_created",
                "new_value":  "new",
                "metadata":   json.dumps({"ai_confidence": ai_confidence})
            }).execute()

            # Create SR approval records if needed
            if ticket_type == "service_request" and sr_type_id:
                _create_approval_records(ticket_id, sr_type_id, profile, supabase)

            # Clear session state
            st.session_state.pop("ai_classification", None)
            st.session_state.pop("saved_description", None)

            st.success(f"✅ Ticket **{ticket_number}** submitted successfully!")
            st.balloons()

            # Summary
            st.markdown(f"""
            | Field | Value |
            |---|---|
            | Ticket Number | `{ticket_number}` |
            | Type | {ticket_type.replace('_', ' ').title()} |
            | Priority | {priority} |
            | SLA Deadline | {sla_deadline[:16].replace('T', ' ')} UTC |
            | Status | {'Pending Approval' if 'pending' in (initial_status or '') else 'New'} |
            """)
        else:
            st.error("Failed to submit ticket. Please try again.")

    except Exception as e:
        st.error(f"Error submitting ticket: {str(e)}")


# ── Auto-routing Team Lookup ───────────────────────────────────────────────────
def _get_routing_team(category_id, location_id, supabase):
    """Determine which agent team to route to based on category and location."""
    try:
        if not category_id:
            # Route to IT Admin team
            team = supabase.table("agent_teams").select("id") \
                .eq("team_type", "admin").limit(1).execute()
            return team.data[0]["id"] if team.data else None

        cat = supabase.table("categories").select("routing_basis, default_team_id, code") \
            .eq("id", category_id).single().execute()

        if not cat.data:
            return None

        routing_basis = cat.data.get("routing_basis")
        default_team  = cat.data.get("default_team_id")

        if routing_basis == "central" or routing_basis == "application":
            return default_team

        elif routing_basis == "location" and location_id:
            # Find local support team for this location
            team = supabase.table("agent_teams").select("id") \
                .eq("team_type", "local_support") \
                .eq("location_id", location_id).limit(1).execute()
            return team.data[0]["id"] if team.data else default_team

        elif routing_basis == "region" and location_id:
            # Get region of the location
            loc = supabase.table("locations").select("region_id").eq("id", location_id).single().execute()
            if loc.data:
                region_id = loc.data["region_id"]
                team = supabase.table("agent_teams").select("id") \
                    .eq("team_type", "network") \
                    .eq("region_id", region_id).limit(1).execute()
                return team.data[0]["id"] if team.data else default_team

        return default_team

    except:
        return None


# ── SR Approval Records ────────────────────────────────────────────────────────
def _create_approval_records(ticket_id: str, sr_type_id: str, profile: dict, supabase):
    """Create approval step records for a service request."""
    try:
        sr = supabase.table("sr_types").select("approval_chain, requires_approval") \
            .eq("id", sr_type_id).single().execute()

        if not sr.data or not sr.data.get("requires_approval"):
            return

        chain = sr.data.get("approval_chain") or []
        if isinstance(chain, str):
            chain = json.loads(chain)

        for step in chain:
            approver_role = step.get("approver", "it_admin")

            # Find approver based on role
            approver_id = _find_approver(approver_role, profile, supabase)

            if approver_id:
                supabase.table("sr_approvals").insert({
                    "ticket_id":     ticket_id,
                    "step_number":   step.get("step", 1),
                    "approver_id":   approver_id,
                    "approver_role": approver_role,
                    "status":        "pending"
                }).execute()
    except:
        pass


def _find_approver(role, profile, supabase):
    """Find the appropriate approver user ID for a given role."""
    try:
        if role == "manager":
            return profile.get("manager_id")
        elif role in ("it_admin", "admin"):
            admin = supabase.table("profiles").select("id") \
                .eq("role", "admin").limit(1).execute()
            return admin.data[0]["id"] if admin.data else None
        elif role == "hr":
            hr = supabase.table("profiles").select("id") \
                .eq("role", "admin").limit(1).execute()
            return hr.data[0]["id"] if hr.data else None
        return None
    except:
        return None


# ── Location Update Widget ─────────────────────────────────────────────────────
def _location_update_widget(profile: dict, supabase):
    with st.expander("📍 Update Current Location", expanded=True):
        try:
            locs = supabase.table("locations").select("id, name, code") \
                .eq("is_active", True).execute()
            loc_map = {f"{l['name']} ({l['code']})": l["id"] for l in locs.data} if locs.data else {}

            selected = st.selectbox("Select your current location", list(loc_map.keys()))

            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Update", type="primary"):
                    new_loc_id = loc_map[selected]
                    supabase.table("profiles").update(
                        {"current_location_id": new_loc_id}
                    ).eq("id", profile["id"]).execute()
                    st.session_state["profile"]["current_location_id"] = new_loc_id
                    st.session_state["show_location_update"] = False
                    st.success("Location updated!")
                    st.rerun()
            with col2:
                if st.button("Cancel"):
                    st.session_state["show_location_update"] = False
                    st.rerun()
        except Exception as e:
            st.error(f"Could not load locations: {e}")
