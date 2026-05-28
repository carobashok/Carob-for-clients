"""
Inventory — Carob Inventory Manager
Item master, stock levels, add/edit items
"""
import streamlit as st
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db

CATEGORIES = ["Raw Material", "WIP", "Finished Good", "Consumable", "Spare Part"]
UNITS = ["Nos", "Kg", "MT", "Ltr", "Box", "Pcs", "Set", "Roll", "Bag", "Bundle"]

def show():
    st.markdown('<div class="carob-title">Inventory</div>', unsafe_allow_html=True)
    st.markdown('<div class="carob-subtitle">Item master · Stock levels · Reorder management</div>',
                unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["📋 Item List", "➕ Add Item", "🏪 Suppliers"])

    # ── Tab 1: Item List ─────────────────────────────────────────────────────
    with tab1:
        alerts_df = db.get_stock_alerts()
        if alerts_df.empty:
            st.info("No items found. Add items using the 'Add Item' tab.")
            return

        # Filters
        col_f1, col_f2, col_f3 = st.columns([2, 1.5, 1.5])
        with col_f1:
            search = st.text_input("🔍 Search item name or code", "")
        with col_f2:
            cat_filter = st.selectbox("Category", ["All"] + CATEGORIES)
        with col_f3:
            status_filter = st.selectbox("Status", ["All", "Out of Stock", "Reorder Now", "Low Stock", "OK"])

        df = alerts_df.copy()
        if search:
            df = df[df["name"].str.contains(search, case=False) |
                    df["item_code"].str.contains(search, case=False)]
        if cat_filter != "All":
            df = df[df["category"] == cat_filter]
        if status_filter != "All":
            df = df[df["stock_status"] == status_filter]

        # Stock value summary
        total_val = df["stock_value"].sum()
        st.caption(f"Showing **{len(df)}** items · Total stock value: **₹{total_val:,.2f}**")

        display_cols = ["item_code", "name", "category", "unit", "current_stock",
                        "reorder_level", "reorder_qty", "unit_cost", "stock_value",
                        "stock_status", "supplier_name"]

        st.dataframe(
            df[display_cols].rename(columns={
                "item_code": "Code", "name": "Item Name", "category": "Category",
                "unit": "Unit", "current_stock": "In Stock",
                "reorder_level": "Reorder At", "reorder_qty": "Reorder Qty",
                "unit_cost": "Unit Cost (₹)", "stock_value": "Stock Value (₹)",
                "stock_status": "Status", "supplier_name": "Preferred Supplier"
            }),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Stock Value (₹)": st.column_config.NumberColumn(format="₹%.2f"),
                "Unit Cost (₹)": st.column_config.NumberColumn(format="₹%.2f"),
            }
        )

        # Manual stock adjustment
        st.markdown("<hr>", unsafe_allow_html=True)
        st.subheader("Manual Stock Adjustment / Wastage")
        items_list = db.get_item_options()
        if items_list:
            item_map = {f"{i['item_code']} — {i['name']}": i for i in items_list}
            sel = st.selectbox("Select Item", list(item_map.keys()))
            item_data = item_map[sel]
            col_a, col_b, col_c = st.columns([1.5, 1, 1])
            with col_a:
                mv_type = st.selectbox("Movement Type",
                                       ["GRN", "Issue", "Return", "Adjustment", "Wastage"])
            with col_b:
                mv_qty = st.number_input("Quantity", min_value=0.01, value=1.0, step=0.5)
            with col_c:
                mv_ref = st.text_input("Reference", "",
                                        placeholder="PO/PRD/SO number")
            mv_remarks = st.text_input("Remarks", "",
                                        placeholder="Reason for wastage / adjustment")
            if mv_type == "Wastage":
                st.info("⚠️ Wastage will deduct from stock and appear in Stock Ledger. "
                        "For production-linked wastage, use the Production module.")
            if st.button("Post Movement"):
                db.log_movement(item_data["id"], mv_type, mv_qty, mv_ref, mv_remarks)
                st.success(f"✅ {mv_type} of {mv_qty} {item_data['unit']} posted for {item_data['name']}")
                st.rerun()

    # ── Tab 2: Add Item ──────────────────────────────────────────────────────
    with tab2:
        st.subheader("Add New Item")
        suppliers = db.get_supplier_options()
        supplier_map = {"— None —": None}
        for s in suppliers:
            supplier_map[s["name"]] = s["id"]

        with st.form("add_item_form"):
            col1, col2 = st.columns(2)
            with col1:
                item_code = st.text_input("Item Code *", placeholder="RM-001")
                item_name = st.text_input("Item Name *", placeholder="MS Plate 6mm")
                category = st.selectbox("Category", CATEGORIES)
                unit = st.selectbox("Unit", UNITS)
            with col2:
                current_stock = st.number_input("Opening Stock", min_value=0.0, value=0.0)
                reorder_level = st.number_input("Reorder Level", min_value=0.0, value=10.0)
                reorder_qty = st.number_input("Reorder Qty", min_value=0.0, value=50.0)
                unit_cost = st.number_input("Unit Cost (₹)", min_value=0.0, value=0.0)
            supplier_name = st.selectbox("Primary Supplier", list(supplier_map.keys()))
            submitted = st.form_submit_button("Add Item")

        if submitted:
            if not item_code or not item_name:
                st.error("Item Code and Name are required.")
            else:
                db.add_item({
                    "item_code": item_code.upper(),
                    "name": item_name,
                    "category": category,
                    "unit": unit,
                    "current_stock": current_stock,
                    "reorder_level": reorder_level,
                    "reorder_qty": reorder_qty,
                    "unit_cost": unit_cost,
                    "supplier_id": supplier_map[supplier_name]
                })
                st.success(f"✅ Item '{item_name}' added successfully.")
                st.rerun()

    # ── Tab 3: Suppliers ─────────────────────────────────────────────────────
    with tab3:
        col_s1, col_s2 = st.columns([1.6, 1])
        with col_s1:
            st.subheader("Supplier List")
            sup_df = db.get_all_suppliers()
            if not sup_df.empty:
                st.dataframe(sup_df.drop(columns=["created_at"], errors="ignore"),
                             use_container_width=True, hide_index=True)
            else:
                st.info("No suppliers added yet.")

        with col_s2:
            st.subheader("Add Supplier")
            with st.form("add_supplier_form"):
                s_name = st.text_input("Supplier Name *")
                s_contact = st.text_input("Contact Person")
                s_phone = st.text_input("Phone")
                s_email = st.text_input("Email")
                s_city = st.text_input("City")
                s_lead = st.number_input("Lead Time (days)", min_value=1, value=7)
                s_submit = st.form_submit_button("Add Supplier")
            if s_submit:
                if not s_name:
                    st.error("Supplier name is required.")
                else:
                    db.add_supplier({
                        "name": s_name, "contact_person": s_contact,
                        "phone": s_phone, "email": s_email,
                        "city": s_city, "lead_time_days": s_lead
                    })
                    st.success(f"✅ Supplier '{s_name}' added.")
                    st.rerun()
