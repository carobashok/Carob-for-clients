"""
portal_db.py — Supabase helpers for Carob Order Portal
"""
import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import date

@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)


# ── Auth ──────────────────────────────────────────────────────────────────────

def login_user(username: str, password: str) -> dict | None:
    sb = get_supabase()
    res = (sb.table("portal_users")
             .select("*")
             .eq("username", username)
             .eq("password_hash", password)
             .eq("is_active", True)
             .execute())
    return res.data[0] if res.data else None


# ── Products ──────────────────────────────────────────────────────────────────

def get_active_products() -> pd.DataFrame:
    sb = get_supabase()
    res = sb.table("portal_products").select("*").eq("is_active", True).order("name").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def get_featured_products() -> pd.DataFrame:
    sb = get_supabase()
    res = (sb.table("portal_products")
             .select("*")
             .eq("is_active", True)
             .eq("is_featured", True)
             .execute())
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def get_all_products() -> pd.DataFrame:
    sb = get_supabase()
    res = sb.table("portal_products").select("*").order("name").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def get_pricing_tiers(product_id: int) -> list:
    sb = get_supabase()
    res = (sb.table("portal_pricing_tiers")
             .select("*")
             .eq("product_id", product_id)
             .order("qty_from")
             .execute())
    return res.data or []

def get_all_tiers() -> pd.DataFrame:
    sb = get_supabase()
    res = (sb.table("portal_pricing_tiers")
             .select("*, portal_products(name, product_code)")
             .order("product_id")
             .execute())
    if not res.data:
        return pd.DataFrame()
    df = pd.json_normalize(res.data)
    df.rename(columns={"portal_products.name": "product_name",
                        "portal_products.product_code": "product_code"}, inplace=True)
    return df

def calculate_price(product: dict, qty: float) -> tuple:
    """Returns (unit_price, discount_pct) based on qty and tiers"""
    tiers = get_pricing_tiers(product["id"])
    base = product["base_price"]
    discount = 0
    for tier in tiers:
        if qty >= tier["qty_from"]:
            if tier["qty_to"] is None or qty <= tier["qty_to"]:
                discount = tier["discount_pct"]
                break
            discount = tier["discount_pct"]
    unit_price = round(base * (1 - discount / 100), 2)
    return unit_price, discount

def add_product(data: dict):
    sb = get_supabase()
    sb.table("portal_products").insert(data).execute()

def update_product(product_id: int, data: dict):
    sb = get_supabase()
    sb.table("portal_products").update(data).eq("id", product_id).execute()

def save_pricing_tiers(product_id: int, tiers: list):
    sb = get_supabase()
    sb.table("portal_pricing_tiers").delete().eq("product_id", product_id).execute()
    for tier in tiers:
        tier["product_id"] = product_id
        sb.table("portal_pricing_tiers").insert(tier).execute()


# ── Portal Orders ─────────────────────────────────────────────────────────────

def get_my_orders(portal_user_id: int) -> pd.DataFrame:
    sb = get_supabase()
    res = (sb.table("portal_orders")
             .select("*")
             .eq("portal_user_id", portal_user_id)
             .order("created_at", desc=True)
             .execute())
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def get_order_lines(portal_order_id: int) -> pd.DataFrame:
    sb = get_supabase()
    res = (sb.table("portal_order_lines")
             .select("*, portal_products(name, product_code, unit, base_price, id)")
             .eq("portal_order_id", portal_order_id)
             .execute())
    if not res.data:
        return pd.DataFrame()
    df = pd.json_normalize(res.data)
    df.rename(columns={
        "portal_products.name": "product_name",
        "portal_products.product_code": "product_code",
        "portal_products.unit": "unit",
        "portal_products.base_price": "base_price",
        "portal_products.id": "portal_product_id"
    }, inplace=True)
    return df

def place_order(portal_user_id: int, delivery_address: str,
                notes: str, cart: list) -> str:
    sb = get_supabase()
    count_res = sb.table("portal_orders").select("id", count="exact").execute()
    order_num = f"DPI-{2000 + (count_res.count or 0) + 1}"
    total = sum(item["qty"] * item["unit_price"] for item in cart)
    order_res = sb.table("portal_orders").insert({
        "order_number": order_num,
        "portal_user_id": portal_user_id,
        "order_date": str(date.today()),
        "status": "Pending",
        "total_value": total,
        "delivery_address": delivery_address,
        "notes": notes
    }).execute()
    order_id = order_res.data[0]["id"]
    for item in cart:
        sb.table("portal_order_lines").insert({
            "portal_order_id": order_id,
            "product_id": item["product_id"],
            "qty": item["qty"],
            "unit_price": item["unit_price"],
            "discount_pct": item["discount_pct"]
        }).execute()
    return order_num

