"""
Sales & Dispatch — Carob Inventory Manager
Sales orders, dispatch notes, FG stock deduction
"""
import streamlit as st
import pandas as pd
from datetime import date, timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db

def show():
    st.markdown('<div class="carob-title">Sales & Dispatch</div>', unsafe_allow_html=True)
    st.markdown('<div class="carob-subtitle">Sales orders · Dispatch notes · FG stock deduction</div>',
                unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["📋 Sales Orders", "➕ New Sales Order",
                                       "🚚 Dispatch", "👥 Customers"])

    # ── Tab 1: Sales Order List ──────────────────────────────────────────────
    with tab1:
        col_f1, col_f2 = st.columns([2, 1.5])
        with col_f1:
            search = st.text_input("🔍 Search SO # or Customer", "")
        with col_f2:
            status_filter = st.selectbox("Status", ["All", "Open", "Partial", "Fulfilled", "Cancelled"])

        so_df = db.get_so_summary()
        if so_df.empty:
            st.info("No sales orders yet. Create one using the 'New Sales Order' tab.")
        else:
            df = so_df.copy()
            if search:
                df = df[df["so_number"].str.contains(search, case=False) |
                        df["customer_name"].str.contains(search, case=False)]
            if status_filter != "All":
                df = df[df["status"] == status_filter]

            open_val = df[df["status"].isin(["Open", "Partial"])]["total_value"].sum()
            st.caption(f"**{len(df)}** orders · Open order value: **₹{open_val:,.2f}**")

            cols = ["so_number", "customer_name", "order_date", "expected_date",
                    "status", "total_value", "line_count", "total_dispatched"]
            available = [c for c in cols if c in df.columns]
            st.dataframe(
                df[available].rename(columns={
                    "so_number": "SO #", "customer_name": "Customer",
                    "order_date": "Order Date", "expected_date": "Expected",
                    "status": "Status", "total_value": "Value (₹)",
                    "line_count": "Lines", "total_dispatched": "Qty Dispatched"
                }),
                use_container_width=True, hide_index=True,
                column_config={"Value (₹)": st.column_config.NumberColumn(format="₹%.2f")}
            )

            # SO Line detail
            st.markdown("<hr>", unsafe_allow_html=True)
            st.subheader("View SO Lines")
            so_opts = {row["so_number"]: row["id"] for _, row in so_df.iterrows()}
            sel_so = st.selectbox("Select Sales Order", list(so_opts.keys()), key="view_so")
            if sel_so:
                lines = db.get_so_lines(so_opts[sel_so])
                if not lines.empty:
                    dcols = ["item_code", "item_name", "unit", "qty_ordered",
                             "qty_dispatched", "unit_price", "line_total"]
                    available_l = [c for c in dcols if c in lines.columns]
                    st.dataframe(lines[available_l].rename(columns={
                        "item_code": "Code", "item_name": "Item", "unit": "Unit",
                        "qty_ordered": "Qty Ordered", "qty_dispatched": "Dispatched",
                        "unit_price": "Unit Price (₹)", "line_total": "Line Total (₹)"
                    }), use_container_width=True, hide_index=True)

                    # Pending dispatch summary
                    if "qty_ordered" in lines.columns and "qty_dispatched" in lines.columns:
                        lines["pending"] = lines["qty_ordered"] - lines["qty_dispatched"]
                        pending_total = lines["pending"].sum()
                        if pending_total > 0:
                            st.warning(f"⚠️ Pending dispatch: **{pending_total:.0f} units** across {len(lines[lines['pending']>0])} line(s)")
                        else:
                            st.success("✅ All lines fully dispatched.")

    # ── Tab 2: New Sales Order ────────────────────────────────────────────────
    with tab2:
        st.subheader("Create New Sales Order")
        customers = db.get_customer_options()
        if not customers:
            st.warning("⚠️ Please add customers first in the 'Customers' tab.")
        else:
            customer_map = {f"{c['name']} — {c['city']}": c["id"] for c in customers}
            items_list = db.get_item_options()
            # Only FG and WIP for sales
            fg_items = [i for i in items_list if True]
            item_map = {f"{i['item_code']} — {i['name']}": i for i in fg_items}

            col1, col2, col3 = st.columns(3)
            with col1:
                sel_customer = st.selectbox("Customer *", list(customer_map.keys()))
            with col2:
                so_order_date = st.date_input("Order Date", value=date.today(), key="so_date")
            with col3:
                so_exp_date = st.date_input("Expected Delivery", value=date.today() + timedelta(days=7), key="so_exp")
            so_notes = st.text_input("Notes", "", key="so_notes")

            st.markdown("**Line Items**")
            if "so_lines" not in st.session_state:
                st.session_state.so_lines = []

            with st.expander("➕ Add Line Item", expanded=True):
                lc1, lc2, lc3 = st.columns([3, 1.5, 1.5])
                with lc1:
                    sel_item = st.selectbox("Item", list(item_map.keys()), key="so_line_item")
                with lc2:
                    so_qty = st.number_input("Qty", min_value=1.0, value=1.0, key="so_line_qty")
                with lc3:
                    item_d = item_map[sel_item]
                    so_price = st.number_input("Unit Price (₹)", min_value=0.0,
                                                value=float(item_d["unit_cost"]) * 1.2,
                                                key="so_line_price")
                if st.button("Add Line", key="add_so_line"):
                    st.session_state.so_lines.append({
                        "item_id": item_d["id"],
                        "item_label": sel_item,
                        "qty_ordered": so_qty,
                        "unit_price": so_price,
                        "line_total": so_qty * so_price
                    })
                    st.rerun()

            if st.session_state.so_lines:
                so_lines_df = pd.DataFrame(st.session_state.so_lines)[
                    ["item_label", "qty_ordered", "unit_price", "line_total"]
                ].rename(columns={
                    "item_label": "Item", "qty_ordered": "Qty",
                    "unit_price": "Unit Price (₹)", "line_total": "Total (₹)"
                })
                st.dataframe(so_lines_df, use_container_width=True, hide_index=True)
                total = sum(l["line_total"] for l in st.session_state.so_lines)
                st.markdown(f"**Order Total: ₹{total:,.2f}**")

                col_b1, col_b2 = st.columns([1, 4])
                with col_b1:
                    if st.button("🗑 Clear", key="clear_so"):
                        st.session_state.so_lines = []
                        st.rerun()
                with col_b2:
                    if st.button("✅ Create Sales Order"):
                        lines_payload = [
                            {"item_id": l["item_id"], "qty_ordered": l["qty_ordered"],
                             "unit_price": l["unit_price"]}
                            for l in st.session_state.so_lines
                        ]
                        so_num = db.create_so(
                            customer_map[sel_customer],
                            so_order_date, so_exp_date, so_notes,
                            lines_payload
                        )
                        st.success(f"✅ Sales Order **{so_num}** created!")
                        st.session_state.so_lines = []
                        st.rerun()

    # ── Tab 3: Dispatch ───────────────────────────────────────────────────────
    with tab3:
        st.subheader("Create Dispatch Note")

        # Dispatch history
        dn_df = db.get_dispatch_summary()
        if not dn_df.empty:
            st.markdown("**Recent Dispatches**")
            cols_d = ["dn_number", "so_number", "customer_name", "dispatch_date",
                      "vehicle_no", "line_count", "total_qty"]
            available_d = [c for c in cols_d if c in dn_df.columns]
            st.dataframe(dn_df[available_d].rename(columns={
                "dn_number": "DN #", "so_number": "SO #",
                "customer_name": "Customer", "dispatch_date": "Date",
                "vehicle_no": "Vehicle", "line_count": "Lines",
                "total_qty": "Total Qty"
            }), use_container_width=True, hide_index=True)
            st.markdown("<hr>", unsafe_allow_html=True)

        # New dispatch
        so_df2 = db.get_so_summary()
        open_sos = so_df2[so_df2["status"].isin(["Open", "Partial"])] if not so_df2.empty else pd.DataFrame()

        if open_sos.empty:
            st.info("No open sales orders to dispatch against.")
        else:
            so_opts2 = {f"{row['so_number']} — {row['customer_name']}": row
                        for _, row in open_sos.iterrows()}
            sel_dispatch_so = st.selectbox("Select Sales Order to Dispatch", list(so_opts2.keys()))
            so_row = so_opts2[sel_dispatch_so]
            so_id = so_row["id"]

            col_d1, col_d2, col_d3 = st.columns(3)
            with col_d1:
                dispatch_date = st.date_input("Dispatch Date", value=date.today())
            with col_d2:
                vehicle_no = st.text_input("Vehicle No.", placeholder="TN01AB1234")
            with col_d3:
                driver_name = st.text_input("Driver Name", placeholder="Optional")
            dn_remarks = st.text_input("Remarks", "")

            # Load SO lines
            so_lines = db.get_so_lines(so_id)
            dispatch_data = []

            if not so_lines.empty:
                st.markdown("**Quantities to Dispatch:**")

                for _, row in so_lines.iterrows():
                    pending = row["qty_ordered"] - row["qty_dispatched"]
                    if pending <= 0:
                        continue

                    # Check available FG stock
                    stock_df = db.get_stock_alerts()
                    item_stock = 0
                    if not stock_df.empty:
                        match = stock_df[stock_df["id"] == row["item_id"]]
                        if not match.empty:
                            item_stock = match.iloc[0]["current_stock"]

                    dc1, dc2, dc3, dc4 = st.columns([3, 1.5, 1.5, 1.5])
                    with dc1:
                        st.text(f"{row.get('item_code','')} — {row.get('item_name','')}")
                    with dc2:
                        st.text(f"Pending: {pending:.0f} {row.get('unit','')}")
                    with dc3:
                        st.text(f"In Stock: {item_stock:.0f}")
                    with dc4:
                        max_dispatch = min(pending, item_stock)
                        disp_qty = st.number_input(
                            "Dispatch Qty",
                            min_value=0.0,
                            max_value=float(max_dispatch),
                            value=float(max_dispatch),
                            key=f"disp_{row['id']}"
                        )
                    dispatch_data.append({
                        "so_line_id": row["id"],
                        "item_id": row["item_id"],
                        "qty_dispatched": disp_qty,
                        "so_number": so_row["so_number"]
                    })

                if st.button("🚚 Post Dispatch"):
                    if not vehicle_no:
                        st.error("Please enter a vehicle number.")
                    elif all(d["qty_dispatched"] == 0 for d in dispatch_data):
                        st.error("Please enter at least one dispatch quantity.")
                    else:
                        dn_num = db.create_dispatch(
                            so_id, so_row["customer_id"] if "customer_id" in so_row else None,
                            dispatch_date, vehicle_no, driver_name, dn_remarks,
                            dispatch_data
                        )
                        st.success(f"✅ Dispatch Note **{dn_num}** posted. FG stock updated.")
                        st.rerun()

    # ── Tab 4: Customers ─────────────────────────────────────────────────────
    with tab4:
        col_c1, col_c2 = st.columns([1.6, 1])
        with col_c1:
            st.subheader("Customer List")
            cust_df = db.get_all_customers()
            if not cust_df.empty:
                st.dataframe(cust_df.drop(columns=["created_at"], errors="ignore"),
                             use_container_width=True, hide_index=True)
            else:
                st.info("No customers added yet.")

        with col_c2:
            st.subheader("Add Customer")
            with st.form("add_customer_form"):
                c_name = st.text_input("Customer Name *")
                c_contact = st.text_input("Contact Person")
                c_phone = st.text_input("Phone")
                c_email = st.text_input("Email")
                c_city = st.text_input("City")
                c_gstin = st.text_input("GSTIN")
                c_submit = st.form_submit_button("Add Customer")
            if c_submit:
                if not c_name:
                    st.error("Customer name is required.")
                else:
                    db.add_customer({
                        "name": c_name, "contact_person": c_contact,
                        "phone": c_phone, "email": c_email,
                        "city": c_city, "gstin": c_gstin
                    })
                    st.success(f"✅ Customer '{c_name}' added.")
                    st.rerun()
