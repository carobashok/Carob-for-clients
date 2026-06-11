import streamlit as st
import json
from utils.supabase_client import get_supabase
from auth import get_current_profile, require_role


def admin_panel_page():
    require_role("admin")
    profile  = get_current_profile()
    supabase = get_supabase()

    st.title("⚙️ Admin Panel")
    st.markdown("Configure and manage your IT Help Desk system.")
    st.markdown("---")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "👥 Users",
        "📁 Categories",
        "🏢 Agent Teams",
        "📋 SR Types",
        "📏 SLA Rules"
    ])

    with tab1: _users_tab(supabase)
    with tab2: _categories_tab(supabase)
    with tab3: _teams_tab(supabase)
    with tab4: _sr_types_tab(supabase)
    with tab5: _sla_rules_tab(supabase)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — USERS
# ══════════════════════════════════════════════════════════════════════════════
def _users_tab(supabase):
    st.subheader("👥 User Management")

    try:
        users = supabase.table("profiles").select(
            "id, full_name, email, role, employee_id, is_active, "
            "departments(name), "
            "home_loc:locations!profiles_home_location_id_fkey(name), "
            "agent_teams(name)"
        ).order("role").execute().data or []
    except Exception as e:
        st.error(f"Could not load users: {e}")
        return

    if not users:
        st.info("No users found.")
        return

    st.markdown(f"**{len(users)} users registered**")

    # Fetch lookup data
    try:
        teams = supabase.table("agent_teams").select("id, name").eq("is_active", True).execute().data or []
        locs  = supabase.table("locations").select("id, name, code").eq("is_active", True).execute().data or []
        depts = supabase.table("departments").select("id, name").eq("is_active", True).execute().data or []
        team_map = {t["name"]: t["id"] for t in teams}
        loc_map  = {f"{l['name']} ({l['code']})": l["id"] for l in locs}
        dept_map = {d["name"]: d["id"] for d in depts}
    except:
        team_map = {}
        loc_map  = {}
        dept_map = {}

    for i, user in enumerate(users):
        uid       = user.get("id","")
        name      = user.get("full_name","")
        email     = user.get("email","")
        role      = user.get("role","employee")
        emp_id    = user.get("employee_id","—")
        active    = user.get("is_active", True)
        dept      = (user.get("departments") or {}).get("name","—")
        home_loc  = (user.get("home_loc") or {}).get("name","—")
        team      = (user.get("agent_teams") or {}).get("name","—")

        role_colours = {
            "admin": "#c0392b", "team_lead": "#8e44ad",
            "agent": "#2980b9", "employee": "#27ae60"
        }
        role_colour = role_colours.get(role, "#888")
        status_icon = "🟢" if active else "🔴"

        with st.expander(f"{status_icon} {name} — {email} | {role.replace('_',' ').title()}##{i}"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Employee ID:** {emp_id}")
                st.markdown(f"**Department:** {dept}")
                st.markdown(f"**Home Location:** {home_loc}")
                st.markdown(f"**Team:** {team}")
            with col2:
                with st.form(key=f"user_edit_{uid}_{i}"):
                    st.markdown("**Edit User**")
                    roles       = ["employee","agent","team_lead","admin"]
                    new_role    = st.selectbox("Role", roles,
                        index=roles.index(role) if role in roles else 0,
                        key=f"ur_{uid}_{i}")
                    team_names  = ["-- No Team --"] + list(team_map.keys())
                    curr_team   = team if team in team_map else "-- No Team --"
                    new_team    = st.selectbox("Agent Team", team_names,
                        index=team_names.index(curr_team) if curr_team in team_names else 0,
                        key=f"ut_{uid}_{i}")
                    loc_names   = ["-- No Change --"] + list(loc_map.keys())
                    new_loc     = st.selectbox("Home Location", loc_names,
                        key=f"ul_{uid}_{i}")
                    new_active  = st.checkbox("Active", value=active, key=f"ua_{uid}_{i}")

                    if st.form_submit_button("💾 Save Changes", type="primary"):
                        try:
                            update = {
                                "role":          new_role,
                                "is_active":     new_active,
                                "agent_team_id": team_map.get(new_team) if new_team != "-- No Team --" else None,
                            }
                            if new_loc != "-- No Change --":
                                update["home_location_id"]    = loc_map[new_loc]
                                update["current_location_id"] = loc_map[new_loc]
                            supabase.table("profiles").update(update).eq("id", uid).execute()
                            st.success(f"✅ {name} updated!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Update failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — CATEGORIES
# ══════════════════════════════════════════════════════════════════════════════
def _categories_tab(supabase):
    st.subheader("📁 Category Management")

    # Fetch teams for routing
    try:
        teams    = supabase.table("agent_teams").select("id, name").eq("is_active", True).execute().data or []
        team_map = {t["name"]: t["id"] for t in teams}
    except:
        team_map = {}

    # ── Add new category ───────────────────────────────────────────────────────
    with st.expander("➕ Add New Category"):
        with st.form("add_category_form"):
            col1, col2 = st.columns(2)
            with col1:
                cat_name  = st.text_input("Category Name *")
                cat_code  = st.text_input("Code *", help="Short code e.g. HW, NET")
                cat_desc  = st.text_area("Description", height=80)
            with col2:
                sla_hours = st.number_input("SLA Hours *", min_value=0.5, max_value=168.0, value=8.0, step=0.5)
                routing   = st.selectbox("Routing Basis",
                    ["location","region","central","application"],
                    format_func=lambda x: x.title())
                team_names = ["-- No Default Team --"] + list(team_map.keys())
                def_team  = st.selectbox("Default Team", team_names)

            if st.form_submit_button("➕ Add Category", type="primary"):
                if not cat_name or not cat_code:
                    st.error("Name and code are required.")
                else:
                    try:
                        supabase.table("categories").insert({
                            "name":            cat_name.strip(),
                            "code":            cat_code.strip().upper(),
                            "description":     cat_desc.strip(),
                            "sla_hours":       sla_hours,
                            "routing_basis":   routing,
                            "default_team_id": team_map.get(def_team) if def_team != "-- No Default Team --" else None,
                            "is_active":       True
                        }).execute()
                        st.success(f"✅ Category '{cat_name}' added!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

    st.markdown("---")

    # ── Existing categories ────────────────────────────────────────────────────
    try:
        cats = supabase.table("categories").select(
            "*, agent_teams(name)"
        ).order("name").execute().data or []
    except Exception as e:
        st.error(f"Could not load categories: {e}")
        return

    for i, cat in enumerate(cats):
        cid       = cat.get("id","")
        cname     = cat.get("name","")
        ccode     = cat.get("code","")
        cdesc     = cat.get("description","")
        sla       = cat.get("sla_hours", 8)
        routing   = cat.get("routing_basis","location")
        active    = cat.get("is_active", True)
        def_team  = (cat.get("agent_teams") or {}).get("name","—")
        status_icon = "🟢" if active else "🔴"

        with st.expander(f"{status_icon} {cname} ({ccode}) — SLA: {sla}h | Routing: {routing}##{i}"):
            col1, col2 = st.columns([1.5, 1])

            with col1:
                with st.form(key=f"edit_cat_{cid}_{i}"):
                    new_name  = st.text_input("Name", value=cname, key=f"cn_{cid}_{i}")
                    new_sla   = st.number_input("SLA Hours", value=float(sla),
                        min_value=0.5, max_value=168.0, step=0.5, key=f"cs_{cid}_{i}")
                    rout_opts = ["location","region","central","application"]
                    new_rout  = st.selectbox("Routing Basis", rout_opts,
                        index=rout_opts.index(routing) if routing in rout_opts else 0,
                        key=f"cr_{cid}_{i}")
                    team_names = ["-- No Default Team --"] + list(team_map.keys())
                    curr_team  = def_team if def_team in team_map else "-- No Default Team --"
                    new_team   = st.selectbox("Default Team", team_names,
                        index=team_names.index(curr_team) if curr_team in team_names else 0,
                        key=f"ct_{cid}_{i}")
                    new_active = st.checkbox("Active", value=active, key=f"ca_{cid}_{i}")

                    if st.form_submit_button("💾 Save", type="primary"):
                        try:
                            supabase.table("categories").update({
                                "name":            new_name.strip(),
                                "sla_hours":       new_sla,
                                "routing_basis":   new_rout,
                                "default_team_id": team_map.get(new_team) if new_team != "-- No Default Team --" else None,
                                "is_active":       new_active
                            }).eq("id", cid).execute()
                            st.success("✅ Category updated!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")

            with col2:
                st.markdown("**Subcategories**")
                try:
                    subcats = supabase.table("subcategories").select("id, name, is_active") \
                        .eq("category_id", cid).execute().data or []
                    for sc in subcats:
                        sc_icon = "🟢" if sc.get("is_active") else "🔴"
                        st.caption(f"{sc_icon} {sc['name']}")
                except:
                    pass

                st.markdown("---")
                with st.form(key=f"add_sub_{cid}_{i}"):
                    new_sub  = st.text_input("New Subcategory", key=f"nsn_{cid}_{i}")
                    new_subc = st.text_input("Code", key=f"nsc_{cid}_{i}")
                    if st.form_submit_button("➕ Add"):
                        if new_sub.strip():
                            try:
                                supabase.table("subcategories").insert({
                                    "category_id": cid,
                                    "name":        new_sub.strip(),
                                    "code":        new_subc.strip().upper() or new_sub[:3].upper(),
                                    "is_active":   True
                                }).execute()
                                st.success(f"✅ Subcategory added!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — AGENT TEAMS
# ══════════════════════════════════════════════════════════════════════════════
def _teams_tab(supabase):
    st.subheader("🏢 Agent Team Management")

    try:
        regions = supabase.table("regions").select("id, name, code").execute().data or []
        locs    = supabase.table("locations").select("id, name, code").eq("is_active", True).execute().data or []
        region_map = {r["name"]: r["id"] for r in regions}
        loc_map    = {f"{l['name']} ({l['code']})": l["id"] for l in locs}
    except:
        region_map = {}
        loc_map    = {}

    # ── Add new team ───────────────────────────────────────────────────────────
    with st.expander("➕ Add New Agent Team"):
        with st.form("add_team_form"):
            col1, col2 = st.columns(2)
            with col1:
                team_name = st.text_input("Team Name *")
                team_type = st.selectbox("Team Type",
                    ["local_support","app_support","network","access","admin"],
                    format_func=lambda x: x.replace("_"," ").title())
            with col2:
                region_names = ["-- Central (No Region) --"] + list(region_map.keys())
                sel_region   = st.selectbox("Region", region_names)
                loc_names    = ["-- Central (No Location) --"] + list(loc_map.keys())
                sel_loc      = st.selectbox("Location", loc_names)

            if st.form_submit_button("➕ Add Team", type="primary"):
                if not team_name:
                    st.error("Team name is required.")
                else:
                    try:
                        supabase.table("agent_teams").insert({
                            "name":        team_name.strip(),
                            "team_type":   team_type,
                            "region_id":   region_map.get(sel_region) if sel_region != "-- Central (No Region) --" else None,
                            "location_id": loc_map.get(sel_loc) if sel_loc != "-- Central (No Location) --" else None,
                            "is_active":   True
                        }).execute()
                        st.success(f"✅ Team '{team_name}' added!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

    st.markdown("---")

    # ── Existing teams ─────────────────────────────────────────────────────────
    try:
        teams = supabase.table("agent_teams").select(
            "*, regions(name), locations(name)"
        ).order("team_type").execute().data or []
    except Exception as e:
        st.error(f"Could not load teams: {e}")
        return

    for i, team in enumerate(teams):
        tid      = team.get("id","")
        tname    = team.get("name","")
        ttype    = team.get("team_type","")
        active   = team.get("is_active", True)
        region   = (team.get("regions") or {}).get("name","Central")
        location = (team.get("locations") or {}).get("name","All Locations")
        status_icon = "🟢" if active else "🔴"

        with st.expander(f"{status_icon} {tname} | {ttype.replace('_',' ').title()} | {region} / {location}##{i}"):
            # Show team members
            try:
                members = supabase.table("profiles").select("full_name, role, email") \
                    .eq("agent_team_id", tid).execute().data or []
                if members:
                    st.markdown(f"**Team Members ({len(members)}):**")
                    for m in members:
                        st.caption(f"👤 {m['full_name']} ({m['role'].replace('_',' ').title()}) — {m['email']}")
                else:
                    st.caption("No members assigned yet.")
            except:
                pass

            with st.form(key=f"edit_team_{tid}_{i}"):
                new_active = st.checkbox("Active", value=active, key=f"ta_{tid}_{i}")
                new_name   = st.text_input("Team Name", value=tname, key=f"tn_{tid}_{i}")
                if st.form_submit_button("💾 Save", type="primary"):
                    try:
                        supabase.table("agent_teams").update({
                            "name": new_name.strip(), "is_active": new_active
                        }).eq("id", tid).execute()
                        st.success("✅ Team updated!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — SR TYPES
# ══════════════════════════════════════════════════════════════════════════════
def _sr_types_tab(supabase):
    st.subheader("📋 Service Request Types")
    st.caption("Configure SR types, approval requirements, and approval chains.")

    try:
        cats = supabase.table("categories").select("id, name").eq("is_active", True).execute().data or []
        cat_map = {c["name"]: c["id"] for c in cats}
    except:
        cat_map = {}

    # ── Add SR type ────────────────────────────────────────────────────────────
    with st.expander("➕ Add New SR Type"):
        with st.form("add_sr_form"):
            col1, col2 = st.columns(2)
            with col1:
                sr_name      = st.text_input("SR Type Name *")
                cat_names    = ["-- No Category --"] + list(cat_map.keys())
                sr_cat       = st.selectbox("Category", cat_names)
                sr_sla       = st.number_input("SLA Hours", min_value=0.5, max_value=168.0,
                    value=8.0, step=0.5)
            with col2:
                req_approval = st.checkbox("Requires Approval", value=True)
                auto_fulfill = st.checkbox("Auto-Fulfill (no agent needed)", value=False)
                st.markdown("**Approval Chain** (JSON)")
                st.caption('Example: [{"step":1,"approver":"manager"},{"step":2,"approver":"it_admin"}]')
                chain_json   = st.text_area("Approval Chain JSON", height=100,
                    value='[{"step":1,"approver":"manager"},{"step":2,"approver":"it_admin"}]')

            if st.form_submit_button("➕ Add SR Type", type="primary"):
                if not sr_name:
                    st.error("SR type name is required.")
                else:
                    try:
                        chain = json.loads(chain_json) if chain_json.strip() else None
                        supabase.table("sr_types").insert({
                            "name":             sr_name.strip(),
                            "category_id":      cat_map.get(sr_cat) if sr_cat != "-- No Category --" else None,
                            "requires_approval": req_approval,
                            "auto_fulfill":      auto_fulfill,
                            "approval_chain":    chain,
                            "sla_hours":         sr_sla,
                            "is_active":         True
                        }).execute()
                        st.success(f"✅ SR Type '{sr_name}' added!")
                        st.rerun()
                    except json.JSONDecodeError:
                        st.error("Invalid JSON in approval chain.")
                    except Exception as e:
                        st.error(f"Error: {e}")

    st.markdown("---")

    # ── Existing SR types ──────────────────────────────────────────────────────
    try:
        sr_types = supabase.table("sr_types").select(
            "*, categories(name)"
        ).order("name").execute().data or []
    except Exception as e:
        st.error(f"Could not load SR types: {e}")
        return

    for i, sr in enumerate(sr_types):
        sid      = sr.get("id","")
        sname    = sr.get("name","")
        cat      = (sr.get("categories") or {}).get("name","—")
        req_app  = sr.get("requires_approval", True)
        auto_ful = sr.get("auto_fulfill", False)
        sla      = sr.get("sla_hours", 8)
        chain    = sr.get("approval_chain")
        active   = sr.get("is_active", True)
        status_icon = "🟢" if active else "🔴"
        app_icon    = "✅" if req_app else "⏭️"

        with st.expander(f"{status_icon} {sname} | {cat} | {app_icon} Approval | SLA: {sla}h##{i}"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Approval Chain:**")
                if chain:
                    chain_data = chain if isinstance(chain, list) else json.loads(chain)
                    for step in chain_data:
                        st.caption(f"Step {step.get('step','?')}: {step.get('approver','?').replace('_',' ').title()}")
                else:
                    st.caption("No approval chain configured.")
            with col2:
                with st.form(key=f"edit_sr_{sid}_{i}"):
                    new_req  = st.checkbox("Requires Approval", value=req_app, key=f"sra_{sid}_{i}")
                    new_auto = st.checkbox("Auto-Fulfill", value=auto_ful, key=f"srf_{sid}_{i}")
                    new_sla  = st.number_input("SLA Hours", value=float(sla),
                        min_value=0.5, max_value=168.0, step=0.5, key=f"srs_{sid}_{i}")
                    new_act  = st.checkbox("Active", value=active, key=f"srx_{sid}_{i}")
                    if st.form_submit_button("💾 Save", type="primary"):
                        try:
                            supabase.table("sr_types").update({
                                "requires_approval": new_req,
                                "auto_fulfill":      new_auto,
                                "sla_hours":         new_sla,
                                "is_active":         new_act
                            }).eq("id", sid).execute()
                            st.success("✅ SR Type updated!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — SLA RULES
# ══════════════════════════════════════════════════════════════════════════════
def _sla_rules_tab(supabase):
    st.subheader("📏 SLA Rules")
    st.caption("SLA rules override the category default when a specific priority is matched.")

    try:
        cats = supabase.table("categories").select("id, name, sla_hours").execute().data or []
        cat_map = {c["name"]: c["id"] for c in cats}
    except:
        cat_map = {}

    # ── Category SLA quick edit ────────────────────────────────────────────────
    st.markdown("### Default SLA per Category")
    st.caption("These are the base SLA hours used when no priority-specific rule exists.")

    try:
        for i, cat in enumerate(cats):
            cid   = cat.get("id","")
            cname = cat.get("name","")
            csla  = cat.get("sla_hours", 8)

            col1, col2, col3 = st.columns([2, 1, 1])
            with col1: st.markdown(f"**{cname}**")
            with col2: new_sla = st.number_input("Hours", value=float(csla),
                min_value=0.5, max_value=168.0, step=0.5,
                key=f"cat_sla_{cid}_{i}", label_visibility="collapsed")
            with col3:
                if st.button("💾 Save", key=f"cat_sla_btn_{cid}_{i}"):
                    try:
                        supabase.table("categories").update(
                            {"sla_hours": new_sla}
                        ).eq("id", cid).execute()
                        st.success(f"✅ {cname} SLA updated to {new_sla}h!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
    except Exception as e:
        st.error(f"Could not load categories: {e}")

    st.markdown("---")
    st.markdown("### Priority-Specific SLA Rules")
    st.caption("Add rules for specific Category + Priority combinations.")

    # ── Add SLA rule ───────────────────────────────────────────────────────────
    with st.expander("➕ Add Priority-Specific Rule"):
        with st.form("add_sla_rule"):
            col1, col2, col3 = st.columns(3)
            with col1:
                cat_names = ["-- Select --"] + list(cat_map.keys())
                sel_cat   = st.selectbox("Category *", cat_names)
            with col2:
                sel_pri = st.selectbox("Priority", ["P1","P2","P3","P4"])
            with col3:
                rule_sla = st.number_input("SLA Hours *", min_value=0.5,
                    max_value=168.0, value=4.0, step=0.5)

            if st.form_submit_button("➕ Add Rule", type="primary"):
                if sel_cat == "-- Select --":
                    st.error("Please select a category.")
                else:
                    try:
                        supabase.table("sla_rules").upsert({
                            "category_id": cat_map[sel_cat],
                            "priority":    sel_pri,
                            "sla_hours":   rule_sla,
                            "is_active":   True
                        }, on_conflict="category_id,priority").execute()
                        st.success(f"✅ Rule added: {sel_cat} / {sel_pri} = {rule_sla}h")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

    # ── Existing rules ─────────────────────────────────────────────────────────
    try:
        rules = supabase.table("sla_rules").select(
            "*, categories(name)"
        ).eq("is_active", True).order("category_id").execute().data or []

        if rules:
            import pandas as pd
            rules_df = pd.DataFrame([{
                "Category": (r.get("categories") or {}).get("name","—"),
                "Priority": r.get("priority","—"),
                "SLA Hours": r.get("sla_hours","—"),
                "Active": "✅" if r.get("is_active") else "🔴"
            } for r in rules])
            st.dataframe(rules_df, use_container_width=True, hide_index=True)
        else:
            st.info("No priority-specific rules yet. Base category SLA hours apply.")
    except Exception as e:
        st.error(f"Could not load SLA rules: {e}")
