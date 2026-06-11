import streamlit as st
import anthropic
import json
from datetime import datetime, timezone, timedelta
from utils.supabase_client import get_supabase
from auth import require_role, get_current_profile


def ai_insights_page():
    require_role("agent","team_lead","admin")
    supabase = get_supabase()
    profile  = get_current_profile()

    st.title("💡 AI Insights")
    st.markdown("Claude analyses your live ticket data and surfaces trends, anomalies, and recommendations.")
    st.markdown("---")

    # ── Controls ───────────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns([1,1,2])
    with col1:
        days = st.selectbox("Analyse last", [7,14,30,60,90],
            format_func=lambda x: f"{x} days", key="ai_days")
    with col2:
        focus = st.selectbox("Focus area", [
            "All — Full Overview",
            "SLA Performance",
            "Agent Workload",
            "Category Trends",
            "Anomalies Only"
        ], key="ai_focus")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        generate_btn = st.button("🤖 Generate Insights", type="primary", use_container_width=True)

    # ── Previous insights ──────────────────────────────────────────────────────
    st.markdown("---")

    if "ai_insight_result" in st.session_state:
        _render_insight(st.session_state["ai_insight_result"])

    if generate_btn:
        with st.spinner("🤖 Claude is analysing your ticket data..."):
            result = _generate_insights(supabase, profile, days, focus)
            st.session_state["ai_insight_result"] = result
            st.rerun()

    # ── Past insights log ──────────────────────────────────────────────────────
    if "ai_insight_result" not in st.session_state:
        _render_past_insights(supabase)


def _generate_insights(supabase, profile, days, focus):
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        # Fetch tickets
        tickets = supabase.table("tickets").select(
            "type, status, priority, sla_status, created_at, resolved_at, "
            "categories(name), "
            "assigned_agent:profiles!tickets_assigned_to_fkey(full_name), "
            "agent_teams(name)"
        ).gte("created_at", since).execute().data or []

        if not tickets:
            return {"success": False, "error": "No ticket data found for the selected period."}

        # Build summary stats for the prompt
        total     = len(tickets)
        open_t    = len([t for t in tickets if t["status"] not in ("resolved","closed")])
        resolved  = len([t for t in tickets if t["status"] in ("resolved","closed")])
        breached  = len([t for t in tickets if t["sla_status"] == "breached"])
        at_risk   = len([t for t in tickets if t["sla_status"] == "at_risk"])
        p1_count  = len([t for t in tickets if t["priority"] == "P1"])
        p2_count  = len([t for t in tickets if t["priority"] == "P2"])

        # Category breakdown
        cat_counts = {}
        for t in tickets:
            cat = (t.get("categories") or {}).get("name","Others")
            cat_counts[cat] = cat_counts.get(cat,0) + 1

        # Agent workload
        agent_counts = {}
        for t in tickets:
            if t["status"] not in ("resolved","closed"):
                agent = (t.get("assigned_agent") or {}).get("full_name","Unassigned")
                agent_counts[agent] = agent_counts.get(agent,0) + 1

        # Category SLA breach
        cat_breach = {}
        for t in tickets:
            cat = (t.get("categories") or {}).get("name","Others")
            if cat not in cat_breach:
                cat_breach[cat] = {"total":0,"breached":0}
            cat_breach[cat]["total"] += 1
            if t["sla_status"] == "breached":
                cat_breach[cat]["breached"] += 1

        focus_instruction = {
            "All — Full Overview":  "Provide a comprehensive overview covering all areas.",
            "SLA Performance":      "Focus specifically on SLA performance, breaches, and at-risk tickets.",
            "Agent Workload":       "Focus on agent workload distribution, overloaded agents, and reassignment recommendations.",
            "Category Trends":      "Focus on category-wise ticket trends, spikes, and patterns.",
            "Anomalies Only":       "Focus only on anomalies — unusual spikes, patterns, or concerning trends."
        }.get(focus, "Provide a comprehensive overview.")

        prompt = f"""You are an IT Help Desk analytics expert. Analyse the following ticket data for the last {days} days and provide actionable insights.

FOCUS: {focus_instruction}

SUMMARY STATISTICS:
- Total tickets: {total}
- Open: {open_t} | Resolved/Closed: {resolved}
- SLA Breached: {breached} | At Risk: {at_risk}
- P1 tickets: {p1_count} | P2 tickets: {p2_count}
- SLA breach rate: {round(breached/total*100,1) if total else 0}%

TICKETS BY CATEGORY:
{json.dumps(cat_counts, indent=2)}

OPEN TICKETS BY AGENT:
{json.dumps(agent_counts, indent=2)}

SLA BREACH BY CATEGORY:
{json.dumps(cat_breach, indent=2)}

Provide your analysis in this exact structure:

## 📊 Summary
[2-3 sentences summarising overall IT support health]

## 🚨 Key Issues
[Bullet points — most critical problems requiring immediate attention]

## 📈 Trends & Patterns
[Bullet points — notable trends, spikes, recurring patterns]

## 👥 Team Performance
[Bullet points — agent workload observations, overloaded agents, recommendations]

## 💡 Recommendations
[Bullet points — specific, actionable recommendations the IT manager should act on]

## ⚡ Immediate Actions
[Bullet points — things that should be done TODAY]

Be specific with numbers. Use plain English. Be direct and actionable."""

        client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role":"user","content": prompt}]
        )

        insight_text = response.content[0].text

        # Save to insights log
        try:
            supabase.table("ai_insights").insert({
                "generated_by":   profile.get("id"),
                "insight_text":   insight_text,
                "ticket_count":   total,
                "date_range_from": since,
                "date_range_to":   datetime.now(timezone.utc).isoformat(),
                "filters_used":   json.dumps({"days": days, "focus": focus})
            }).execute()
        except:
            pass

        return {"success": True, "text": insight_text, "total": total, "days": days, "focus": focus}

    except Exception as e:
        return {"success": False, "error": str(e)}


