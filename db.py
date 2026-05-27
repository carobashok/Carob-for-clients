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


# ── Customers ────────────────────────────────────────────────────────────────

def get_all_customers() -> pd.DataFrame:
    sb = get_supabase()
    res = sb.table("customers").select("*").order("customer_name").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def get_customer_options() -> list:
    sb = get_supabase()
    res = sb.table("customers").select("customer_id, customer_name, city").order("customer_name").execute()
    return res.data if res.data else []

def add_customer(data: dict):
    sb = get_supabase()
    sb.table("customers").insert(data).execute()


# ── Sales Orders ─────────────────────────────────────────────────────────────

def get_so_summary() -> pd.DataFrame:
    sb = get_supabase()
    res = sb.table("v_so_summary").select("*").order("order_date", desc=True).execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def get_so_lines(so_id: int) -> pd.DataFrame:
    sb = get_supabase()
    res = (sb.table("so_lines")
             .select("*, items(name, item_code, unit)")
             .eq("so_id", so_id)
             .execute())
    if not res.data:
        return pd.DataFrame()
    df = pd.json_normalize(res.data)
    df.rename(columns={"items.name": "item_name", "items.item_code": "item_code",
                        "items.unit": "unit"}, inplace=True)
    return df

def create_so(customer_id: int, order_date: date, expected_date: date,
              notes: str, lines: list) -> str:
    sb = get_supabase()
    count_res = sb.table("sales_orders").select("id", count="exact").execute()
    so_num = f"SO-{(count_res.count or 0) + 1:04d}"
    total = sum(l["qty_ordered"] * l["unit_price"] for l in lines)
    so_res = sb.table("sales_orders").insert({
        "so_number": so_num,
        "customer_id": customer_id,
        "order_date": str(order_date),
        "expected_date": str(expected_date),
        "notes": notes,
        "status": "Open",
        "total_value": total
    }).execute()
    so_id = so_res.data[0]["id"]
    for line in lines:
        line["so_id"] = so_id
        sb.table("so_lines").insert(line).execute()
    return so_num


# ── Dispatch ─────────────────────────────────────────────────────────────────

def get_dispatch_summary() -> pd.DataFrame:
    sb = get_supabase()
    res = sb.table("v_dispatch_summary").select("*").order("dispatch_date", desc=True).execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def get_dispatch_lines(dn_id: int) -> pd.DataFrame:
    sb = get_supabase()
    res = (sb.table("dispatch_lines")
             .select("*, items(name, item_code, unit)")
             .eq("dn_id", dn_id)
             .execute())
    if not res.data:
        return pd.DataFrame()
    df = pd.json_normalize(res.data)
    df.rename(columns={"items.name": "item_name", "items.item_code": "item_code",
                        "items.unit": "unit"}, inplace=True)
    return df

def create_dispatch(so_id: int, customer_id: int, dispatch_date: date,
                    vehicle_no: str, driver_name: str, remarks: str,
                    lines: list) -> str:
    sb = get_supabase()
    count_res = sb.table("dispatch_notes").select("id", count="exact").execute()
    dn_num = f"DN-{(count_res.count or 0) + 1:04d}"

    dn_res = sb.table("dispatch_notes").insert({
        "dn_number": dn_num,
        "so_id": so_id,
        "customer_id": customer_id,
        "dispatch_date": str(dispatch_date),
        "vehicle_no": vehicle_no,
        "driver_name": driver_name,
        "remarks": remarks
    }).execute()
    dn_id = dn_res.data[0]["id"]

    all_fulfilled = True
    for line in lines:
        if line["qty_dispatched"] <= 0:
            continue
        sb.table("dispatch_lines").insert({
            "dn_id": dn_id,
            "so_line_id": line["so_line_id"],
            "item_id": line["item_id"],
            "qty_dispatched": line["qty_dispatched"]
        }).execute()
        # Update SO line dispatched qty
        so_line_res = sb.table("so_lines").select("qty_ordered, qty_dispatched").eq("id", line["so_line_id"]).execute()
        sl = so_line_res.data[0]
        new_dispatched = sl["qty_dispatched"] + line["qty_dispatched"]
        sb.table("so_lines").update({"qty_dispatched": new_dispatched}).eq("id", line["so_line_id"]).execute()
        if new_dispatched < sl["qty_ordered"]:
            all_fulfilled = False
        # Deduct from FG stock
        item_res = sb.table("items").select("current_stock").eq("id", line["item_id"]).execute()
        cur = item_res.data[0]["current_stock"]
        sb.table("items").update({"current_stock": cur - line["qty_dispatched"]}).eq("id", line["item_id"]).execute()
        # Log movement
        sb.table("stock_movements").insert({
            "item_id": line["item_id"],
            "movement_type": "Issue",
            "qty": -line["qty_dispatched"],
            "reference": dn_num,
            "remarks": f"Dispatched against {line.get('so_number', '')}",
            "movement_date": str(dispatch_date)
        }).execute()

    # Update SO status
    so_lines_res = sb.table("so_lines").select("qty_ordered, qty_dispatched").eq("so_id", so_id).execute()
    all_done = all(l["qty_dispatched"] >= l["qty_ordered"] for l in so_lines_res.data)
    any_done = any(l["qty_dispatched"] > 0 for l in so_lines_res.data)
    status = "Fulfilled" if all_done else ("Partial" if any_done else "Open")
    sb.table("sales_orders").update({"status": status}).eq("id", so_id).execute()

    return dn_num


