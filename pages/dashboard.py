"""
Dashboard — Carob Inventory Manager
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db

def show():
    st.markdown('<div class="carob-title">Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="carob-subtitle">Inventory health at a glance</div>', unsafe_allow_html=True)

    kpis = db.get_dashboard_kpis()

    # ── KPI Row ──────────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total Items", kpis["total_items"])
    c2.metric("Stock Value (₹)", f"{kpis['total_stock_value']:,.0f}")
    c3.metric("Low Stock Alerts", kpis["low_stock_alerts"],
              delta=f"{kpis['low_stock_alerts']} items",
              delta_color="inverse")
    c4.metric("Out of Stock", kpis["out_of_stock"],
              delta=f"{kpis['out_of_stock']} items",
              delta_color="inverse")
    c5.metric("Open POs", f"{kpis['open_po_count']}")
    c6.metric("Open PO Value (₹)", f"{kpis['open_po_value']:,.0f}")

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Charts Row ───────────────────────────────────────────────────────────
    col_left, col_right = st.columns([1.2, 1])

    with col_left:
        st.subheader("Stock Alerts")
        alerts_df = db.get_stock_alerts()
        if not alerts_df.empty:
            status_map = {
                "Out of Stock": "🔴",
                "Reorder Now": "🟠",
                "Low Stock": "🟡",
                "OK": "🟢"
            }
            alerts_df["Status"] = alerts_df["stock_status"].map(
                lambda x: f"{status_map.get(x, '')} {x}"
            )
            alert_items = alerts_df[alerts_df["stock_status"] != "OK"].copy()
            if not alert_items.empty:
                display_cols = ["item_code", "name", "category", "current_stock",
                                "reorder_level", "unit", "Status"]
                st.dataframe(
                    alert_items[display_cols].rename(columns={
                        "item_code": "Code", "name": "Item", "category": "Category",
                        "current_stock": "In Stock", "reorder_level": "Reorder At",
                        "unit": "Unit"
                    }),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.success("✅ All items are well stocked.")
        else:
            st.info("No inventory data yet. Add items in the Inventory module.")

    with col_right:
        st.subheader("Stock by Category")
        if not alerts_df.empty:
            cat_df = (alerts_df.groupby("category")["stock_value"]
                               .sum()
                               .reset_index()
                               .rename(columns={"stock_value": "Value (₹)", "category": "Category"}))
            if not cat_df.empty:
                fig = px.pie(
                    cat_df, values="Value (₹)", names="Category",
                    color_discrete_sequence=["#0D1B2A", "#1E3A5F", "#C9A84C", "#E8C97A"],
                    hole=0.45
                )
                fig.update_traces(textposition="outside", textinfo="percent+label")
                fig.update_layout(
                    showlegend=False,
                    margin=dict(t=10, b=10, l=10, r=10),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    height=300
                )
                st.plotly_chart(fig, use_container_width=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Recent POs ───────────────────────────────────────────────────────────
    st.subheader("Recent Purchase Orders")
    po_df = db.get_po_summary()
    if not po_df.empty:
        recent = po_df.head(5)
        status_colors = {
            "Ordered": "badge-info",
            "Partial": "badge-warn",
            "Received": "badge-ok",
            "Cancelled": "badge-danger",
            "Draft": "badge-warn"
        }
        cols = ["po_number", "supplier_name", "order_date", "expected_date",
                "status", "total_value", "line_count"]
        st.dataframe(
            recent[cols].rename(columns={
                "po_number": "PO #", "supplier_name": "Supplier",
                "order_date": "Order Date", "expected_date": "Expected",
                "status": "Status", "total_value": "Value (₹)",
                "line_count": "Lines"
            }),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No purchase orders yet.")
