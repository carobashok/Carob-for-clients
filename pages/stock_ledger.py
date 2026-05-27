"""
Stock Ledger — Carob Inventory Manager
Full audit trail of all stock movements
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db

def show():
    st.markdown('<div class="carob-title">Stock Ledger</div>', unsafe_allow_html=True)
    st.markdown('<div class="carob-subtitle">Full audit trail · Every movement · Every item</div>',
                unsafe_allow_html=True)

    col_f1, col_f2, col_f3 = st.columns([2.5, 1.5, 1])
    with col_f1:
        items_list = db.get_item_options()
        item_options = {"All Items": None}
        for i in items_list:
            item_options[f"{i['item_code']} — {i['name']}"] = i["id"]
        sel_item_label = st.selectbox("Filter by Item", list(item_options.keys()))
        sel_item_id = item_options[sel_item_label]
    with col_f2:
        mv_type_filter = st.selectbox("Movement Type",
                                       ["All", "GRN", "Issue", "Return", "Adjustment"])
    with col_f3:
        limit = st.selectbox("Show last", [50, 100, 250, 500], index=1)

    movements = db.get_movements(item_id=sel_item_id, limit=limit)

    if movements.empty:
        st.info("No stock movements recorded yet.")
        return

    df = movements.copy()
    if mv_type_filter != "All":
        df = df[df["movement_type"] == mv_type_filter]

    # Summary stats
    total_in = df[df["qty"] > 0]["qty"].sum()
    total_out = abs(df[df["qty"] < 0]["qty"].sum())
    st.caption(f"**{len(df)}** movements · Total IN: **{total_in:,.2f}** · Total OUT: **{total_out:,.2f}**")

    # Display table
    display_cols = ["movement_date", "item_code", "item_name", "unit",
                    "movement_type", "qty", "reference", "remarks"]
    available = [c for c in display_cols if c in df.columns]

    def color_qty(val):
        if val > 0:
            return "color: #166534"
        elif val < 0:
            return "color: #991B1B"
        return ""

    st.dataframe(
        df[available].rename(columns={
            "movement_date": "Date", "item_code": "Code", "item_name": "Item",
            "unit": "Unit", "movement_type": "Type", "qty": "Qty",
            "reference": "Reference", "remarks": "Remarks"
        }),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Qty": st.column_config.NumberColumn(format="%.2f"),
        }
    )

    # Movement trend chart
    if len(df) > 1 and "movement_date" in df.columns:
        st.markdown("<hr>", unsafe_allow_html=True)
        st.subheader("Movement Trend")
        df["movement_date"] = pd.to_datetime(df["movement_date"])
        trend = (df.groupby(["movement_date", "movement_type"])["qty"]
                   .sum()
                   .reset_index())
        fig = px.bar(
            trend, x="movement_date", y="qty", color="movement_type",
            color_discrete_map={
                "GRN": "#166534", "Issue": "#991B1B",
                "Return": "#1E40AF", "Adjustment": "#C9A84C"
            },
            labels={"movement_date": "Date", "qty": "Quantity", "movement_type": "Type"},
            barmode="group"
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=20, b=20),
            height=320,
            legend=dict(orientation="h", yanchor="bottom", y=1.02)
        )
        fig.update_xaxes(gridcolor="#E2E8F0")
        fig.update_yaxes(gridcolor="#E2E8F0")
        st.plotly_chart(fig, use_container_width=True)