# ── Dashboard KPIs update (sales added) ──────────────────────────────────────

def get_sales_kpis() -> dict:
    sb = get_supabase()
    so_res = sb.table("sales_orders").select("status, total_value").execute()
    sos = so_res.data or []
    open_so_count = sum(1 for s in sos if s["status"] in ("Open", "Partial"))
    open_so_value = sum(s["total_value"] for s in sos if s["status"] in ("Open", "Partial"))
    fulfilled_value = sum(s["total_value"] for s in sos if s["status"] == "Fulfilled")
    return {
        "open_so_count": open_so_count,
        "open_so_value": open_so_value,
        "fulfilled_value": fulfilled_value
    }


# ── Reports ───────────────────────────────────────────────────────────────────

def get_stock_valuation() -> pd.DataFrame:
    sb = get_supabase()
    res = sb.table("v_stock_alerts").select("*").order("category").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def get_dispatch_register(date_from: str = None, date_to: str = None,
                           customer_id: int = None) -> pd.DataFrame:
    sb = get_supabase()
    q = (sb.table("dispatch_notes")
           .select("*, sales_orders(so_number, total_value), customers(customer_name)")
           .order("dispatch_date", desc=True))
    if date_from:
        q = q.gte("dispatch_date", date_from)
    if date_to:
        q = q.lte("dispatch_date", date_to)
    if customer_id:
        q = q.eq("customer_id", customer_id)
    res = q.execute()
    if not res.data:
        return pd.DataFrame()
    df = pd.json_normalize(res.data)
    df.rename(columns={
        "sales_orders.so_number": "so_number",
        "customers.customer_name": "customer_name"
    }, inplace=True)

    # Get dispatch lines for each DN
    all_lines = []
    for _, row in df.iterrows():
        lines_res = (sb.table("dispatch_lines")
                       .select("*, items(name, item_code, unit)")
                       .eq("dn_id", row["id"])
                       .execute())
        for line in (lines_res.data or []):
            all_lines.append({
                "dn_number": row["dn_number"],
                "so_number": row.get("so_number", ""),
                "customer_name": row.get("customer_name", ""),
                "dispatch_date": row["dispatch_date"],
                "vehicle_no": row.get("vehicle_no", ""),
                "item_code": line.get("items", {}).get("item_code", ""),
                "item_name": line.get("items", {}).get("name", ""),
                "unit": line.get("items", {}).get("unit", ""),
                "qty_dispatched": line["qty_dispatched"]
            })
    return pd.DataFrame(all_lines) if all_lines else pd.DataFrame()

