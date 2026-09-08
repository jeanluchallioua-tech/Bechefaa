"""Phase 1 / Phase 3.3 — impression 80 mm BÉCHÉFAA."""
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
    })
    return payload


def _base_css():
    return r'''<style>
@page{size:80mm auto;margin:3mm}*{box-sizing:border-box}html,body{margin:0;padding:0;background:#fff;color:#000;font-family:Arial,sans-serif}
.ticket80{width:74mm;margin:0 auto;font-size:12px;line-height:1.3}.center{text-align:center}.brand{font-size:22px;font-weight:900}.sep{border-top:1px dashed #000;margin:7px 0}.row{display:flex;justify-content:space-between;gap:8px}.actions{margin:12px auto;width:74mm;display:flex;gap:8px}.actions button{flex:1;padding:10px;border:0;border-radius:6px;background:#111827;color:#fff;font-weight:800;cursor:pointer}@media print{.actions{display:none!important}.ticket80{width:74mm}}
</style>'''


def _option_lines(item):
    options = item.get("options") or []
    lines, last_group = [], None
    for option in options:
        if isinstance(option, dict):
            group = str(option.get("group") or "").strip(); label = str(option.get("name") or option.get("label") or "").strip()
            if not label: continue
            if group and group == last_group: lines.append(f'<div class="kopt kcontinuation">{escape(label)}</div>')
            elif group: lines.append(f'<div class="kopt"><span class="kgroup">{escape(group)} :</span> {escape(label)}</div>')
            else: lines.append(f'<div class="kopt">{escape(label)}</div>')
            last_group = group or None
        elif option is not None:
            lines.append(f'<div class="kopt">{escape(str(option))}</div>'); last_group = None
    if lines: return "".join(lines)
    text = str(item.get("options_text") or "").strip()
    if not text: return ""
    rendered, last_group = [], None
    for part in [p.strip() for p in text.split(" • ") if p.strip()]:
        if ":" in part:
            group, value = [x.strip() for x in part.split(":", 1)]
            if group == last_group: rendered.append(f'<div class="kopt kcontinuation">{escape(value)}</div>')
            else: rendered.append(f'<div class="kopt"><span class="kgroup">{escape(group)} :</span> {escape(value)}</div>')
            last_group = group
        else:
            rendered.append(f'<div class="kopt">{escape(part)}</div>'); last_group = None
    return "".join(rendered)


def register_printing_phase1(app, db, ensure_order_schema, order_payload):
    @app.get("/impression/client/<order_id>")
    def print_client(order_id):
        try:
            with db() as conn: order = _load_order(conn, ensure_order_schema, order_payload, order_id)
            if not order: return "Commande introuvable", 404
        except Exception as exc: return f"Impression indisponible : {escape(str(exc))}", 500
        mode = order["ticket_type"]
        mode_title = "COMPTOIR / EMPORTER" if mode == "Comptoir" else mode.upper()
        parts = []
        if order.get("customer_name"): parts.append(escape(str(order["customer_name"])))
        if order.get("phone"): parts.append(escape(str(order["phone"])))
        if order.get("email"): parts.append(escape(str(order["email"])))
        if mode == "Livraison":
            address = " ".join(x for x in [order.get("address"), order.get("postal_code"), order.get("city")] if x)
            if address: parts.append(escape(address))
        client_block = '<div class="cclient">' + "<br>".join(parts) + '</div>' if parts else '<div class="cclient">Client comptoir</div>'
        items = order.get("items") or []
        piece_count = sum(int(i.get("qty") or 0) for i in items)
        items_html = "".join(f'''<div class="citem"><div class="cline"><span class="cname">{escape(str(i.get("qty",1)))}×&nbsp;&nbsp;{escape(str(i.get("name") or ""))}</span><span class="cprice">{_money(float(i.get("unit_price") or 0)*float(i.get("qty") or 1))}</span></div>{_option_lines(i)}</div>''' for i in items)
        try: rate_text = f"{float(order.get('tax_rate') or 10):g}".replace(".", ",")
        except Exception: rate_text = "10"
        auto = request.args.get("auto") == "1"
        html = f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Ticket #{escape(str(order['num']))}</title>{_base_css()}<style>