def resubmit_order(portal_order_id: int, updated_lines: list, notes: str = ""):
    """Distributor modifies and resubmits a Change Requested order"""
    sb = get_supabase()
    # Delete existing lines
    sb.table("portal_order_lines").delete().eq("portal_order_id", portal_order_id).execute()
    # Insert updated lines
    total = 0
    for line in updated_lines:
        sb.table("portal_order_lines").insert({
            "portal_order_id": portal_order_id,
            "product_id": line["product_id"],
            "qty": line["qty"],
            "unit_price": line["unit_price"],
            "discount_pct": line["discount_pct"]
        }).execute()
        total += line["qty"] * line["unit_price"]
    # Reset order status to Pending, clear admin remarks
    sb.table("portal_orders").update({
        "status": "Pending",
        "admin_remarks": None,
        "total_value": total,
        "notes": notes,
        "order_date": str(date.today())
    }).eq("id", portal_order_id).execute()


# ── Admin — Portal Order Management ──────────────────────────────────────────

def get_portal_orders_summary(status: str = None) -> pd.DataFrame:
    sb = get_supabase()
    q = sb.table("v_portal_orders").select("*").order("order_date", desc=True)
    if status:
        q = q.eq("status", status)
    res = q.execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def approve_order(portal_order_id: int, order_number: str,
                  portal_user_id: int, cart_lines: pd.DataFrame) -> str:
    sb = get_supabase()
    from datetime import datetime, timedelta

    user_res = sb.table("portal_users").select("*").eq("id", portal_user_id).execute()
    user = user_res.data[0]

    cust_res = sb.table("customers").select("customer_id").eq("customer_name", user["company_name"]).execute()
    if cust_res.data:
        customer_id = cust_res.data[0]["customer_id"]
    else:
        new_cust = sb.table("customers").insert({
            "customer_name": user["company_name"],
            "contact_person": user.get("contact_person", ""),
            "phone": user.get("phone", ""),
            "email": user.get("email", ""),
            "address": user.get("address", "-"),
            "city": user.get("city", ""),
            "pincode": "000000"
        }).execute()
        customer_id = new_cust.data[0]["customer_id"]

    so_count = sb.table("sales_orders").select("id", count="exact").execute()
    so_num = f"SO-{(so_count.count or 0) + 1:04d}"
    total = cart_lines["line_total"].sum() if not cart_lines.empty else 0
    exp_date = date.today() + timedelta(days=7)

    so_res = sb.table("sales_orders").insert({
        "so_number": so_num,
        "customer_id": customer_id,
        "customer_po_number": order_number,
        "order_date": str(date.today()),
        "expected_date": str(exp_date),
        "status": "Open",
        "total_value": float(total),
        "notes": f"Auto-created from portal order {order_number}"
    }).execute()
    so_id = so_res.data[0]["id"]

    for _, line in cart_lines.iterrows():
        item_res = sb.table("items").select("id").eq("item_code", line.get("product_code", "")).execute()
        if item_res.data:
            item_id = item_res.data[0]["id"]
            sb.table("so_lines").insert({
                "so_id": so_id,
                "item_id": item_id,
                "qty_ordered": float(line["qty"]),
                "qty_dispatched": 0,
                "unit_price": float(line["unit_price"])
            }).execute()

    sb.table("portal_orders").update({
        "status": "Approved",
        "so_number": so_num,
        "approved_at": datetime.utcnow().isoformat()
    }).eq("id", portal_order_id).execute()

    return so_num

def reject_order(portal_order_id: int, remarks: str):
    sb = get_supabase()
    sb.table("portal_orders").update({
        "status": "Rejected",
        "admin_remarks": remarks
    }).eq("id", portal_order_id).execute()

def request_change(portal_order_id: int, remarks: str):
    sb = get_supabase()
    sb.table("portal_orders").update({
        "status": "Change Requested",
        "admin_remarks": remarks
    }).eq("id", portal_order_id).execute()


# ── Portal Users (admin) ──────────────────────────────────────────────────────

def get_all_portal_users() -> pd.DataFrame:
    sb = get_supabase()
    res = sb.table("portal_users").select(
        "id, username, company_name, contact_person, phone, email, city, gstin, is_active, created_at"
    ).order("company_name").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def add_portal_user(data: dict):
    sb = get_supabase()
    sb.table("portal_users").insert(data).execute()

def toggle_portal_user(user_id: int, is_active: bool):
    sb = get_supabase()
    sb.table("portal_users").update({"is_active": is_active}).eq("id", user_id).execute()


# ── Proforma Invoice Data ─────────────────────────────────────────────────────

def get_proforma_data(portal_order_id: int) -> dict:
    sb = get_supabase()
    order_res = sb.table("v_portal_orders").select("*").eq("id", portal_order_id).execute()
    if not order_res.data:
        return {}
    order = order_res.data[0]
    lines = get_order_lines(portal_order_id)
    return {"order": order, "lines": lines}