def get_pending_orders(order_type: str = "SO") -> pd.DataFrame:
    sb = get_supabase()
    if order_type == "SO":
        res = (sb.table("so_lines")
                 .select("*, sales_orders(so_number, order_date, expected_date, status, customers(customer_name)), items(name, item_code, unit)")
                 .execute())
        if not res.data:
            return pd.DataFrame()
        rows = []
        today = date.today()
        for r in res.data:
            so = r.get("sales_orders") or {}
            item = r.get("items") or {}
            if so.get("status") in ("Open", "Partial"):
                pending = r["qty_ordered"] - r["qty_dispatched"]
                if pending > 0:
                    order_date = so.get("order_date", "")
                    age = (today - date.fromisoformat(order_date)).days if order_date else 0
                    rows.append({
                        "so_number": so.get("so_number", ""),
                        "customer_name": (so.get("customers") or {}).get("customer_name", ""),
                        "order_date": order_date,
                        "expected_date": so.get("expected_date", ""),
                        "item_code": item.get("item_code", ""),
                        "item_name": item.get("name", ""),
                        "unit": item.get("unit", ""),
                        "qty_ordered": r["qty_ordered"],
                        "qty_dispatched": r["qty_dispatched"],
                        "qty_pending": pending,
                        "pending_value": pending * r["unit_price"],
                        "age_days": age,
                        "status": so.get("status", "")
                    })
        return pd.DataFrame(rows)
    else:  # PO
        res = (sb.table("po_lines")
                 .select("*, purchase_orders(po_number, order_date, expected_date, status, suppliers(name)), items(name, item_code, unit)")
                 .execute())
        if not res.data:
            return pd.DataFrame()
        rows = []
        today = date.today()
        for r in res.data:
            po = r.get("purchase_orders") or {}
            item = r.get("items") or {}
            if po.get("status") in ("Ordered", "Partial"):
                pending = r["qty_ordered"] - r["qty_received"]
                if pending > 0:
                    order_date = po.get("order_date", "")
                    age = (today - date.fromisoformat(order_date)).days if order_date else 0
                    rows.append({
                        "po_number": po.get("po_number", ""),
                        "supplier_name": (po.get("suppliers") or {}).get("name", ""),
                        "order_date": order_date,
                        "expected_date": po.get("expected_date", ""),
                        "item_code": item.get("item_code", ""),
                        "item_name": item.get("name", ""),
                        "unit": item.get("unit", ""),
                        "qty_ordered": r["qty_ordered"],
                        "qty_received": r["qty_received"],
                        "qty_pending": pending,
                        "age_days": age,
                        "status": po.get("status", "")
                    })
        return pd.DataFrame(rows)

def get_production_summary() -> pd.DataFrame:
    sb = get_supabase()
    res = (sb.table("production_orders")
             .select("*, items(name, item_code)")
             .order("created_at", desc=True)
             .execute())
    if not res.data:
        return pd.DataFrame()

    rows = []
    for r in res.data:
        item = r.get("items") or {}
        cons_res = (sb.table("production_consumption")
                      .select("qty_planned, qty_actual, wastage")
                      .eq("production_order_id", r["id"])
                      .execute())
        cons = cons_res.data or []
        total_planned = sum(c["qty_planned"] for c in cons)
        total_actual = sum(c["qty_actual"] for c in cons)
        total_wastage = sum(c["wastage"] for c in cons)
        wastage_pct = round((total_wastage / total_actual * 100), 1) if total_actual > 0 else 0
        efficiency = round((r["qty_produced"] / r["qty_planned"] * 100), 1) if r["qty_planned"] > 0 else 0
        rows.append({
            "order_number": r["order_number"],
            "product_code": item.get("item_code", ""),
            "product_name": item.get("name", ""),
            "qty_planned": r["qty_planned"],
            "qty_produced": r["qty_produced"],
            "efficiency_%": efficiency,
            "material_planned": total_planned,
            "material_actual": total_actual,
            "wastage": total_wastage,
            "wastage_%": wastage_pct,
            "status": r["status"],
            "start_date": r.get("start_date", ""),
            "end_date": r.get("end_date", "")
        })
    return pd.DataFrame(rows)


# ── Production Wastage ────────────────────────────────────────────────────────

def record_production_wastage(production_order_id: int, item_id: int,
                               wastage_qty: float, reason: str, order_number: str):
    """Record mid-production wastage — deducts stock and updates consumption record"""
    sb = get_supabase()

    # Check if consumption line exists for this item in this order
    cons_res = (sb.table("production_consumption")
                  .select("id, wastage, qty_actual")
                  .eq("production_order_id", production_order_id)
                  .eq("item_id", item_id)
                  .execute())

    if cons_res.data:
        # Update existing consumption line wastage
        cons = cons_res.data[0]
        new_wastage = cons["wastage"] + wastage_qty
        sb.table("production_consumption").update(
            {"wastage": new_wastage}
        ).eq("id", cons["id"]).execute()
    else:
        # Create a new consumption line for wastage only
        sb.table("production_consumption").insert({
            "production_order_id": production_order_id,
            "item_id": item_id,
            "qty_planned": 0,
            "qty_actual": 0,
            "wastage": wastage_qty
        }).execute()

    # Deduct from stock
    item_res = sb.table("items").select("current_stock").eq("id", item_id).execute()
    cur = item_res.data[0]["current_stock"]
    sb.table("items").update({"current_stock": cur - wastage_qty}).eq("id", item_id).execute()

    # Log stock movement
    sb.table("stock_movements").insert({
        "item_id": item_id,
        "movement_type": "Wastage",
        "qty": -wastage_qty,
        "reference": order_number,
        "remarks": f"Production wastage: {reason}",
        "movement_date": str(date.today())
    }).execute()
