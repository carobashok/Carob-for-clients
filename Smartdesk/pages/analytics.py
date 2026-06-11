import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils.supabase_client import get_supabase
from auth import require_role


def analytics_page():
    require_role("agent","team_lead","admin")
    supabase = get_supabase()

    st.title("📊 Analytics Dashboard")
    st.markdown("Live metrics from your IT Help Desk data.")
    st.markdown("---")

    # ── Fetch all tickets ──────────────────────────────────────────────────────
    try:
        tickets = supabase.table("tickets").select(
            "id, type, status, priority, sla_status, created_at, resolved_at, "
            "categories(name), "
            "assigned_agent:profiles!tickets_assigned_to_fkey(full_name), "
            "reported_by_profile:profiles!tickets_reported_by_fkey(full_name), "
            "agent_teams(name)"
        ).execute().data or []
    except Exception as e:
        st.error(f"Could not load data: {e}")
        return

    if not tickets:
        st.info("No ticket data available yet.")
        return

    df = pd.DataFrame(tickets)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    df["category"]   = df["categories"].apply(lambda x: (x or {}).get("name","Others"))
    df["agent"]      = df["assigned_agent"].apply(lambda x: (x or {}).get("full_name","Unassigned"))
    df["team"]       = df["agent_teams"].apply(lambda x: (x or {}).get("full_name","—"))
    df["date"]       = df["created_at"].dt.date

    # Resolution time
    df["resolved_at"] = pd.to_datetime(df["resolved_at"], utc=True, errors="coerce")
    df["resolution_hours"] = (df["resolved_at"] - df["created_at"]).dt.total_seconds() / 3600

    # ── Date range filter ──────────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        date_from = st.date_input("From", value=df["date"].min(), key="an_from")
    with col2:
        date_to   = st.date_input("To",   value=df["date"].max(), key="an_to")

    mask = (df["date"] >= date_from) & (df["date"] <= date_to)
    df   = df[mask]

    if df.empty:
        st.warning("No data in selected date range.")
        return

    # ── KPI row ────────────────────────────────────────────────────────────────
    total     = len(df)
    open_t    = len(df[~df["status"].isin(["resolved","closed"])])
    resolved  = len(df[df["status"].isin(["resolved","closed"])])
    breach_rt = round(len(df[df["sla_status"]=="breached"]) / total * 100, 1) if total else 0
    avg_res   = round(df["resolution_hours"].dropna().mean(), 1) if not df["resolution_hours"].dropna().empty else 0

    c1,c2,c3,c4,c5 = st.columns(5)
    with c1: st.markdown(f"<div class='metric-card'><p>Total</p><h3>{total}</h3></div>", unsafe_allow_html=True)
    with c2: st.markdown(f"<div class='metric-card' style='border-left-color:#e67e22'><p>Open</p><h3>{open_t}</h3></div>", unsafe_allow_html=True)
    with c3: st.markdown(f"<div class='metric-card' style='border-left-color:#27ae60'><p>Resolved</p><h3>{resolved}</h3></div>", unsafe_allow_html=True)
    with c4: st.markdown(f"<div class='metric-card' style='border-left-color:#c0392b'><p>SLA Breach %</p><h3>{breach_rt}%</h3></div>", unsafe_allow_html=True)
    with c5: st.markdown(f"<div class='metric-card' style='border-left-color:#2980b9'><p>Avg Res (hrs)</p><h3>{avg_res}</h3></div>", unsafe_allow_html=True)

    st.markdown("---")

    # ── Row 1: Volume trend + Category breakdown ───────────────────────────────
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📈 Ticket Volume Trend")
        vol = df.groupby("date").size().reset_index(name="count")
        fig = px.line(vol, x="date", y="count", markers=True,
            color_discrete_sequence=["#2E75B6"])
        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font_color="white", margin=dict(t=20,b=20,l=20,r=20),
            xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor="#333"))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("📁 Tickets by Category")
        cat_counts = df["category"].value_counts().reset_index()
        cat_counts.columns = ["category","count"]
        fig = px.pie(cat_counts, names="category", values="count",
            color_discrete_sequence=px.colors.qualitative.Set2, hole=0.4)
        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font_color="white", margin=dict(t=20,b=20,l=20,r=20),
            legend=dict(font=dict(color="white")))
        st.plotly_chart(fig, use_container_width=True)

    # ── Row 2: Priority distribution + Status breakdown ────────────────────────
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🎯 Tickets by Priority")
        pri_counts = df["priority"].value_counts().reindex(["P1","P2","P3","P4"], fill_value=0).reset_index()
        pri_counts.columns = ["priority","count"]
        colours = {"P1":"#c0392b","P2":"#e67e22","P3":"#2980b9","P4":"#27ae60"}
        fig = px.bar(pri_counts, x="priority", y="count",
            color="priority", color_discrete_map=colours)
        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font_color="white", margin=dict(t=20,b=20,l=20,r=20),
            showlegend=False, xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="#333"))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("📊 Tickets by Status")
        status_counts = df["status"].value_counts().reset_index()
        status_counts.columns = ["status","count"]
        status_counts["status"] = status_counts["status"].str.replace("_"," ").str.title()
        fig = px.bar(status_counts, x="count", y="status", orientation="h",
            color_discrete_sequence=["#2E75B6"])
        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font_color="white", margin=dict(t=20,b=20,l=20,r=20),
            xaxis=dict(showgrid=True, gridcolor="#333"),
            yaxis=dict(showgrid=False))
        st.plotly_chart(fig, use_container_width=True)

    # ── Row 3: Agent workload + Avg resolution by category ────────────────────
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🧑‍💻 Agent Workload (Open Tickets)")
        open_df = df[~df["status"].isin(["resolved","closed"])]
        if not open_df.empty:
            agent_counts = open_df["agent"].value_counts().reset_index()
            agent_counts.columns = ["agent","open_tickets"]
            fig = px.bar(agent_counts, x="open_tickets", y="agent", orientation="h",
                color_discrete_sequence=["#8e44ad"])
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font_color="white", margin=dict(t=20,b=20,l=20,r=20),
                xaxis=dict(showgrid=True, gridcolor="#333"),
                yaxis=dict(showgrid=False))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No open tickets currently.")

    with col2:
        st.subheader("⏱️ Avg Resolution Time by Category (hrs)")
        res_df = df[df["resolution_hours"].notna()]
        if not res_df.empty:
            avg_res_cat = res_df.groupby("category")["resolution_hours"].mean().reset_index()
            avg_res_cat.columns = ["category","avg_hours"]
            avg_res_cat["avg_hours"] = avg_res_cat["avg_hours"].round(1)
            fig = px.bar(avg_res_cat, x="avg_hours", y="category", orientation="h",
                color_discrete_sequence=["#16a085"])
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font_color="white", margin=dict(t=20,b=20,l=20,r=20),
                xaxis=dict(showgrid=True, gridcolor="#333"),
                yaxis=dict(showgrid=False))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No resolved tickets yet for resolution time analysis.")

    # ── Row 4: SLA breach rate by category ────────────────────────────────────
    st.subheader("🚨 SLA Breach Rate by Category")
    sla_df = df.groupby("category").apply(
        lambda x: pd.Series({
            "total":   len(x),
            "breached": len(x[x["sla_status"]=="breached"]),
            "breach_pct": round(len(x[x["sla_status"]=="breached"]) / len(x) * 100, 1)
        })
    ).reset_index()

    fig = px.bar(sla_df, x="category", y="breach_pct",
        text="breach_pct", color="breach_pct",
        color_continuous_scale=["#27ae60","#e67e22","#c0392b"],
        labels={"breach_pct": "Breach %", "category": "Category"})
    fig.update_traces(texttemplate="%{text}%", textposition="outside")
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font_color="white", margin=dict(t=40,b=20,l=20,r=20),
        xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor="#333"),
        coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

    # ── Issue vs SR split ──────────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🔧 Issue vs Service Request Split")
        type_counts = df["type"].value_counts().reset_index()
        type_counts.columns = ["type","count"]
        type_counts["type"] = type_counts["type"].str.replace("_"," ").str.title()
        fig = px.pie(type_counts, names="type", values="count",
            color_discrete_sequence=["#2E75B6","#e67e22"], hole=0.5)
        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font_color="white", margin=dict(t=20,b=20,l=20,r=20),
            legend=dict(font=dict(color="white")))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("🤖 AI Classification Confidence")
        if "ai_confidence" in df.columns:
            conf_counts = df["ai_confidence"].fillna("not set").value_counts().reset_index()
            conf_counts.columns = ["confidence","count"]
            conf_colours = {"high":"#27ae60","medium":"#e67e22","low":"#c0392b","not set":"#888"}
            fig = px.pie(conf_counts, names="confidence", values="count",
                color="confidence", color_discrete_map=conf_colours, hole=0.5)
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font_color="white", margin=dict(t=20,b=20,l=20,r=20),
                legend=dict(font=dict(color="white")))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No AI confidence data available.")
