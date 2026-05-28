"""
Reports — Carob Inventory Manager
Stock Valuation · Dispatch Register · Pending Orders · Production Summary
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta
import io
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db

def to_excel(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Report")
    return output.getvalue()

def show():
    st.markdown('<div class="carob-title">Reports</div>', unsafe_allow_html=True)
    st.markdown('<div class="carob-subtitle">Stock Valuation · Dispatch Register · Pending Orders · Production Summary</div>',
                unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Stock Valuation",
        "🚚 Dispatch Register",
        "⏳ Pending Orders",
        "🏭 Production Summary"
    ])

    # ── Tab 1: Stock Valuation ────────────────────────────────────────────────
    with tab1:
        st.subheader("Stock Valuation Report")
        st.caption(f"As on {date.today().strftime('%d %b %Y')}")

        df = db.get_stock_valuation()
        if df.empty:
            st.info("No inventory data found.")
        else:
            # Category filter
            categories = ["All"] + sorted(df["category"].dropna().unique().tolist())
            col_f1, col_f2 = st.columns([2, 1])
            with col_f1:
                cat_filter = st.selectbox("Filter by Category", categories, key="sv_cat")
            with col_f2:
                show_zero = st.checkbox("Include zero stock items", value=True)

            filtered = df.copy()
            if cat_filter != "All":
                filtered = filtered[filtered["category"] == cat_filter]
            if not show_zero:
                filtered = filtered[filtered["current_stock"] > 0]

            # Summary KPIs
            total_val = filtered["stock_value"].sum()
            low_count = len(filtered[filtered["stock_status"].isin(["Reorder Now", "Out of Stock"])])
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Total Items", len(filtered))
            k2.metric("Total Stock Value (₹)", f"{total_val:,.2f}")
            k3.metric("Items Needing Reorder", low_count)
            k4.metric("Out of Stock", len(filtered[filtered["stock_status"] == "Out of Stock"]))

            st.markdown("<hr>", unsafe_allow_html=True)

            # Category-wise summary
            st.markdown("**Category-wise Summary**")
            cat_summary = (filtered.groupby("category")
                                   .agg(items=("id", "count"),
                                        total_stock_value=("stock_value", "sum"))
                                   .reset_index()
                                   .rename(columns={
                                       "category": "Category",
                                       "items": "Items",
                                       "total_stock_value": "Stock Value (₹)"
                                   }))
            cat_summary["Stock Value (₹)"] = cat_summary["Stock Value (₹)"].map("₹{:,.2f}".format)

            col_t, col_c = st.columns([1.2, 1])
            with col_t:
                st.dataframe(cat_summary, use_container_width=True, hide_index=True)
            with col_c:
                fig = px.pie(
                    filtered.groupby("category")["stock_value"].sum().reset_index(),
                    values="stock_value", names="category",
                    color_discrete_sequence=["#0D1B2A", "#1E3A5F", "#C9A84C", "#E8C97A", "#94A3B8"],
                    hole=0.4
                )
                fig.update_layout(
                    showlegend=True, height=260,
                    margin=dict(t=10, b=10, l=10, r=10),
                    paper_bgcolor="rgba(0,0,0,0)"
                )
                st.plotly_chart(fig, use_container_width=True)

            # Detailed table
            st.markdown("**Item-wise Detail**")
            display_cols = ["item_code", "name", "category", "unit", "current_stock",
                            "reorder_level", "unit_cost", "stock_value", "stock_status", "supplier_name"]
            available = [c for c in display_cols if c in filtered.columns]
            st.dataframe(
                filtered[available].rename(columns={
                    "item_code": "Code", "name": "Item", "category": "Category",
                    "unit": "Unit", "current_stock": "Stock", "reorder_level": "Reorder At",
                    "unit_cost": "Unit Cost (₹)", "stock_value": "Value (₹)",
                    "stock_status": "Status", "supplier_name": "Supplier"
                }),
                use_container_width=True, hide_index=True,
                column_config={
                    "Value (₹)": st.column_config.NumberColumn(format="₹%.2f"),
                    "Unit Cost (₹)": st.column_config.NumberColumn(format="₹%.2f"),
                }
            )

            # Download
            st.download_button(
                "⬇️ Download to Excel",
                data=to_excel(filtered[available]),
                file_name=f"stock_valuation_{date.today()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    # ── Tab 2: Dispatch Register ──────────────────────────────────────────────
    with tab2:
        st.subheader("Dispatch Register")

        col_d1, col_d2, col_d3 = st.columns(3)
        with col_d1:
            dr_from = st.date_input("From Date", value=date.today() - timedelta(days=30), key="dr_from")
        with col_d2:
            dr_to = st.date_input("To Date", value=date.today(), key="dr_to")
        with col_d3:
            customers = db.get_customer_options()
            cust_map = {"All Customers": None}
            for c in customers:
                cust_map[c["customer_name"]] = c["customer_id"]
            sel_cust = st.selectbox("Customer", list(cust_map.keys()), key="dr_cust")

        df2 = db.get_dispatch_register(
            date_from=str(dr_from),
            date_to=str(dr_to),
            customer_id=cust_map[sel_cust]
        )

        if df2.empty:
            st.info("No dispatches found for the selected filters.")
        else:
            # Summary
            total_dns = df2["dn_number"].nunique()
            total_qty = df2["qty_dispatched"].sum()
            k1, k2, k3 = st.columns(3)
            k1.metric("Dispatch Notes", total_dns)
            k2.metric("Total Qty Dispatched", f"{total_qty:,.0f}")
            k3.metric("Customers Served", df2["customer_name"].nunique())

            st.markdown("<hr>", unsafe_allow_html=True)

            # Customer-wise summary
            st.markdown("**Customer-wise Summary**")
            cust_summary = (df2.groupby("customer_name")
                               .agg(dispatches=("dn_number", "nunique"),
                                    total_qty=("qty_dispatched", "sum"))
                               .reset_index()
                               .rename(columns={
                                   "customer_name": "Customer",
                                   "dispatches": "DN Count",
                                   "total_qty": "Total Qty"
                               }))
            st.dataframe(cust_summary, use_container_width=True, hide_index=True)

            st.markdown("**Line-wise Detail**")
            st.dataframe(
                df2.rename(columns={
                    "dn_number": "DN #", "so_number": "SO #",
                    "customer_name": "Customer", "dispatch_date": "Date",
                    "vehicle_no": "Vehicle", "item_code": "Code",
                    "item_name": "Item", "unit": "Unit",
                    "qty_dispatched": "Qty Dispatched"
                }),
                use_container_width=True, hide_index=True
            )

            st.download_button(
                "⬇️ Download to Excel",
                data=to_excel(df2),
                file_name=f"dispatch_register_{dr_from}_to_{dr_to}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    # ── Tab 3: Pending Orders ─────────────────────────────────────────────────
    with tab3:
        st.subheader("Pending Orders Report")

        order_type = st.radio("Order Type", ["Sales Orders (SO)", "Purchase Orders (PO)"],
                               horizontal=True, key="pending_type")
        otype = "SO" if "Sales" in order_type else "PO"

        df3 = db.get_pending_orders(order_type=otype)

        if df3.empty:
            st.success(f"✅ No pending {otype}s — all orders fulfilled!")
        else:
            # Summary KPIs
            total_pending_val = df3["pending_value"].sum() if "pending_value" in df3.columns else 0
            overdue = len(df3[df3["age_days"] > 7]) if "age_days" in df3.columns else 0

            k1, k2, k3 = st.columns(3)
            k1.metric("Pending Lines", len(df3))
            if "pending_value" in df3.columns:
                k2.metric("Pending Value (₹)", f"{total_pending_val:,.2f}")
            k3.metric("Overdue (>7 days)", overdue)

            st.markdown("<hr>", unsafe_allow_html=True)

            # Ageing highlight
            if "age_days" in df3.columns:
                def age_color(val):
                    if val > 14:
                        return "🔴"
                    elif val > 7:
                        return "🟠"
                    return "🟢"
                df3["Ageing"] = df3["age_days"].apply(lambda x: f"{age_color(x)} {x} days")

            if otype == "SO":
                display_cols = ["so_number", "customer_name", "order_date", "expected_date",
                                "item_code", "item_name", "unit", "qty_ordered",
                                "qty_dispatched", "qty_pending", "pending_value", "Ageing", "status"]
                rename_map = {
                    "so_number": "SO #", "customer_name": "Customer",
                    "order_date": "Order Date", "expected_date": "Expected",
                    "item_code": "Code", "item_name": "Item", "unit": "Unit",
                    "qty_ordered": "Ordered", "qty_dispatched": "Dispatched",
                    "qty_pending": "Pending", "pending_value": "Pending Value (₹)",
                    "status": "Status"
                }
            else:
                display_cols = ["po_number", "supplier_name", "order_date", "expected_date",
                                "item_code", "item_name", "unit", "qty_ordered",
                                "qty_received", "qty_pending", "Ageing", "status"]
                rename_map = {
                    "po_number": "PO #", "supplier_name": "Supplier",
                    "order_date": "Order Date", "expected_date": "Expected",
                    "item_code": "Code", "item_name": "Item", "unit": "Unit",
                    "qty_ordered": "Ordered", "qty_received": "Received",
                    "qty_pending": "Pending", "status": "Status"
                }

            available = [c for c in display_cols if c in df3.columns]
            st.dataframe(
                df3[available].rename(columns=rename_map),
                use_container_width=True, hide_index=True,
                column_config={
                    "Pending Value (₹)": st.column_config.NumberColumn(format="₹%.2f"),
                }
            )

            dl_df = df3.drop(columns=["Ageing"], errors="ignore")
            st.download_button(
                "⬇️ Download to Excel",
                data=to_excel(dl_df),
                file_name=f"pending_{otype.lower()}s_{date.today()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    # ── Tab 4: Production Summary ─────────────────────────────────────────────
    with tab4:
        st.subheader("Production Summary Report")

        df4 = db.get_production_summary()

        if df4.empty:
            st.info("No production orders found.")
        else:
            # Filter by status
            status_filter = st.selectbox("Filter by Status",
                                          ["All", "Completed", "In Progress", "Planned", "Cancelled"],
                                          key="prd_status")
            filtered4 = df4.copy()
            if status_filter != "All":
                filtered4 = filtered4[filtered4["status"] == status_filter]

            # KPIs
            completed = filtered4[filtered4["status"] == "Completed"]
            avg_efficiency = completed["efficiency_%"].mean() if not completed.empty else 0
            avg_wastage = completed["wastage_%"].mean() if not completed.empty else 0
            total_produced = completed["qty_produced"].sum() if not completed.empty else 0

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Total Orders", len(filtered4))
            k2.metric("Total Qty Produced", f"{total_produced:,.0f}")
            k3.metric("Avg Efficiency", f"{avg_efficiency:.1f}%")
            k4.metric("Avg Wastage %", f"{avg_wastage:.1f}%")

            st.markdown("<hr>", unsafe_allow_html=True)

            # Charts
            if not completed.empty:
                col_ch1, col_ch2 = st.columns(2)
                with col_ch1:
                    st.markdown("**Planned vs Produced**")
                    chart_df = completed[["order_number", "qty_planned", "qty_produced"]].copy()
                    fig1 = px.bar(
                        chart_df.melt(id_vars="order_number",
                                       value_vars=["qty_planned", "qty_produced"],
                                       var_name="Type", value_name="Qty"),
                        x="order_number", y="Qty", color="Type",
                        color_discrete_map={"qty_planned": "#94A3B8", "qty_produced": "#0D1B2A"},
                        barmode="group",
                        labels={"order_number": "Order", "Qty": "Quantity"}
                    )
                    fig1.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        height=280, margin=dict(t=10, b=10),
                        legend=dict(orientation="h", y=1.1)
                    )
                    st.plotly_chart(fig1, use_container_width=True)

                with col_ch2:
                    st.markdown("**Wastage % per Order**")
                    fig2 = px.bar(
                        completed, x="order_number", y="wastage_%",
                        color_discrete_sequence=["#C9A84C"],
                        labels={"order_number": "Order", "wastage_%": "Wastage %"}
                    )
                    fig2.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        height=280, margin=dict(t=10, b=10)
                    )
                    st.plotly_chart(fig2, use_container_width=True)

            # Detail table
            st.markdown("**Order-wise Detail**")
            display_cols = ["order_number", "product_code", "product_name", "qty_planned",
                            "qty_produced", "efficiency_%", "material_planned",
                            "material_actual", "wastage", "wastage_%", "status",
                            "start_date", "end_date"]
            available4 = [c for c in display_cols if c in filtered4.columns]
            st.dataframe(
                filtered4[available4].rename(columns={
                    "order_number": "Order #", "product_code": "Code",
                    "product_name": "Product", "qty_planned": "Planned",
                    "qty_produced": "Produced", "efficiency_%": "Efficiency %",
                    "material_planned": "Mat. Planned", "material_actual": "Mat. Actual",
                    "wastage": "Wastage", "wastage_%": "Wastage %",
                    "status": "Status", "start_date": "Start", "end_date": "End"
                }),
                use_container_width=True, hide_index=True,
                column_config={
                    "Efficiency %": st.column_config.NumberColumn(format="%.1f%%"),
                    "Wastage %": st.column_config.NumberColumn(format="%.1f%%"),
                }
            )

            st.download_button(
                "⬇️ Download to Excel",
                data=to_excel(filtered4),
                file_name=f"production_summary_{date.today()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