.ctitle{{font-size:25px;font-weight:900;text-align:center}}.cmode{{text-align:center;font-size:16px;font-weight:900;margin:5px 0}}.cnum{{text-align:center;font-size:28px;font-weight:900;margin:6px 0}}.cclient{{text-align:center;font-size:14px;font-weight:900;margin:5px 0}}.citem{{padding:5px 0}}.cline{{display:flex;justify-content:space-between;gap:5px}}.cname{{font-size:14px;font-weight:900}}.cprice{{font-size:13px;font-weight:800;white-space:nowrap}}.kopt{{font-size:12px;line-height:1.2;margin-top:2px;padding-left:10mm}}.kcontinuation{{padding-left:16mm}}.kgroup{{font-weight:900}}.cpieces{{font-weight:900;margin:4px 0}}.cfiscal{{font-size:13px;font-weight:700;padding:1px 0}}.ctotal{{font-size:20px;font-weight:900}}.thanks{{font-size:12px;font-weight:800;text-align:center;margin-top:8px}}
</style></head><body><div class="ticket80"><div class="ctitle">BÉCHÉFAA</div><div class="sep"></div><div class="cmode">{escape(mode_title)}</div><div class="cnum">N° {escape(str(order['num']))}</div>{client_block}<div class="sep"></div>{items_html}<div class="sep"></div><div class="cpieces">Nombre de pièces : {piece_count}</div><div class="sep"></div><div class="row cfiscal"><span>Total HT</span><span>{_money(order.get('total_ht'))}</span></div><div class="row cfiscal"><span>TVA {escape(rate_text)} %</span><span>{_money(order.get('tax_amount'))}</span></div><div class="row ctotal"><span>TOTAL TTC</span><span>{_money(order.get('total_ttc'))}</span></div><div class="row cfiscal"><span>Paiement</span><span>{escape(str(order.get('payment') or 'À ENCAISSER'))}</span></div><div class="sep"></div><div class="thanks">Merci</div></div><div class="actions"><button onclick="window.print()">Imprimer</button><button onclick="window.close()">Fermer</button></div>{'<script>window.addEventListener("load",()=>setTimeout(()=>window.print(),150));</script>' if auto else ''}</body></html>'''
        return Response(html, content_type="text/html; charset=utf-8")

    @app.get("/impression/cuisine/<order_id>")
    def print_kitchen(order_id):
        try:
            with db() as conn: order = _load_order(conn, ensure_order_schema, order_payload, order_id)
            if not order: return "Commande introuvable", 404
        except Exception as exc: return f"Impression indisponible : {escape(str(exc))}", 500
        mode = order["ticket_type"]; mode_title = "COMPTOIR / EMPORTER" if mode == "Comptoir" else mode.upper()
        client_name = escape(str(order.get("customer_name") or "Client comptoir"))
        items_html = "".join(f'''<div class="kitem"><div class="kline"><span class="kname"><span class="kqty">{escape(str(i.get("qty",1)))}×</span>&nbsp;&nbsp;{escape(str(i.get("name") or ""))}</span><span class="kprice">{_money(float(i.get("unit_price") or 0)*float(i.get("qty") or 1))}</span></div>{_option_lines(i)}</div>''' for i in order.get("items") or [])
        auto = request.args.get("auto") == "1"
        html = f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Cuisine #{escape(str(order['num']))}</title>{_base_css()}<style>
.ticket80{{width:72mm}}.ktitle{{font-size:25px;font-weight:900;text-align:center}}.ksolid{{border-top:1.5px solid #000;margin:5px 0 6px}}.kmode{{text-align:center;font-size:17px;font-weight:900}}.knum{{text-align:center;font-size:28px;font-weight:900;margin:7px 0 5px}}.kclient{{font-size:19px;font-weight:900;margin:5px 0 3px}}.kdots{{border-top:1px dotted #000;margin:4px 0 8px}}.kitem{{padding:2px 0 9px}}.kline{{display:flex;justify-content:space-between;gap:5px}}.kname{{font-size:16px;font-weight:900;max-width:54mm}}.kqty{{font-size:16px;font-weight:900}}.kprice{{font-size:15px;font-weight:900;white-space:nowrap}}.kopt{{font-size:13px;line-height:1.18;margin-top:2px;padding-left:12mm}}.kcontinuation{{padding-left:18mm}}.kgroup{{font-weight:900}}.ktotal{{display:flex;justify-content:space-between;font-size:24px;font-weight:900;margin-top:6px;padding-top:6px;border-top:2px solid #000}}
</style></head><body><div class="ticket80"><div class="ktitle">BÉCHÉFAA</div><div class="ksolid"></div><div class="kmode">{escape(mode_title)}</div><div class="ksolid"></div><div class="knum">N° {escape(str(order['num']))}</div><div class="kclient">{client_name}</div><div class="kdots"></div>{items_html or '<div class="center">Aucun article</div>'}<div class="ktotal"><span>TOTAL</span><span>{_money(order.get('total_ttc'))}</span></div></div><div class="actions"><button onclick="window.print()">Imprimer</button><button onclick="window.close()">Fermer</button></div>{'<script>window.addEventListener("load",()=>setTimeout(()=>window.print(),150));</script>' if auto else ''}</body></html>'''
        return Response(html, content_type="text/html; charset=utf-8")

    @app.after_request
    def inject_print_buttons(response):
        if request.path != "/pos" or response.status_code != 200 or response.mimetype != "text/html": return response
        html = response.get_data(as_text=True)
        addon = r'''<style>.print-actions{display:flex;gap:8px;margin-top:8px}.print-actions a{flex:1;text-align:center;text-decoration:none;border-radius:8px;padding:10px 8px;font-weight:800;font-size:12px}.print-client{background:#2563eb;color:white}.print-kitchen{background:#d97706;color:white}</style><script>
(function(){function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}ready(function(){let lastOrderId=null;const nativeFetch=window.fetch.bind(window);window.fetch=async function(input,init){const url=typeof input==='string'?input:(input&&input.url)||'';const res=await nativeFetch(input,init);try{const method=String((init&&init.method)||'GET').toUpperCase();if((url==='/api/orders'&&method==='POST')||(url.includes('/send-kitchen')&&method==='POST')){const clone=res.clone(),data=await clone.json();if(data&&data.ok!==false&&data.id)lastOrderId=data.id;setTimeout(addButtons,80)}}catch(e){}return res};function addButtons(){if(!lastOrderId)return;const msg=document.getElementById('order-message');if(!msg||msg.querySelector('.print-actions'))return;const wrap=document.createElement('div');wrap.className='print-actions';wrap.innerHTML='<a class="print-client" target="_blank" href="/impression/client/'+encodeURIComponent(lastOrderId)+'">Ticket client 80 mm</a><a class="print-kitchen" target="_blank" href="/impression/cuisine/'+encodeURIComponent(lastOrderId)+'">Ticket cuisine 80 mm</a>';msg.appendChild(wrap)}const msg=document.getElementById('order-message');if(msg)new MutationObserver(()=>setTimeout(addButtons,50)).observe(msg,{childList:true,subtree:true})})})();</script>'''
        html = html.replace("</body>", addon + "</body>"); response.set_data(html); response.content_length = len(response.get_data()); return response
