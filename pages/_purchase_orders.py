"""
Purchase Orders — Carob Inventory Manager
Create POs, receive goods, track status
"""
import streamlit as st
import pandas as pd
from datetime import date, timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db

PO_STATUSES = ["All", "Draft", "Ordered", "Partial", "Received", "Cancelled"]

def show():
    st.markdown('<div class="carob-title">Purchase Orders</div>', unsafe_allow_html=True)
    st.markdown('<div class="carob-subtitle">Raise POs · Track delivery · Receive goods into stock</div>',
                unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["📋 PO List", "➕ New PO", "📥 Receive Goods"])

    # ── Tab 1: PO List ───────────────────────────────────────────────────────
    with tab1:
        col_f1, col_f2 = st.columns([2, 1.5])
        with col_f1:
            search = st.text_input("🔍 Search PO # or Supplier", "")
        with col_f2:
            status_filter = st.selectbox("Status", PO_STATUSES)

        po_df = db.get_po_summary()
        if po_df.empty:
            st.info("No purchase orders yet. Create one using the 'New PO' tab.")
            return

        df = po_df.copy()
        if search:
            df = df[df["po_number"].str.contains(search, case=False) |
                    df["supplier_name"].str.contains(search, case=False)]
        if status_filter != "All":
            df = df[df["status"] == status_filter]

        open_val = df[df["status"].isin(["Ordered", "Partial"])]["total_value"].sum()
        st.caption(f"**{len(df)}** orders · Open PO value: **₹{open_val:,.2f}**")

        cols = ["po_number", "supplier_name", "order_date", "expected_date",
                "status", "total_value", "line_count", "total_received"]
        st.dataframe(
            df[cols].rename(columns={
                "po_number": "PO #", "supplier_name": "Supplier",
                "order_date": "Order Date", "expected_date": "Expected",
                "status": "Status", "total_value": "Value (₹)",
                "line_count": "Lines", "total_received": "Qty Received"
            }),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Value (₹)": st.column_config.NumberColumn(format="₹%.2f"),
            }
        )

        # PO Line Details
        st.markdown("<hr>", unsafe_allow_html=True)
        st.subheader("View PO Lines")
        po_options = {row["po_number"]: row["id"] for _, row in po_df.iterrows()}
        sel_po = st.selectbox("Select PO to view lines", list(po_options.keys()))
        if sel_po:
            lines = db.get_po_lines(po_options[sel_po])
            if not lines.empty:
                line_cols = ["item_code", "item_name", "unit", "qty_ordered", "qty_received", "unit_price", "line_total"]
                st.dataframe(lines[line_cols].rename(columns={
                    "item_code": "Code", "item_name": "Item", "unit": "Unit",
                    "qty_ordered": "Qty Ordered", "qty_received": "Qty Received",
                    "unit_price": "Unit Price (₹)", "line_total": "Line Total (₹)"
                }), use_container_width=True, hide_index=True)

    # ── Tab 2: New PO ────────────────────────────────────────────────────────
    with tab2:
        st.subheader("Create New Purchase Order")
        suppliers = db.get_supplier_options()
        if not suppliers:
            st.warning("⚠️ Please add suppliers first in the Inventory > Suppliers tab.")
            return
        supplier_map = {s["name"]: s["id"] for s in suppliers}

        items_list = db.get_item_options()
        if not items_list:
            st.warning("⚠️ Please add items first in the Inventory tab.")
            return
        item_map = {f"{i['item_code']} — {i['name']}": i for i in items_list}

        col_h1, col_h2, col_h3 = st.columns(3)
        with col_h1:
            sel_supplier = st.selectbox("Supplier *", list(supplier_map.keys()))
        with col_h2:
            order_date = st.date_input("Order Date", value=date.today())
        with col_h3:
            expected_date = st.date_input("Expected Delivery", value=date.today() + timedelta(days=7))

        notes = st.text_input("Notes / Remarks", "")

        st.markdown("**Line Items**")
        if "po_lines" not in st.session_state:
            st.session_state.po_lines = []

        # Add line form
        with st.expander("➕ Add Line Item", expanded=True):
            lc1, lc2, lc3 = st.columns([3, 1.5, 1.5])
            with lc1:
                sel_item = st.selectbox("Item", list(item_map.keys()), key="new_line_item")
            with lc2:
                sel_qty = st.number_input("Qty", min_value=0.01, value=1.0, step=1.0, key="new_line_qty")
            with lc3:
                item_d = item_map[sel_item]
                sel_price = st.number_input("Unit Price (₹)", min_value=0.0,
                                             value=float(item_d["unit_cost"]), key="new_line_price")
            if st.button("Add Line"):
                st.session_state.po_lines.append({
                    "item_id": item_d["id"],
                    "item_label": sel_item,
                    "qty_ordered": sel_qty,
                    "unit_price": sel_price,
                    "line_total": sel_qty * sel_price
                })
                st.rerun()

        if st.session_state.po_lines:
            lines_df = pd.DataFrame(st.session_state.po_lines)[
                ["item_label", "qty_ordered", "unit_price", "line_total"]
            ].rename(columns={
                "item_label": "Item", "qty_ordered": "Qty",
                "unit_price": "Unit Price (₹)", "line_total": "Total (₹)"
            })
            st.dataframe(lines_df, use_container_width=True, hide_index=True)
            total = sum(l["line_total"] for l in st.session_state.po_lines)
            st.markdown(f"**Grand Total: ₹{total:,.2f}**")

            col_btn1, col_btn2 = st.columns([1, 4])
            with col_btn1:
                if st.button("🗑 Clear Lines"):
                    st.session_state.po_lines = []
                    st.rerun()
            with col_btn2:
                if st.button("✅ Create Purchase Order"):
                    lines_payload = [
                        {"item_id": l["item_id"], "qty_ordered": l["qty_ordered"],
                         "unit_price": l["unit_price"]}
                        for l in st.session_state.po_lines
                    ]
                    po_num = db.create_po(
                        supplier_map[sel_supplier],
                        order_date, expected_date, notes,
                        lines_payload
                    )
                    st.success(f"✅ Purchase Order **{po_num}** created successfully!")
                    st.session_state.po_lines = []
                    st.rerun()

    # ── Tab 3: Receive Goods ─────────────────────────────────────────────────
    with tab3:
        st.subheader("Receive Goods Against PO")
        po_df2 = db.get_po_summary()
        open_pos = po_df2[po_df2["status"].isin(["Ordered", "Partial"])] if not po_df2.empty else pd.DataFrame()

        if open_pos.empty:
            st.info("No open purchase orders to receive against.")
            return

        po_options2 = {row["po_number"]: row["id"] for _, row in open_pos.iterrows()}
        sel_receive_po = st.selectbox("Select Open PO", list(po_options2.keys()))
        po_id = po_options2[sel_receive_po]

        lines = db.get_po_lines(po_id)
        if lines.empty:
            st.warning("No lines found for this PO.")
            return

        st.markdown("**Enter quantities received:**")
        received_data = []
        for _, row in lines.iterrows():
            pending = row["qty_ordered"] - row["qty_received"]
            rc1, rc2, rc3, rc4 = st.columns([3, 1.5, 1.5, 1.5])
            with rc1:
                st.text(f"{row['item_code']} — {row['item_name']}")
            with rc2:
                st.text(f"Ordered: {row['qty_ordered']} {row['unit']}")
            with rc3:
                st.text(f"Pending: {pending} {row['unit']}")
            with rc4:
                recv_qty = st.number_input(
                    "Receive", min_value=0.0, max_value=float(pending),
                    value=float(pending), key=f"recv_{row['id']}"
                )
            received_data.append({
                "line_id": row["id"],
                "item_id": row["item_id"],
                "qty_ordered": row["qty_ordered"],
                "qty_received": recv_qty,
                "po_number": sel_receive_po
            })

        if st.button("📥 Post Receipt"):
            db.receive_po(po_id, received_data)
            st.success(f"✅ Goods received and stock updated for {sel_receive_po}!")
            st.rerun()
