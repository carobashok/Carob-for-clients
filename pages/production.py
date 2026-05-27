"""
Production — Carob Inventory Manager
Production orders, BOM consumption, wastage tracking
"""
import streamlit as st
import pandas as pd
from datetime import date, timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db

def show():
    st.markdown('<div class="carob-title">Production</div>', unsafe_allow_html=True)
    st.markdown('<div class="carob-subtitle">Production orders · Material consumption · Wastage tracking</div>',
                unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["📋 Orders", "➕ New Production Order", "✅ Record Completion"])

    # ── Tab 1: Order List ────────────────────────────────────────────────────
    with tab1:
        prd_df = db.get_production_orders()
        if prd_df.empty:
            st.info("No production orders yet. Create one using the 'New Production Order' tab.")
            return

        status_filter = st.selectbox("Filter by Status",
                                     ["All", "Planned", "In Progress", "Completed", "Cancelled"])
        df = prd_df.copy()
        if status_filter != "All":
            df = df[df["status"] == status_filter]

        cols = ["order_number", "product_code", "product_name", "qty_planned",
                "qty_produced", "status", "start_date", "end_date"]
        available_cols = [c for c in cols if c in df.columns]
        st.dataframe(
            df[available_cols].rename(columns={
                "order_number": "Order #", "product_code": "Code",
                "product_name": "Product", "qty_planned": "Qty Planned",
                "qty_produced": "Qty Produced", "status": "Status",
                "start_date": "Start Date", "end_date": "End Date"
            }),
            use_container_width=True,
            hide_index=True
        )

        # View consumption
        st.markdown("<hr>", unsafe_allow_html=True)
        st.subheader("View Material Consumption")
        order_options = {row["order_number"]: row["id"] for _, row in prd_df.iterrows()}
        sel_order = st.selectbox("Select Production Order", list(order_options.keys()))
        if sel_order:
            cons_df = db.get_consumption(order_options[sel_order])
            if not cons_df.empty:
                dcols = ["item_code", "item_name", "unit", "qty_planned", "qty_actual", "wastage"]
                available = [c for c in dcols if c in cons_df.columns]
                st.dataframe(cons_df[available].rename(columns={
                    "item_code": "Code", "item_name": "Material", "unit": "Unit",
                    "qty_planned": "Planned", "qty_actual": "Actual", "wastage": "Wastage"
                }), use_container_width=True, hide_index=True)
                if "qty_actual" in cons_df.columns and "wastage" in cons_df.columns:
                    total_wastage = cons_df["wastage"].sum()
                    if total_wastage > 0:
                        st.warning(f"⚠️ Total wastage: **{total_wastage:.2f} units**")
            else:
                st.info("No consumption lines recorded for this order yet.")

    # ── Tab 2: New Production Order ──────────────────────────────────────────
    with tab2:
        st.subheader("Create Production Order")
        items_list = db.get_item_options()
        if not items_list:
            st.warning("⚠️ Add items in the Inventory module first.")
            return

        finished_goods = [i for i in items_list if True]  # All items can be produced
        fg_map = {f"{i['item_code']} — {i['name']}": i for i in finished_goods}
        rm_map = {f"{i['item_code']} — {i['name']}": i for i in items_list}

        col1, col2, col3 = st.columns(3)
        with col1:
            sel_product = st.selectbox("Product to Manufacture *", list(fg_map.keys()))
        with col2:
            qty_planned = st.number_input("Quantity to Produce *", min_value=1.0, value=100.0)
        with col3:
            start_date = st.date_input("Start Date", value=date.today())
        end_date = st.date_input("Expected End Date", value=date.today() + timedelta(days=3))

        st.markdown("**Bill of Materials (Raw Materials Required)**")
        if "bom_lines" not in st.session_state:
            st.session_state.bom_lines = []

        with st.expander("➕ Add Material", expanded=True):
            bc1, bc2 = st.columns([3, 1.5])
            with bc1:
                sel_rm = st.selectbox("Material", list(rm_map.keys()), key="new_bom_item")
            with bc2:
                bom_qty = st.number_input("Qty Required", min_value=0.01,
                                           value=1.0, key="new_bom_qty")
            if st.button("Add to BOM"):
                rm_data = rm_map[sel_rm]
                st.session_state.bom_lines.append({
                    "item_id": rm_data["id"],
                    "item_label": sel_rm,
                    "qty_planned": bom_qty
                })
                st.rerun()

        if st.session_state.bom_lines:
            bom_df = pd.DataFrame(st.session_state.bom_lines)[["item_label", "qty_planned"]]
            bom_df.columns = ["Material", "Qty Required"]
            st.dataframe(bom_df, use_container_width=True, hide_index=True)

            col_b1, col_b2 = st.columns([1, 4])
            with col_b1:
                if st.button("🗑 Clear BOM"):
                    st.session_state.bom_lines = []
                    st.rerun()
            with col_b2:
                if st.button("✅ Create Production Order"):
                    product_data = fg_map[sel_product]
                    bom_payload = [
                        {"item_id": b["item_id"], "qty_planned": b["qty_planned"]}
                        for b in st.session_state.bom_lines
                    ]
                    order_num = db.create_production_order(
                        product_data["id"], qty_planned, start_date, end_date, bom_payload
                    )
                    st.success(f"✅ Production Order **{order_num}** created!")
                    st.session_state.bom_lines = []
                    st.rerun()

    # ── Tab 3: Record Completion ─────────────────────────────────────────────
    with tab3:
        st.subheader("Record Production Completion")
        prd_df2 = db.get_production_orders()
        open_orders = prd_df2[prd_df2["status"].isin(["Planned", "In Progress"])] \
            if not prd_df2.empty else pd.DataFrame()

        if open_orders.empty:
            st.info("No open production orders to complete.")
            return

        order_opts = {row["order_number"]: row["id"] for _, row in open_orders.iterrows()}
        sel_complete = st.selectbox("Select Production Order", list(order_opts.keys()))
        prd_id = order_opts[sel_complete]

        order_row = open_orders[open_orders["order_number"] == sel_complete].iloc[0]
        qty_planned_val = order_row["qty_planned"]

        qty_produced = st.number_input("Qty Actually Produced",
                                        min_value=0.0, max_value=float(qty_planned_val),
                                        value=float(qty_planned_val))

        cons_df = db.get_consumption(prd_id)
        consumption_data = []

        if not cons_df.empty:
            st.markdown("**Record Actual Consumption & Wastage:**")
            for _, row in cons_df.iterrows():
                cc1, cc2, cc3 = st.columns([3, 1.5, 1.5])
                with cc1:
                    item_label = f"{row.get('item_code', '')} — {row.get('item_name', '')}"
                    st.text(item_label)
                with cc2:
                    actual = st.number_input(
                        f"Actual Qty ({row.get('unit', '')})",
                        min_value=0.0, value=float(row["qty_planned"]),
                        key=f"actual_{row['id']}"
                    )
                with cc3:
                    wastage = st.number_input(
                        "Wastage",
                        min_value=0.0, value=0.0,
                        key=f"wastage_{row['id']}"
                    )
                consumption_data.append({
                    "consumption_id": row["id"],
                    "item_id": row["item_id"],
                    "qty_actual": actual,
                    "wastage": wastage,
                    "order_number": sel_complete
                })
        else:
            st.info("No BOM lines defined — stock will not be auto-deducted.")

        if st.button("🏁 Complete Production Order"):
            db.complete_production(prd_id, qty_produced, consumption_data)
            st.success(f"✅ Production Order **{sel_complete}** completed. "
                       f"{qty_produced} units added to finished goods stock.")
            st.rerun()
