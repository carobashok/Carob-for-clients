"""
Carob Order Portal — Distributor App
Distributors place orders; admin approves and converts to SO
"""
import streamlit as st
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portal_db as db
from proforma import generate_proforma_html

st.set_page_config(
    page_title="Carob Order Portal",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=DM+Sans:wght@300;400;500;600&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

[data-testid="stSidebar"] { background: #0A0A0F; }
[data-testid="stSidebar"] * { color: #E8E8E8 !important; }
[data-testid="stSidebarNav"] { display: none !important; }

[data-testid="stMetric"] {
    background: #F8F6F0; border: 1px solid #EDE8E0;
    border-radius: 10px; padding: 16px 20px;
}
[data-testid="stMetricValue"] {
    font-family: 'Playfair Display', serif !important;
    font-size: 2rem !important; font-weight: 700 !important; color: #0A0A0F !important;
}

.portal-title { font-family: 'Playfair Display', serif; font-size: 2rem; font-weight: 700; color: #0A0A0F; margin-bottom: 4px; }
.portal-sub { font-size: 0.85rem; color: #8A8A9A; margin-bottom: 24px; }

.product-card {
    border: 1px solid #EDE8E0; border-radius: 12px; padding: 20px;
    background: #FAFAF8; margin-bottom: 12px;
}
.product-name { font-family: 'Playfair Display', serif; font-size: 1.1rem; font-weight: 700; color: #0A0A0F; }
.product-cat { font-size: 0.78rem; color: #8A8A9A; margin-bottom: 8px; }
.product-price { font-size: 1.1rem; font-weight: 700; color: #C9A84C; }
.product-moq { font-size: 0.78rem; color: #8A8A9A; }

.status-pending { background: #FEF9C3; color: #854D0E; padding: 3px 10px; border-radius: 99px; font-size: 0.75rem; font-weight: 600; }
.status-approved { background: #DCFCE7; color: #166534; padding: 3px 10px; border-radius: 99px; font-size: 0.75rem; font-weight: 600; }
.status-rejected { background: #FEE2E2; color: #991B1B; padding: 3px 10px; border-radius: 99px; font-size: 0.75rem; font-weight: 600; }
.status-change { background: #DBEAFE; color: #1E40AF; padding: 3px 10px; border-radius: 99px; font-size: 0.75rem; font-weight: 600; }

.stButton > button { background: #0A0A0F; color: #C9A84C; border: none; border-radius: 6px; font-weight: 600; }
.stButton > button:hover { background: #C9A84C; color: #0A0A0F; }
#MainMenu, footer, header { visibility: hidden; }
hr { border: none; border-top: 1px solid #EDE8E0; margin: 20px 0; }
</style>
""", unsafe_allow_html=True)


# ── Session state ─────────────────────────────────────────────────────────────
if "portal_user" not in st.session_state:
    st.session_state.portal_user = None
if "cart" not in st.session_state:
    st.session_state.cart = []


# ── LOGIN ─────────────────────────────────────────────────────────────────────
def show_login():
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("""
        <div style='text-align:center;padding:40px 0 24px;'>
            <div style='font-family:Playfair Display,serif;font-size:2.2rem;font-weight:900;color:#C9A84C;'>
                Carob Order Portal
            </div>
            <div style='font-size:0.8rem;color:#8A8A9A;letter-spacing:2px;text-transform:uppercase;margin-top:4px;'>
                Distributor Login
            </div>
        </div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            username = st.text_input("Username", placeholder="e.g. rajan_ent")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            submitted = st.form_submit_button("Sign In →", use_container_width=True)

        if submitted:
            user = db.login_user(username, password)
            if user:
                st.session_state.portal_user = user
                st.session_state.cart = []
                st.rerun()
            else:
                st.error("Invalid username or password. Please try again.")

        st.markdown("""
        <div style='text-align:center;margin-top:16px;font-size:0.78rem;color:#8A8A9A;'>
            Demo credentials: rajan_ent / demo123
        </div>
        """, unsafe_allow_html=True)


# ── SIDEBAR (logged in) ───────────────────────────────────────────────────────
def show_sidebar():
    user = st.session_state.portal_user
    with st.sidebar:
        st.markdown(f"""
        <div style='padding:8px 0 16px;'>
            <div style='font-family:Playfair Display,serif;font-size:1.3rem;font-weight:900;color:#C9A84C;'>
                Carob Portal
            </div>
            <div style='font-size:0.65rem;color:#475569;letter-spacing:1.5px;text-transform:uppercase;margin-top:2px;'>
                Distributor
            </div>
        </div>
        <div style='background:#1C1C2E;border-radius:8px;padding:10px 12px;margin-bottom:16px;'>
            <div style='font-size:0.8rem;font-weight:600;color:#C9A84C;'>{user['company_name']}</div>
            <div style='font-size:0.72rem;color:#8A8A9A;margin-top:2px;'>{user['city']}</div>
        </div>
        <hr style='border-color:#1E3A5F;margin-bottom:12px;'/>
        """, unsafe_allow_html=True)

        cart_count = len(st.session_state.cart)
        cart_label = f"🛒 My Cart ({cart_count})" if cart_count else "🛒 My Cart"

        page = st.radio("Navigation", [
            "📊 Dashboard",
            "🎨 Product Catalogue",
            cart_label,
            "📋 My Orders"
        ], label_visibility="collapsed")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Sign Out", use_container_width=True):
            st.session_state.portal_user = None
            st.session_state.cart = []
            st.rerun()

        st.markdown("""
        <div style='font-size:0.68rem;color:#475569;border-top:1px solid #1E3A5F;padding-top:10px;margin-top:8px;'>
            Carob Order Portal · v1.0
        </div>
        """, unsafe_allow_html=True)

    return page


# ── DASHBOARD ─────────────────────────────────────────────────────────────────
def show_dashboard():
    user = st.session_state.portal_user
    st.markdown(f'<div class="portal-title">Welcome, {user["company_name"]}</div>', unsafe_allow_html=True)
    st.markdown('<div class="portal-sub">Your ordering dashboard</div>', unsafe_allow_html=True)

    orders_df = db.get_my_orders(user["id"])
    pending = len(orders_df[orders_df["status"] == "Pending"]) if not orders_df.empty else 0
    approved = len(orders_df[orders_df["status"] == "Approved"]) if not orders_df.empty else 0
    total_val = orders_df["total_value"].sum() if not orders_df.empty else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Orders", len(orders_df))
    k2.metric("Pending Approval", pending)
    k3.metric("Approved", approved)
    k4.metric("Total Order Value (₹)", f"{total_val:,.0f}")

    st.markdown("<hr>", unsafe_allow_html=True)

    # Featured products
    st.subheader("Featured Products")
    featured = db.get_featured_products()
    if not featured.empty:
        cols = st.columns(min(len(featured), 4))
        for i, (_, prod) in enumerate(featured.iterrows()):
            with cols[i % 4]:
                stock_status = "✅ In Stock" if prod["current_stock"] > 0 else "⚠️ Low Stock"
                st.markdown(f"""
                <div class="product-card">
                    <div class="product-name">{prod['name']}</div>
                    <div class="product-cat">{prod['category']}</div>
                    <div class="product-price">₹{prod['base_price']:,.0f}/{prod['unit']}</div>
                    <div class="product-moq">MOQ: {prod['moq']} {prod['unit']} · {stock_status}</div>
                </div>
                """, unsafe_allow_html=True)

    # Recent orders
    if not orders_df.empty:
        st.markdown("<hr>", unsafe_allow_html=True)
        st.subheader("Recent Orders")
        recent = orders_df.head(5)[["order_number", "order_date", "status", "total_value"]]
        st.dataframe(recent.rename(columns={
            "order_number": "Order #", "order_date": "Date",
            "status": "Status", "total_value": "Value (₹)"
        }), use_container_width=True, hide_index=True)


# ── PRODUCT CATALOGUE ─────────────────────────────────────────────────────────
def show_catalogue():
    st.markdown('<div class="portal-title">Product Catalogue</div>', unsafe_allow_html=True)
    st.markdown('<div class="portal-sub">Browse and add to cart</div>', unsafe_allow_html=True)

    products = db.get_active_products()
    if products.empty:
        st.info("No products available at this time.")
        return

    categories = ["All"] + sorted(products["category"].dropna().unique().tolist())
    col_f1, col_f2 = st.columns([2, 1.5])
    with col_f1:
        search = st.text_input("🔍 Search products", "")
    with col_f2:
        cat_filter = st.selectbox("Category", categories)

    filtered = products.copy()
    if search:
        filtered = filtered[filtered["name"].str.contains(search, case=False)]
    if cat_filter != "All":
        filtered = filtered[filtered["category"] == cat_filter]

    for _, prod in filtered.iterrows():
        with st.expander(f"**{prod['name']}** — ₹{prod['base_price']:,.0f}/{prod['unit']} · {prod['category']}", expanded=False):
            col_info, col_order = st.columns([2, 1])
            with col_info:
                st.markdown(f"**Description:** {prod.get('description','—')}")
                st.markdown(f"**MOQ:** {prod['moq']} {prod['unit']}")
                stock_color = "🟢" if prod["current_stock"] > prod["moq"] * 2 else "🟡" if prod["current_stock"] > 0 else "🔴"
                st.markdown(f"**Stock:** {stock_color} {prod['current_stock']} {prod['unit']}")

                tiers = db.get_pricing_tiers(prod["id"])
                if tiers:
                    st.markdown("**Bulk Pricing:**")
                    tier_data = []
                    for t in tiers:
                        qty_range = f"{t['qty_from']}–{t['qty_to']} {prod['unit']}" if t["qty_to"] else f"{t['qty_from']}+ {prod['unit']}"
                        discounted = prod["base_price"] * (1 - t["discount_pct"] / 100)
                        tier_data.append({
                            "Quantity": qty_range,
                            "Discount": f"{t['discount_pct']}%",
                            "Price": f"₹{discounted:,.2f}/{prod['unit']}"
                        })
                    st.dataframe(pd.DataFrame(tier_data), use_container_width=True, hide_index=True)

            with col_order:
                if prod["current_stock"] <= 0:
                    st.warning("Out of stock")
                else:
                    qty = st.number_input(
                        f"Qty ({prod['unit']})",
                        min_value=float(prod["moq"]),
                        value=float(prod["moq"]),
                        step=float(prod["moq"]),
                        key=f"qty_{prod['id']}"
                    )
                    unit_price, discount = db.calculate_price(prod.to_dict(), qty)
                    line_total = qty * unit_price
                    if discount > 0:
                        st.markdown(f"**Price:** ~~₹{prod['base_price']:,.2f}~~ ₹{unit_price:,.2f} ({discount:.0f}% off)")
                    else:
                        st.markdown(f"**Price:** ₹{unit_price:,.2f}/{prod['unit']}")
                    st.markdown(f"**Line Total:** ₹{line_total:,.2f}")

                    if st.button("Add to Cart 🛒", key=f"add_{prod['id']}"):
                        existing = next((i for i, c in enumerate(st.session_state.cart)
                                        if c["product_id"] == prod["id"]), None)
                        if existing is not None:
                            st.session_state.cart[existing]["qty"] += qty
                            st.session_state.cart[existing]["unit_price"] = unit_price
                            st.session_state.cart[existing]["discount_pct"] = discount
                        else:
                            st.session_state.cart.append({
                                "product_id": prod["id"],
                                "product_name": prod["name"],
                                "product_code": prod["product_code"],
                                "unit": prod["unit"],
                                "qty": qty,
                                "unit_price": unit_price,
                                "discount_pct": discount
                            })
                        st.success(f"✅ {prod['name']} added to cart!")
                        st.rerun()


# ── CART ─────────────────────────────────────────────────────────────────────
def show_cart():
    st.markdown('<div class="portal-title">My Cart</div>', unsafe_allow_html=True)
    st.markdown('<div class="portal-sub">Review and place your order</div>', unsafe_allow_html=True)

    user = st.session_state.portal_user

    if not st.session_state.cart:
        st.info("Your cart is empty. Browse the Product Catalogue to add items.")
        return

    cart_df = pd.DataFrame(st.session_state.cart)
    cart_df["line_total"] = cart_df["qty"] * cart_df["unit_price"]

    st.dataframe(
        cart_df[["product_code", "product_name", "unit", "qty",
                  "discount_pct", "unit_price", "line_total"]].rename(columns={
            "product_code": "Code", "product_name": "Product",
            "unit": "Unit", "qty": "Qty", "discount_pct": "Disc %",
            "unit_price": "Unit Price (₹)", "line_total": "Total (₹)"
        }),
        use_container_width=True, hide_index=True,
        column_config={
            "Unit Price (₹)": st.column_config.NumberColumn(format="₹%.2f"),
            "Total (₹)": st.column_config.NumberColumn(format="₹%.2f"),
        }
    )

    total = cart_df["line_total"].sum()
    st.markdown(f"### Order Total: ₹{total:,.2f}")
    st.markdown("<hr>", unsafe_allow_html=True)

    col_addr, col_act = st.columns([2, 1])
    with col_addr:
        delivery_address = st.text_area(
            "Delivery Address *",
            value=user.get("address", ""),
            height=100
        )
        notes = st.text_input("Order Notes / Special Instructions", "")

    with col_act:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑 Clear Cart"):
            st.session_state.cart = []
            st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("✅ Place Order", use_container_width=True):
            if not delivery_address:
                st.error("Please enter a delivery address.")
            else:
                order_num = db.place_order(
                    user["id"], delivery_address, notes,
                    st.session_state.cart
                )
                st.success(f"✅ Order **{order_num}** placed successfully! "
                           f"You will be notified once it is approved.")
                st.session_state.cart = []
                st.rerun()


# ── MY ORDERS ─────────────────────────────────────────────────────────────────
def show_my_orders():
    st.markdown('<div class="portal-title">My Orders</div>', unsafe_allow_html=True)
    st.markdown('<div class="portal-sub">Track your order status and download proformas</div>', unsafe_allow_html=True)

    user = st.session_state.portal_user
    orders_df = db.get_my_orders(user["id"])

    if orders_df.empty:
        st.info("No orders placed yet.")
        return

    status_filter = st.selectbox("Filter by Status",
                                  ["All", "Pending", "Approved", "Change Requested", "Rejected"])
    df = orders_df.copy()
    if status_filter != "All":
        df = df[df["status"] == status_filter]

    for _, order in df.iterrows():
        status = order["status"]
        status_class = {
            "Pending": "status-pending",
            "Approved": "status-approved",
            "Rejected": "status-rejected",
            "Change Requested": "status-change"
        }.get(status, "")

        with st.expander(
            f"**{order['order_number']}** · {order['order_date']} · ₹{order['total_value']:,.0f} · {status}",
            expanded=(status == "Change Requested")
        ):
            col_o1, col_o2 = st.columns([2, 1])
            with col_o1:
                lines = db.get_order_lines(order["id"])
                if not lines.empty:
                    dcols = ["product_code", "product_name", "unit", "qty",
                             "discount_pct", "unit_price", "line_total"]
                    available = [c for c in dcols if c in lines.columns]
                    st.dataframe(lines[available].rename(columns={
                        "product_code": "Code", "product_name": "Product",
                        "unit": "Unit", "qty": "Qty", "discount_pct": "Disc %",
                        "unit_price": "Unit Price (₹)", "line_total": "Total (₹)"
                    }), use_container_width=True, hide_index=True)

                if order.get("admin_remarks"):
                    if status == "Change Requested":
                        st.warning(f"📝 Admin note: {order['admin_remarks']}")
                    elif status == "Rejected":
                        st.error(f"❌ Rejection reason: {order['admin_remarks']}")

            with col_o2:
                st.markdown(f"**Status:** {status}")
                st.markdown(f"**Delivery to:** {order.get('delivery_address','—')}")
                if order.get("so_number"):
                    st.markdown(f"**SO Number:** {order['so_number']}")

                if status == "Approved":
                    lines = db.get_order_lines(order["id"])
                    proforma_html = generate_proforma_html(order.to_dict(), lines)
                    st.download_button(
                        "⬇️ Download Proforma Invoice",
                        data=proforma_html,
                        file_name=f"Proforma_{order['order_number']}.html",
                        mime="text/html",
                        key=f"dl_{order['id']}"
                    )


# ── MAIN ─────────────────────────────────────────────────────────────────────
if st.session_state.portal_user is None:
    show_login()
else:
    page = show_sidebar()
    if "Dashboard" in page:
        show_dashboard()
    elif "Catalogue" in page:
        show_catalogue()
    elif "Cart" in page:
        show_cart()
    elif "Orders" in page:
        show_my_orders()
