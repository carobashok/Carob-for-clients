"""
db.py — Supabase connection & data helpers for Carob Inventory Manager
"""
import os
import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import date

# ── Connection ──────────────────────────────────────────────────────────────

@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

# ── Items ────────────────────────────────────────────────────────────────────

def get_all_items() -> pd.DataFrame:
    sb = get_supabase()
    res = sb.table("items").select("*, suppliers(name)").order("item_code").execute()
    if not res.data:
        return pd.DataFrame()
    df = pd.json_normalize(res.data)
    df.rename(columns={"suppliers.name": "supplier_name"}, inplace=True)
    return df

def get_stock_alerts() -> pd.DataFrame:
    sb = get_supabase()
    res = sb.table("v_stock_alerts").select("*").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def update_item_stock(item_id: int, new_stock: float):
    sb = get_supabase()
    sb.table("items").update({"current_stock": new_stock}).eq("id", item_id).execute()

def add_item(data: dict):
    sb = get_supabase()
    sb.table("items").insert(data).execute()

def get_item_options() -> dict:
    """Returns {item_name: item_id} for dropdowns"""
    sb = get_supabase()
    res = sb.table("items").select("id, name, item_code, unit, unit_cost").order("name").execute()
    return res.data if res.data else []


# ── Suppliers ────────────────────────────────────────────────────────────────

def get_all_suppliers() -> pd.DataFrame:
    sb = get_supabase()
    res = sb.table("suppliers").select("*").order("name").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def get_supplier_options() -> list:
    sb = get_supabase()
    res = sb.table("suppliers").select("id, name").order("name").execute()
    return res.data if res.data else []

def add_supplier(data: dict):
    sb = get_supabase()
    sb.table("suppliers").insert(data).execute()


# ── Purchase Orders ──────────────────────────────────────────────────────────

def get_po_summary() -> pd.DataFrame:
    sb = get_supabase()
    res = sb.table("v_po_summary").select("*").order("order_date", desc=True).execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def get_po_lines(po_id: int) -> pd.DataFrame:
    sb = get_supabase()
    res = (sb.table("po_lines")
             .select("*, items(name, item_code, unit)")
             .eq("po_id", po_id)
             .execute())
    if not res.data:
        return pd.DataFrame()
    df = pd.json_normalize(res.data)
    df.rename(columns={"items.name": "item_name", "items.item_code": "item_code",
                        "items.unit": "unit"}, inplace=True)
    return df

def create_po(supplier_id: int, order_date: date, expected_date: date,
              notes: str, lines: list) -> str:
    sb = get_supabase()
    # Generate PO number
    count_res = sb.table("purchase_orders").select("id", count="exact").execute()
    po_num = f"PO-{(count_res.count or 0) + 1:04d}"
    total = sum(l["qty_ordered"] * l["unit_price"] for l in lines)
    po_res = sb.table("purchase_orders").insert({
        "po_number": po_num,
        "supplier_id": supplier_id,
        "order_date": str(order_date),
        "expected_date": str(expected_date),
        "notes": notes,
        "status": "Ordered",
        "total_value": total
    }).execute()
    po_id = po_res.data[0]["id"]
    for line in lines:
        line["po_id"] = po_id
        sb.table("po_lines").insert(line).execute()
    return po_num

def receive_po(po_id: int, lines_received: list):
    """Mark items as received, update stock, log movement"""
    sb = get_supabase()
    all_received = True
    for line in lines_received:
        sb.table("po_lines").update(
            {"qty_received": line["qty_received"]}
        ).eq("id", line["line_id"]).execute()
        if line["qty_received"] > 0:
            # Get current stock
            item_res = sb.table("items").select("current_stock").eq("id", line["item_id"]).execute()
            cur = item_res.data[0]["current_stock"]
            sb.table("items").update(
                {"current_stock": cur + line["qty_received"]}
            ).eq("id", line["item_id"]).execute()
            sb.table("stock_movements").insert({
                "item_id": line["item_id"],
                "movement_type": "GRN",
                "qty": line["qty_received"],
                "reference": line.get("po_number", ""),
                "remarks": "Received against PO",
                "movement_date": str(date.today())
            }).execute()
        if line["qty_received"] < line["qty_ordered"]:
            all_received = False
    status = "Received" if all_received else "Partial"
    sb.table("purchase_orders").update({"status": status}).eq("id", po_id).execute()


# ── Stock Movements ──────────────────────────────────────────────────────────

def get_movements(item_id: int = None, limit: int = 100) -> pd.DataFrame:
    sb = get_supabase()
    q = (sb.table("stock_movements")
           .select("*, items(name, item_code, unit)")
           .order("movement_date", desc=True)
           .limit(limit))
    if item_id:
        q = q.eq("item_id", item_id)
    res = q.execute()
    if not res.data:
        return pd.DataFrame()
    df = pd.json_normalize(res.data)
    df.rename(columns={"items.name": "item_name", "items.item_code": "item_code",
                        "items.unit": "unit"}, inplace=True)
    return df