def _render_insight(result):
    if not result.get("success"):
        st.error(f"Could not generate insights: {result.get('error','Unknown error')}")
        return

    st.markdown(f"**Analysis period:** Last {result.get('days',7)} days &nbsp;|&nbsp; "
                f"**Focus:** {result.get('focus','All')} &nbsp;|&nbsp; "
                f"**Tickets analysed:** {result.get('total',0)}")
    st.markdown("---")
    st.markdown(result.get("text",""))

    col1, col2 = st.columns([1,4])
    with col1:
        if st.button("🔄 Regenerate", key="regen_btn"):
            st.session_state.pop("ai_insight_result", None)
            st.rerun()
    with col2:
        if st.button("🗑️ Clear", key="clear_insight"):
            st.session_state.pop("ai_insight_result", None)
            st.rerun()


def _render_past_insights(supabase):
    st.subheader("📜 Previous Insights")
    try:
        past = supabase.table("ai_insights").select(
            "insight_text, ticket_count, created_at, filters_used"
        ).order("created_at", desc=True).limit(5).execute().data or []

        if not past:
            st.info("No previous insights yet. Click **Generate Insights** above to get started.")
            return

        for i, ins in enumerate(past):
            ts       = ins.get("created_at","")[:16].replace("T"," ")
            count    = ins.get("ticket_count",0)
            filters  = ins.get("filters_used")
            focus    = ""
            days_val = ""
            if filters:
                try:
                    f = json.loads(filters) if isinstance(filters, str) else filters
                    focus    = f.get("focus","")
                    days_val = f.get("days","")
                except:
                    pass

            with st.expander(f"Insight — {ts} | {count} tickets | {days_val} days | {focus}##{i}"):
                st.markdown(ins.get("insight_text",""))
    except Exception as e:
        st.error(f"Could not load past insights: {e}")
