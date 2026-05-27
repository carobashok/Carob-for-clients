"""
Portal Orders — Admin module for Carob Inventory App
Approve / Reject / Request Change on distributor orders
Auto-converts approved orders to Sales Orders
"""
import streamlit as st
import pandas as pd
from datetime import date
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import portal_db from carob_portal folder
portal_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "carob_portal")
sys.path.insert(0, portal_path)
import portal_db as pdb
from proforma import generate_proforma_html

def show():
    st.markdown('<div class="carob-title">Portal Orders</div>', unsafe_allow_html=True)
    st.markdown('<div class="carob-subtitle">Distributor orders · Approve · Convert to SO · Proforma</div>',
                unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs([
        "⏳ Pending Approval",
        "✅ Approved Orders",
        "📋 All Orders",
        "⚙️ Admin Settings"
    ])

    # ── Tab 1: Pending ────────────────────────────────────────────────────────
    with tab1:
        pending_df = pdb.get_portal_orders_summary(status="Pending")
        if pending_df.empty:
            st.success("✅ No orders pending approval.")
        else:
            st.markdown(f"**{len(pending_df)} orders** pending your approval")
            st.markdown("<hr>", unsafe_allow_html=True)

            for _, order in pending_df.iterrows():
                with st.container():
                    col_h1, col_h2, col_h3 = st.columns([3, 1.5, 1])
                    with col_h1:
                        st.markdown(f"### {order['order_number']}")
                        st.caption(f"{order['company_name']} · {order['city']} · GSTIN: {order.get('gstin','—')}")
                    with col_h2:
                        st.markdown(f"**₹{order['total_value']:,.0f}**")
                        st.caption(f"Ordered: {order['order_date']}")
                    with col_h3:
                        st.markdown('<span class="badge-warn">⏳ Pending</span>',
                                    unsafe_allow_html=True)

                    # Order lines
                    lines = pdb.get_order_lines(order["id"])
                    if not lines.empty:
                        dcols = ["product_code", "product_name", "unit", "qty",
                                 "discount_pct", "unit_price", "line_total"]
                        available = [c for c in dcols if c in lines.columns]
                        st.dataframe(lines[available].rename(columns={
                            "product_code": "Code", "product_name": "Product",
                            "unit": "Unit", "qty": "Qty", "discount_pct": "Disc %",
                            "unit_price": "Unit Price (₹)", "line_total": "Total (₹)"
                        }), use_container_width=True, hide_index=True)

                    if order.get("delivery_address"):
                        st.caption(f"📍 Deliver to: {order['delivery_address']}")
                    if order.get("notes"):
                        st.caption(f"📝 Note: {order['notes']}")

                    # Action buttons
                    col_a1, col_a2, col_a3, col_a4 = st.columns([1, 1, 2, 2])
                    with col_a1:
                        if st.button("✅ Approve", key=f"approve_{order['id']}",
                                     use_container_width=True):
                            so_num = pdb.approve_order(
                                order["id"], order["order_number"],
                                order.get("portal_user_id") or
                                    pdb.get_supabase().table("portal_orders")
                                    .select("portal_user_id").eq("id", order["id"])
                                    .execute().data[0]["portal_user_id"],
                                lines
                            )
                            st.success(f"✅ Order **{order['order_number']}** approved! "
                                       f"SO **{so_num}** created automatically.")
                            st.rerun()
                    with col_a2:
                        if st.button("✗ Reject", key=f"reject_{order['id']}",
                                     use_container_width=True):
                            st.session_state[f"show_reject_{order['id']}"] = True

                    with col_a3:
                        if st.button("📝 Request Change", key=f"change_{order['id']}",
                                     use_container_width=True):
                            st.session_state[f"show_change_{order['id']}"] = True

                    # Rejection form
                    if st.session_state.get(f"show_reject_{order['id']}"):
                        rej_reason = st.text_input("Rejection reason *",
                                                    key=f"rej_reason_{order['id']}")
                        if st.button("Confirm Reject", key=f"confirm_rej_{order['id']}"):
                            if rej_reason:
                                pdb.reject_order(order["id"], rej_reason)
                                st.error(f"Order {order['order_number']} rejected.")
                                st.session_state[f"show_reject_{order['id']}"] = False
                                st.rerun()

                    # Change request form
                    if st.session_state.get(f"show_change_{order['id']}"):
                        change_note = st.text_input("Note to distributor *",
                                                     key=f"change_note_{order['id']}")
                        if st.button("Send Change Request", key=f"confirm_change_{order['id']}"):
                            if change_note:
                                pdb.request_change(order["id"], change_note)
                                st.warning(f"Change requested for {order['order_number']}.")
                                st.session_state[f"show_change_{order['id']}"] = False
                                st.rerun()

                    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Tab 2: Approved ───────────────────────────────────────────────────────
    with tab2:
        approved_df = pdb.get_portal_orders_summary(status="Approved")
        if approved_df.empty:
            st.info("No approved orders yet.")
        else:
            total_approved_val = approved_df["total_value"].sum()
            st.caption(f"**{len(approved_df)}** approved orders · Total value: **₹{total_approved_val:,.0f}**")

            for _, order in approved_df.iterrows():
                with st.expander(
                    f"**{order['order_number']}** · {order['company_name']} · "
                    f"₹{order['total_value']:,.0f} · SO: {order.get('so_number','—')}"
                ):
                    col_i1, col_i2 = st.columns([2, 1])
                    with col_i1:
                        lines = pdb.get_order_lines(order["id"])
                        if not lines.empty:
                            dcols = ["product_code", "product_name", "unit", "qty",
                                     "unit_price", "line_total"]
                            available = [c for c in dcols if c in lines.columns]
                            st.dataframe(lines[available].rename(columns={
                                "product_code": "Code", "product_name": "Product",
                                "unit": "Unit", "qty": "Qty",
                                "unit_price": "Unit Price (₹)", "line_total": "Total (₹)"
                            }), use_container_width=True, hide_index=True)
                    with col_i2:
                        st.markdown(f"**Customer:** {order['company_name']}")
                        st.markdown(f"**SO Number:** {order.get('so_number','—')}")
                        st.markdown(f"**Approved:** {str(order.get('approved_at',''))[:10]}")
                        lines2 = pdb.get_order_lines(order["id"])
                        proforma_html = generate_proforma_html(order.to_dict(), lines2)
                        st.download_button(
                            "⬇️ Proforma Invoice",
                            data=proforma_html,
                            file_name=f"Proforma_{order['order_number']}.html",
                            mime="text/html",
                            key=f"adl_{order['id']}"
                        )

    # ── Tab 3: All Orders ─────────────────────────────────────────────────────
    with tab3:
        col_f1, col_f2 = st.columns([2, 1.5])
        with col_f1:
            search = st.text_input("🔍 Search order # or company", "")
        with col_f2:
            status_filter = st.selectbox("Status",
                ["All", "Pending", "Approved", "Rejected", "Change Requested"])

        all_df = pdb.get_portal_orders_summary()
        if all_df.empty:
            st.info("No portal orders found.")
        else:
            df = all_df.copy()
            if search:
                df = df[df["order_number"].str.contains(search, case=False) |
                        df["company_name"].str.contains(search, case=False)]
            if status_filter != "All":
                df = df[df["status"] == status_filter]

            cols = ["order_number", "company_name", "city", "order_date",
                    "status", "total_value", "so_number", "line_count"]
            available = [c for c in cols if c in df.columns]
            st.dataframe(df[available].rename(columns={
                "order_number": "Order #", "company_name": "Distributor",
                "city": "City", "order_date": "Date", "status": "Status",
                "total_value": "Value (₹)", "so_number": "SO #",
                "line_count": "Lines"
            }), use_container_width=True, hide_index=True,
                column_config={"Value (₹)": st.column_config.NumberColumn(format="₹%.2f")})

    # ── Tab 4: Admin Settings ─────────────────────────────────────────────────
    with tab4:
        col_s1, col_s2 = st.columns([1.5, 1])

        with col_s1:
            st.subheader("Product Catalogue")
            products_df = pdb.get_all_products()
            if not products_df.empty:
                cols_p = ["product_code", "name", "category", "unit",
                          "base_price", "moq", "current_stock", "is_active", "is_featured"]
                available_p = [c for c in cols_p if c in products_df.columns]
                st.dataframe(products_df[available_p].rename(columns={
                    "product_code": "Code", "name": "Product", "category": "Category",
                    "unit": "Unit", "base_price": "Base Price (₹)",
                    "moq": "MOQ", "current_stock": "Stock",
                    "is_active": "Active", "is_featured": "Featured"
                }), use_container_width=True, hide_index=True)

            st.markdown("<hr>", unsafe_allow_html=True)
            st.subheader("Add Product to Portal")
            with st.form("add_portal_product"):
                ap1, ap2 = st.columns(2)
                with ap1:
                    p_code = st.text_input("Product Code *", placeholder="INK-001")
                    p_name = st.text_input("Product Name *")
                    p_cat = st.selectbox("Category", [
                        "Offset Printing", "UV-Cure Printing",
                        "Industrial Coding", "Flexographic",
                        "Gravure Printing", "Metal Marking", "Other"
                    ])
                    p_desc = st.text_input("Description")
                with ap2:
                    p_unit = st.selectbox("Unit", ["Ltr", "Kg", "Nos"])
                    p_price = st.number_input("Base Price *", min_value=0.0)
                    p_moq = st.number_input("MOQ *", min_value=0.1, value=1.0)
                    p_stock = st.number_input("Current Stock", min_value=0.0)
                p_active = st.checkbox("Active (visible in portal)", value=True)
                p_featured = st.checkbox("Featured (show on distributor dashboard)")
                p_submit = st.form_submit_button("Add Product")
            if p_submit:
                if not p_code or not p_name or p_price <= 0:
                    st.error("Code, name and price are required.")
                else:
                    pdb.add_product({
                        "product_code": p_code.upper(),
                        "name": p_name, "category": p_cat,
                        "description": p_desc, "unit": p_unit,
                        "base_price": p_price, "moq": p_moq,
                        "current_stock": p_stock,
                        "is_active": p_active, "is_featured": p_featured
                    })
                    st.success(f"✅ Product '{p_name}' added to portal.")
                    st.rerun()

        with col_s2:
            st.subheader("Distributor Accounts")
            users_df = pdb.get_all_portal_users()
            if not users_df.empty:
                cols_u = ["company_name", "username", "city", "phone", "is_active"]
                available_u = [c for c in cols_u if c in users_df.columns]
                st.dataframe(users_df[available_u].rename(columns={
                    "company_name": "Company", "username": "Login",
                    "city": "City", "phone": "Phone", "is_active": "Active"
                }), use_container_width=True, hide_index=True)

            st.markdown("<hr>", unsafe_allow_html=True)
            st.subheader("Add Distributor")
            with st.form("add_distributor"):
                d_company = st.text_input("Company Name *")
                d_username = st.text_input("Username *", placeholder="rajan_ent")
                d_password = st.text_input("Password *", type="password")
                d_contact = st.text_input("Contact Person")
                d_phone = st.text_input("Phone")
                d_email = st.text_input("Email")
                d_city = st.text_input("City")
                d_gstin = st.text_input("GSTIN")
                d_address = st.text_area("Address", height=60)
                d_submit = st.form_submit_button("Add Distributor")
            if d_submit:
                if not d_company or not d_username or not d_password:
                    st.error("Company, username and password are required.")
                else:
                    pdb.add_portal_user({
                        "company_name": d_company,
                        "username": d_username,
                        "password_hash": d_password,
                        "contact_person": d_contact,
                        "phone": d_phone, "email": d_email,
                        "city": d_city, "gstin": d_gstin,
                        "address": d_address, "is_active": True
                    })
                    st.success(f"✅ Distributor '{d_company}' added.")
                    st.rerun()