def log_movement(item_id: int, movement_type: str, qty: float,
                 reference: str = "", remarks: str = ""):
    sb = get_supabase()
    item_res = sb.table("items").select("current_stock").eq("id", item_id).execute()
    cur = item_res.data[0]["current_stock"]
    delta = qty if movement_type in ("GRN", "Return", "Adjustment") else -qty
    sb.table("items").update({"current_stock": cur + delta}).eq("id", item_id).execute()
    sb.table("stock_movements").insert({
        "item_id": item_id,
        "movement_type": movement_type,
        "qty": delta,
        "reference": reference,
        "remarks": remarks,
        "movement_date": str(date.today())
    }).execute()


# ── Production ───────────────────────────────────────────────────────────────

def get_production_orders() -> pd.DataFrame:
    sb = get_supabase()
    res = (sb.table("production_orders")
             .select("*, items(name, item_code)")
             .order("created_at", desc=True)
             .execute())
    if not res.data:
        return pd.DataFrame()
    df = pd.json_normalize(res.data)
    df.rename(columns={"items.name": "product_name", "items.item_code": "product_code"}, inplace=True)
    return df

def get_consumption(production_order_id: int) -> pd.DataFrame:
    sb = get_supabase()
    res = (sb.table("production_consumption")
             .select("*, items(name, item_code, unit)")
             .eq("production_order_id", production_order_id)
             .execute())
    if not res.data:
        return pd.DataFrame()
    df = pd.json_normalize(res.data)
    df.rename(columns={"items.name": "item_name", "items.item_code": "item_code",
                        "items.unit": "unit"}, inplace=True)
    return df

def create_production_order(product_id: int, qty_planned: float,
                             start_date: date, end_date: date, bom: list) -> str:
    sb = get_supabase()
    count_res = sb.table("production_orders").select("id", count="exact").execute()
    order_num = f"PRD-{(count_res.count or 0) + 1:04d}"
    po_res = sb.table("production_orders").insert({
        "order_number": order_num,
        "product_id": product_id,
        "qty_planned": qty_planned,
        "status": "Planned",
        "start_date": str(start_date),
        "end_date": str(end_date)
    }).execute()
    prd_id = po_res.data[0]["id"]
    for bom_line in bom:
        bom_line["production_order_id"] = prd_id
        sb.table("production_consumption").insert(bom_line).execute()
    return order_num

def complete_production(production_order_id: int, qty_produced: float, consumption: list):
    sb = get_supabase()
    for line in consumption:
        sb.table("production_consumption").update({
            "qty_actual": line["qty_actual"],
            "wastage": line.get("wastage", 0)
        }).eq("id", line["consumption_id"]).execute()
        # Deduct from stock
        item_res = sb.table("items").select("current_stock").eq("id", line["item_id"]).execute()
        cur = item_res.data[0]["current_stock"]
        total_used = line["qty_actual"] + line.get("wastage", 0)
        sb.table("items").update({"current_stock": cur - total_used}).eq("id", line["item_id"]).execute()
        sb.table("stock_movements").insert({
            "item_id": line["item_id"],
            "movement_type": "Issue",
            "qty": -total_used,
            "reference": line.get("order_number", ""),
            "remarks": f"Production consumption (wastage: {line.get('wastage', 0)})",
            "movement_date": str(date.today())
        }).execute()
    # Update finished good stock
    order_res = sb.table("production_orders").select("product_id").eq("id", production_order_id).execute()
    product_id = order_res.data[0]["product_id"]
    item_res = sb.table("items").select("current_stock").eq("id", product_id).execute()
    cur = item_res.data[0]["current_stock"]
    sb.table("items").update({"current_stock": cur + qty_produced}).eq("id", product_id).execute()
    sb.table("production_orders").update({
        "qty_produced": qty_produced,
        "status": "Completed"
    }).eq("id", production_order_id).execute()


# ── Dashboard KPIs ────────────────────────────────────────────────────────────

def get_dashboard_kpis() -> dict:
    sb = get_supabase()
    items_res = sb.table("items").select("current_stock, unit_cost, reorder_level").execute()
    items = items_res.data or []
    total_value = sum(i["current_stock"] * i["unit_cost"] for i in items)
    low_stock = sum(1 for i in items if 0 < i["current_stock"] <= i["reorder_level"])
    out_of_stock = sum(1 for i in items if i["current_stock"] == 0)

    po_res = sb.table("purchase_orders").select("status, total_value").execute()
    pos = po_res.data or []
    open_po_value = sum(p["total_value"] for p in pos if p["status"] in ("Ordered", "Partial"))
    open_po_count = sum(1 for p in pos if p["status"] in ("Ordered", "Partial"))

    prd_res = sb.table("production_orders").select("status").execute()
    prds = prd_res.data or []
    active_production = sum(1 for p in prds if p["status"] == "In Progress")

    return {
        "total_items": len(items),
        "total_stock_value": total_value,
        "low_stock_alerts": low_stock,
        "out_of_stock": out_of_stock,
        "open_po_count": open_po_count,
        "open_po_value": open_po_value,
        "active_production": active_production
    }
