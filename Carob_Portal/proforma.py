"""
proforma.py — Proforma invoice generator for Carob Order Portal
Generates a downloadable HTML proforma invoice
"""
from datetime import date, timedelta

def generate_proforma_html(order: dict, lines) -> str:
    today = date.today()
    valid_until = today + timedelta(days=15)
    proforma_num = f"PI/{today.strftime('%Y%m')}/{order.get('order_number','').replace('DPI-','')}"

    # Build line items table rows
    rows_html = ""
    subtotal = 0
    for i, (_, row) in enumerate(lines.iterrows() if hasattr(lines, 'iterrows') else enumerate(lines)):
        lt = float(row.get("line_total", 0))
        subtotal += lt
        disc = float(row.get("discount_pct", 0))
        disc_str = f"{disc:.0f}%" if disc > 0 else "—"
        rows_html += f"""
        <tr>
            <td style="padding:10px 12px;border-bottom:1px solid #F0EDE8;">{i+1}</td>
            <td style="padding:10px 12px;border-bottom:1px solid #F0EDE8;">
                <div style="font-weight:600;color:#0A0A0F;">{row.get('product_name','')}</div>
                <div style="font-size:11px;color:#8A8A9A;">{row.get('product_code','')}</div>
            </td>
            <td style="padding:10px 12px;border-bottom:1px solid #F0EDE8;text-align:center;">{row.get('unit','Ltr')}</td>
            <td style="padding:10px 12px;border-bottom:1px solid #F0EDE8;text-align:right;">{float(row.get('qty',0)):,.1f}</td>
            <td style="padding:10px 12px;border-bottom:1px solid #F0EDE8;text-align:center;">{disc_str}</td>
            <td style="padding:10px 12px;border-bottom:1px solid #F0EDE8;text-align:right;">₹{float(row.get('unit_price',0)):,.2f}</td>
            <td style="padding:10px 12px;border-bottom:1px solid #F0EDE8;text-align:right;font-weight:600;">₹{lt:,.2f}</td>
        </tr>"""

    gst_rate = 18
    gst_amount = subtotal * gst_rate / 100
    grand_total = subtotal + gst_amount

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Proforma Invoice — {proforma_num}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=DM+Sans:wght@300;400;500;600&display=swap');
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'DM Sans', sans-serif; background: #F5F3EF; padding: 32px; color: #1C1C2E; }}
  .page {{ max-width: 860px; margin: 0 auto; background: #fff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 32px rgba(0,0,0,0.08); }}
  .header {{ background: #0A0A0F; padding: 36px 40px; display: flex; justify-content: space-between; align-items: flex-start; }}
  .brand {{ font-family: 'Playfair Display', serif; font-size: 28px; font-weight: 900; color: #C9A84C; }}
  .brand-sub {{ font-size: 10px; color: rgba(255,255,255,0.3); letter-spacing: 2px; text-transform: uppercase; margin-top: 4px; }}
  .pi-label {{ text-align: right; }}
  .pi-title {{ font-family: 'Playfair Display', serif; font-size: 22px; color: #C9A84C; font-weight: 700; }}
  .pi-num {{ font-size: 13px; color: rgba(255,255,255,0.6); margin-top: 4px; }}
  .pi-date {{ font-size: 11px; color: rgba(255,255,255,0.35); margin-top: 2px; }}
  .meta {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0; border-bottom: 1px solid #F0EDE8; }}
  .meta-box {{ padding: 20px 24px; border-right: 1px solid #F0EDE8; }}
  .meta-box:last-child {{ border-right: none; }}
  .meta-lbl {{ font-size: 9px; font-weight: 600; color: #8A8A9A; letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 6px; }}
  .meta-val {{ font-size: 13px; font-weight: 600; color: #0A0A0F; line-height: 1.5; }}
  .meta-sub {{ font-size: 11px; color: #8A8A9A; margin-top: 2px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  thead {{ background: #F8F6F0; }}
  thead th {{ padding: 10px 12px; font-size: 10px; font-weight: 600; color: #8A8A9A; text-transform: uppercase; letter-spacing: 0.8px; text-align: left; }}
  thead th:not(:first-child):not(:nth-child(2)) {{ text-align: center; }}
  thead th:last-child, thead th:nth-last-child(2) {{ text-align: right; }}
  .totals {{ padding: 20px 24px; display: flex; justify-content: flex-end; border-top: 1px solid #F0EDE8; }}
  .totals-box {{ width: 280px; }}
  .tot-row {{ display: flex; justify-content: space-between; padding: 5px 0; font-size: 13px; color: #555; }}
  .tot-row.grand {{ border-top: 2px solid #0A0A0F; margin-top: 8px; padding-top: 10px; font-weight: 700; font-size: 15px; color: #0A0A0F; }}
  .footer-band {{ background: #0A0A0F; padding: 16px 40px; display: flex; justify-content: space-between; align-items: center; }}
  .footer-note {{ font-size: 11px; color: rgba(255,255,255,0.35); }}
  .footer-valid {{ font-size: 11px; color: #C9A84C; font-weight: 500; }}
  .terms {{ padding: 20px 24px; background: #FAFAF8; border-top: 1px solid #F0EDE8; }}
  .terms-title {{ font-size: 10px; font-weight: 700; color: #8A8A9A; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }}
  .terms-list {{ font-size: 11px; color: #666; line-height: 1.8; }}
  @media print {{ body {{ padding: 0; background: #fff; }} .page {{ box-shadow: none; border-radius: 0; }} }}
</style>
</head>
<body>
<div class="page">

  <!-- HEADER -->
  <div class="header">
    <div>
      <div class="brand">Carob Order Portal</div>
      <div class="brand-sub">Powered by Carob Technologies</div>
    </div>
    <div class="pi-label">
      <div class="pi-title">Proforma Invoice</div>
      <div class="pi-num">{proforma_num}</div>
      <div class="pi-date">Date: {today.strftime('%d %b %Y')} &nbsp;·&nbsp; Valid till: {valid_until.strftime('%d %b %Y')}</div>
    </div>
  </div>

  <!-- META -->
  <div class="meta">
    <div class="meta-box">
      <div class="meta-lbl">Bill To</div>
      <div class="meta-val">{order.get('company_name','')}</div>
      <div class="meta-sub">{order.get('contact_person','')}</div>
      <div class="meta-sub">GSTIN: {order.get('gstin','—')}</div>
    </div>
    <div class="meta-box">
      <div class="meta-lbl">Deliver To</div>
      <div class="meta-val" style="font-size:12px;">{order.get('delivery_address','')}</div>
    </div>
    <div class="meta-box">
      <div class="meta-lbl">Order Reference</div>
      <div class="meta-val">{order.get('order_number','')}</div>
      <div class="meta-sub">SO: {order.get('so_number','Pending')}</div>
      <div class="meta-sub">Approved: {str(order.get('approved_at',''))[:10] or today.strftime('%d %b %Y')}</div>
    </div>
  </div>

  <!-- LINE ITEMS -->
  <table>
    <thead>
      <tr>
        <th style="width:40px;">#</th>
        <th>Product</th>
        <th style="width:60px;text-align:center;">Unit</th>
        <th style="width:70px;text-align:right;">Qty</th>
        <th style="width:70px;text-align:center;">Disc.</th>
        <th style="width:100px;text-align:right;">Rate</th>
        <th style="width:110px;text-align:right;">Amount</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>

  <!-- TOTALS -->
  <div class="totals">
    <div class="totals-box">
      <div class="tot-row"><span>Subtotal</span><span>₹{subtotal:,.2f}</span></div>
      <div class="tot-row"><span>GST @ {gst_rate}%</span><span>₹{gst_amount:,.2f}</span></div>
      <div class="tot-row grand"><span>Total</span><span>₹{grand_total:,.2f}</span></div>
    </div>
  </div>

  <!-- TERMS -->
  <div class="terms">
    <div class="terms-title">Terms & Conditions</div>
    <div class="terms-list">
      1. This is a proforma invoice. Goods will be dispatched upon receipt of payment or confirmed credit approval.<br>
      2. Prices are valid for 15 days from the date of this proforma.<br>
      3. GST @ 18% is applicable on all items as indicated above.<br>
      4. Delivery timelines are subject to stock availability at time of order confirmation.
    </div>
  </div>

  <!-- FOOTER -->
  <div class="footer-band">
    <div class="footer-note">Carob Technologies · carob.in · This is a computer-generated document.</div>
    <div class="footer-valid">Valid until {valid_until.strftime('%d %b %Y')}</div>
  </div>

</div>
</body>
</html>"""
    return html
