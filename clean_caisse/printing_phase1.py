"""Phase 1 / Phase 3.3 — impression 80 mm BÉCHÉFAA."""
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal, ROUND_HALF_UP
from html import escape
from flask import Response, request


def _ticket_type(source):
    value = str(source or "").upper()
    if value == "SALLE": return "Salle"
    if value in {"EMPORTER", "TAKEAWAY"}: return "Emporter"
    if value in {"LIVRAISON", "DELIVERY"}: return "Livraison"
    return "Comptoir"


def _channel(source):
    value = str(source or "").upper()
    if "UBER" in value: return "UBER EATS"
    if "DELIVEROO" in value: return "DELIVEROO"
    if "WIX" in value or "SITE" in value or "WEB" in value: return "SITE INTERNET"
    return "CAISSE"


def _money(value):
    try: return f"{float(value):.2f}".replace(".", ",") + " €"
    except Exception: return "0,00 €"


def _fallback_tax(total):
    try: ttc = Decimal(str(total or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception: ttc = Decimal("0.00")
    ht = (ttc / Decimal("1.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return ht, (ttc - ht).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ttc


def _load_order(conn, ensure_order_schema, order_payload, order_id):
    ensure_order_schema(conn)
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS total_ttc NUMERIC(12,2)")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS total_ht NUMERIC(12,2)")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS tax_rate NUMERIC(6,3)")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS tax_amount NUMERIC(12,2)")
    conn.commit()
    row = conn.execute("""SELECT id, num, customer_name, phone, email, address, postal_code, city,
        source, payment, status, total, total_ttc, total_ht, tax_rate, tax_amount, created_at, updated_at
        FROM caisse_orders WHERE id=%s""", (order_id,)).fetchone()
    if not row: return None
    payload = order_payload(conn, row)
    fallback_ht, fallback_tax, fallback_ttc = _fallback_tax(row.get("total"))
    payload.update({
        "phone": row.get("phone") or "", "email": row.get("email") or "",
        "address": row.get("address") or "", "postal_code": row.get("postal_code") or "", "city": row.get("city") or "",
        "ticket_type": _ticket_type(row.get("source")), "channel": _channel(row.get("source")),
        "total_ttc": row.get("total_ttc") if row.get("total_ttc") is not None else fallback_ttc,
        "total_ht": row.get("total_ht") if row.get("total_ht") is not None else fallback_ht,
        "tax_rate": row.get("tax_rate") if row.get("tax_rate") is not None else Decimal("10.0"),
        "tax_amount": row.get("tax_amount") if row.get("tax_amount") is not None else fallback_tax,
        "created_at": row.get("created_at"),
    })
    return payload


def _format_order_datetime(value):
    try:
        if value in (None, ""):
            return ""
        raw = float(value)
        if raw > 100000000000:
            raw /= 1000.0
        dt = datetime.fromtimestamp(raw, tz=timezone.utc).astimezone(ZoneInfo("Europe/Paris"))
        return dt.strftime("%d/%m/%Y à %H:%M")
    except Exception:
        return ""


def _base_css():
    return r'''<style>
@page{size:80mm auto;margin:3mm}*{box-sizing:border-box}html,body{margin:0;padding:0;background:#fff;color:#000;font-family:Arial,sans-serif}
.ticket80{width:74mm;margin:0 auto;font-size:12px;line-height:1.3}.center{text-align:center}.brand{font-size:22px;font-weight:900}.sep{border-top:1px dashed #000;margin:7px 0}.row{display:flex;justify-content:space-between;gap:8px}.actions{margin:12px auto;width:74mm;display:flex;gap:8px}.actions button{flex:1;padding:10px;border:0;border-radius:6px;background:#111827;color:#fff;font-weight:800;cursor:pointer}@media print{.actions{display:none!important}.ticket80{width:74mm}}
</style>'''


def _option_lines(item):
    # This renderer is used only by printed ticket pages, never the kitchen screen.
    from .epson_epos_network_phase6 import _option_text
    text = _option_text(item)
    return '<div class="kopt">' + escape(text) + '</div>' if text else ''


def register_printing_phase1(app, db, ensure_order_schema, order_payload):
    def paper_page(kind, order_id):
        from urllib.parse import quote
        preview = request.args.get("preview") == "1"
        auto = request.args.get("auto") == "1" and not preview
        url = "/apercu/image-ticket/" + kind + "/" + quote(str(order_id), safe="")
        action = '<div class="actions"><button onclick="window.print()">Imprimer</button></div>' if not preview else ''
        script = '<script>document.getElementById("paper").addEventListener("load",()=>window.print());</script>' if auto else ''
        return Response(f'<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Ticket</title>{_base_css()}<style>#paper{{width:72mm;height:auto;display:block;margin:auto}}</style></head><body><img id="paper" alt="Ticket" src="{url}">{action}{script}</body></html>', content_type="text/html; charset=utf-8")

    @app.get("/impression/client/<order_id>")
    def print_client(order_id):
        return paper_page("client", order_id)

    @app.get("/impression/cuisine/<order_id>")
    def print_kitchen(order_id):
        return paper_page("kitchen", order_id)

    @app.after_request
    def inject_print_buttons(response):
        # Réimpression manuelle uniquement depuis l'Historique.
        # Sur /pos, Envoyer en cuisine imprime automatiquement cuisine + client.
        if request.path == "/pos":
            return response
        if response.status_code != 200 or response.mimetype != "text/html": return response
        html = response.get_data(as_text=True)
        addon = r'''<style>.print-actions{display:flex;gap:8px;margin-top:8px}.print-actions a,.print-actions button{flex:1;text-align:center;text-decoration:none;border:0;border-radius:8px;padding:10px 8px;font-weight:800;font-size:12px;cursor:pointer}.print-client{background:#2563eb;color:white}.print-kitchen{background:#d97706;color:white}</style><script>
(function(){function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}ready(function(){let lastOrderId=null;const nativeFetch=window.fetch.bind(window);window.fetch=async function(input,init){const url=typeof input==='string'?input:(input&&input.url)||'';const res=await nativeFetch(input,init);try{const method=String((init&&init.method)||'GET').toUpperCase();if((url==='/api/orders'&&method==='POST')||(url.includes('/send-kitchen')&&method==='POST')){const clone=res.clone(),data=await clone.json();if(data&&data.ok!==false&&data.id)lastOrderId=data.id;setTimeout(addButtons,80)}}catch(e){}return res};function addButtons(){if(!lastOrderId)return;const msg=document.getElementById('order-message');if(!msg||msg.querySelector('.print-actions'))return;const wrap=document.createElement('div');wrap.className='print-actions';wrap.innerHTML='<button type="button" class="print-client" data-print-client>Ticket client</button><button type="button" class="print-kitchen" data-print-kitchen>Ticket cuisine</button>';wrap.querySelector('[data-print-client]').onclick=function(){if(typeof window.bechefaaPrintClient==='function')window.bechefaaPrintClient(lastOrderId);else window.location.href='/impression/client/'+encodeURIComponent(lastOrderId)};wrap.querySelector('[data-print-kitchen]').onclick=function(){if(typeof window.bechefaaPrintKitchen==='function')window.bechefaaPrintKitchen(lastOrderId);else window.location.href='/impression/cuisine/'+encodeURIComponent(lastOrderId)};msg.appendChild(wrap)}const msg=document.getElementById('order-message');if(msg)new MutationObserver(()=>setTimeout(addButtons,50)).observe(msg,{childList:true,subtree:true})})})();</script>'''
        html = html.replace("</body>", addon + "</body>"); response.set_data(html); response.content_length = len(response.get_data()); return response