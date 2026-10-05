"""Phase 6 — impression Epson ePOS-Print sur TM-m30II réseau.

Le navigateur de la tablette envoie directement le XML ePOS à l'imprimante locale.
Clever Cloud ne tente jamais d'accéder au LAN du restaurant.

Configuration actuelle restaurant:
- Epson TM-m30II
- IP 192.168.250.175
- ePOS-Print activé
- Device ID local_printer
"""
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape
from urllib.parse import quote

from flask import Response, jsonify, request


DEFAULT_HOST = "192.168.10.112"
DEFAULT_DEVICE_ID = "local_printer"


def _line(text=""):
    return '<text>' + escape(str(text or "")) + '</text><feed line="1"/>'


def _money(value):
    try:
        return f"{Decimal(str(value or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}".replace(".", ",") + " EUR"
    except Exception:
        return "0,00 EUR"


def _tax_values(order):
    total = Decimal(str(order.get("total_ttc") if order.get("total_ttc") is not None else order.get("total") or 0)).quantize(Decimal("0.01"))
    rate = Decimal(str(order.get("tax_rate") if order.get("tax_rate") is not None else 10))
    if order.get("total_ht") is not None and order.get("tax_amount") is not None:
        ht = Decimal(str(order.get("total_ht"))).quantize(Decimal("0.01"))
        tax = Decimal(str(order.get("tax_amount"))).quantize(Decimal("0.01"))
    else:
        divisor = Decimal("1") + (rate / Decimal("100"))
        ht = (total / divisor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        tax = (total - ht).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return ht, tax, total, rate


def _service_label(order):
    if order.get("table_number") or str(order.get("service_mode") or "").upper()=="SALLE":
        return "SUR PLACE"
    source = str(order.get("source") or "").upper()
    if source in {"LIVRAISON", "DELIVERY"}:
        return "LIVRAISON"
    return "A EMPORTER"


def _option_text(item):
    text = str(item.get("options_text") or "").strip()
    if text:
        return text.replace(";;", " | ").replace("::", ": ")
    values = []
    for option in item.get("options") or []:
        if isinstance(option, dict):
            group = str(option.get("group") or "").strip()
            label = str(option.get("name") or option.get("label") or "").strip()
            if label:
                values.append((group + ": " if group else "") + label)
        elif option is not None:
            values.append(str(option))
    return " | ".join(values)


def _identity_lines(identity):
    identity = identity or {}
    lines = []
    address = str(identity.get("address") or "").strip()
    postal = str(identity.get("postal_code") or "").strip()
    city = str(identity.get("city") or "").strip()
    for suffix in (", France", " France"):
        if address.lower().endswith(suffix.lower()):
            address = address[:-len(suffix)].rstrip(" ,")
    if city.lower() == "france":
        city = ""
    if address:
        lines.append(address)
    locality = " ".join(x for x in (postal, city) if x)
    if locality:
        lines.append(locality)
    phone = str(identity.get("phone") or "").strip()
    if phone:
        lines.append("Tel. " + phone)
    return [line for line in lines if str(line).strip().lower() != "france"]


def _kitchen_xml(order):
    mode = _service_label(order)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<epos-print xmlns="http://www.epson-pos.com/schemas/2011/03/epos-print">',
        '<text align="center" font="font_a" width="2" height="2"/>',
        _line("BECHEFAA"),
        '<text width="1" height="1"/>',
        _line("--------------------------------"),
        '<text width="2" height="2" emphasized="true"/>',
        _line(mode),
        '<text width="1" height="1"/>',
    ]
    if order.get("table_number"):
        parts.append('<text width="2" height="1" emphasized="true"/>')
        parts.append(_line("TABLE " + str(order.get("table_number"))))
        parts.append('<text width="1" height="1"/>')
    parts.append('<text width="1" height="1"/>')
    customer = str(order.get("customer_name") or "").strip()
    if customer and customer.lower() not in {"client comptoir", "client livraison"}:
        parts.append(_line(customer))
    parts.append(_line("--------------------------------"))
    parts.append('<text align="left"/>')

    for item in order.get("items") or []:
        qty = item.get("qty") or 1
        name = str(item.get("name") or "")
        parts.append('<text align="left" width="2" height="1" emphasized="true"/>')
        parts.append(_line(f"{qty} x {name}"))
        parts.append('<text align="left" width="1" height="1" emphasized="false"/>')
        opts = _option_text(item)
        if opts:
            for chunk in [x.strip() for x in opts.replace(" • ", "|").split("|") if x.strip()]:
                parts.append(_line("  - " + chunk))
        parts.append('<feed line="1"/>')

    parts.extend([
        '<text align="left" width="1" height="1"/>',
        _line("--------------------------------"),
        '<feed line="3"/>',
        '<cut type="feed"/>',
        '</epos-print>',
    ])
    return "".join(parts)


def _client_xml(order, identity=None):
    ht, tax, total, rate = _tax_values(order)
    identity = identity or {}
    brand = str(identity.get("name") or "BECHEFAA").strip() or "BECHEFAA"
    mode = _service_label(order)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<epos-print xmlns="http://www.epson-pos.com/schemas/2011/03/epos-print">',
        '<text align="center" font="font_a" width="2" height="2" emphasized="true"/>',
        _line(brand),
        '<text width="1" height="1" emphasized="false"/>',
    ]
    for line in _identity_lines(identity):
        parts.append(_line(line))
    parts.extend([
        _line("--------------------------------"),
        '<text width="2" height="1" emphasized="true"/>',
        _line(mode),
        '<text width="1" height="1" emphasized="false"/>',
    ])
    if order.get("table_number"):
        parts.append(_line("Table " + str(order.get("table_number"))))

    customer = str(order.get("customer_name") or "").strip()
    if customer and customer.lower() not in {"client comptoir", "client livraison"}:
        parts.append(_line(customer))
    if mode == "LIVRAISON":
        phone = str(order.get("phone") or "").strip()
        address = str(order.get("address") or "").strip()
        postal = str(order.get("postal_code") or "").strip()
        city = str(order.get("city") or "").strip()
        if phone:
            parts.append(_line(phone))
        if address:
            parts.append(_line(address))
        locality = " ".join(x for x in (postal, city) if x)
        if locality:
            parts.append(_line(locality))

    parts.append(_line("--------------------------------"))
    parts.append('<text align="left"/>')

    for item in order.get("items") or []:
        qty = item.get("qty") or 1
        name = str(item.get("name") or "")
        price = Decimal(str(item.get("unit_price") or 0)) * Decimal(str(qty))
        parts.append('<text align="left" width="1" height="1" emphasized="true"/>')
        parts.append(_line(f"{qty} x {name}"))
        parts.append('<text align="left" emphasized="false"/>')
        parts.append(_line("    " + _money(price)))
        opts = _option_text(item)
        if opts:
            for chunk in [x.strip() for x in opts.replace(" • ", "|").split("|") if x.strip()]:
                parts.append(_line("  - " + chunk))
        parts.append('<feed line="1"/>')

    rate_text = f"{rate:g}".replace(".", ",")
    parts.extend([
        '<text align="left" width="1" height="1"/>',
        _line("--------------------------------"),
        _line("Total HT        " + _money(ht)),
        _line("TVA " + rate_text + " %       " + _money(tax)),
        '<text width="2" height="1" emphasized="true"/>',
        _line("TOTAL TTC " + _money(total)),
        '<text width="1" height="1" emphasized="false"/>',
        _line("Paiement: " + str(order.get("payment") or "A ENCAISSER")),
        _line("--------------------------------"),
        '<text align="center"/>',
        _line("Merci"),
        '<feed line="3"/>',
        '<cut type="feed"/>',
        '</epos-print>',
    ])
    return "".join(parts)


def _combined_xml(order, identity=None):
    """Un seul travail Epson : cuisine + coupe, puis client + coupe."""
    kitchen = _kitchen_xml(order)
    client = _client_xml(order, identity)
    declaration = '<?xml version="1.0" encoding="UTF-8"?>'
    root = '<epos-print xmlns="http://www.epson-pos.com/schemas/2011/03/epos-print">'

    def body(xml):
        x = xml
        if x.startswith(declaration):
            x = x[len(declaration):]
        if x.startswith(root):
            x = x[len(root):]
        if x.endswith('</epos-print>'):
            x = x[:-len('</epos-print>')]
        return x

    return declaration + root + body(kitchen) + body(client) + '</epos-print>'


def _expense_note_xml(order, identity=None, persons=1):
    identity = identity or {}
    ht, tax, total, rate = _tax_values(order)
    try:
        created_ms = int(order.get("created_at") or 0)
        dt = datetime.fromtimestamp(created_ms / 1000, tz=ZoneInfo("Europe/Paris"))
    except Exception:
        dt = datetime.now(ZoneInfo("Europe/Paris"))
    brand = str(identity.get("name") or "BECHEFAA").strip() or "BECHEFAA"
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<epos-print xmlns="http://www.epson-pos.com/schemas/2011/03/epos-print">',
        '<text align="center" font="font_a" width="2" height="2" emphasized="true"/>',
        _line(brand),
        '<text width="1" height="1" emphasized="false"/>',
        _line("NOTE DE FRAIS"),
    ]
    for line in _identity_lines(identity):
        parts.append(_line(line))
    siret = str(identity.get("siret") or "").strip()
    if siret:
        parts.append(_line("Siret : " + siret))
    parts.extend([
        _line("--------------------------------"),
        _line("Date : " + dt.strftime("%d/%m/%Y %H:%M")),
        _line("Nombre de repas : " + str(persons)),
        _line("--------------------------------"),
        '<text align="left"/>',
        _line("TOTAL HT        " + _money(ht)),
        _line("TVA " + f"{rate:g}".replace(".", ",") + " %       " + _money(tax)),
        '<text width="2" height="1" emphasized="true"/>',
        _line("TOTAL TTC " + _money(total)),
        '<text width="1" height="1" emphasized="false"/>',
        _line("--------------------------------"),
        '<text align="center"/>',
        _line("Justificatif de frais"),
        '<feed line="3"/>',
        '<cut type="feed"/>',
        '</epos-print>',
    ])
    return "".join(parts)


def _assistant_launch_html(xml, title="Epson"):
    assistant_url = (
        "tmprintassistant://tmprintassistant.epson.com/print?"
        "ver=1"
        "&data-type=eposprintxml"
        "&data=" + quote(xml, safe="")
        + "&timeout=30000"
        + "&error-dialog=yes"
    )
    safe_url = assistant_url.replace("\\", "\\\\").replace("'", "\\'")
    html = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>{title}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{{font-family:Arial,sans-serif;background:#111827;color:#fff;padding:24px;text-align:center}}
.box{{max-width:520px;margin:60px auto;background:#1f2937;border-radius:16px;padding:24px}}
button{{padding:12px 18px;border:0;border-radius:9px;font-weight:800}}</style>
</head><body><div class="box"><h2>{title}</h2><p>Ouverture de TM Print Assistant…</p>
<button onclick="launch()">Ouvrir Epson</button></div>
<script>
function launch(){{window.location.href='{safe_url}';}}
window.addEventListener('load',()=>setTimeout(launch,80));
</script></body></html>"""
    return Response(html, content_type="text/html; charset=utf-8")


def register_epson_epos_network_phase6(app, db, ensure_order_schema, order_payload):
    def _load_identity(conn):
        try:
            rows = conn.execute("SELECT setting_key,setting_value FROM caisse_restaurant_settings").fetchall()
            return {r["setting_key"]: (r["setting_value"] or "") for r in rows}
        except Exception:
            return {}

    def _ensure_ticket_columns(conn):
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS total_ttc NUMERIC(12,2)")
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS total_ht NUMERIC(12,2)")
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS tax_rate NUMERIC(6,3)")
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS tax_amount NUMERIC(12,2)")
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS table_number INTEGER NULL")
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS table_label TEXT NULL")

    def _load_print_order(conn, order_id):
        ensure_order_schema(conn)
        _ensure_ticket_columns(conn)
        conn.commit()
        row = conn.execute(
            """SELECT id,num,customer_name,phone,email,address,postal_code,city,
                      source,payment,status,total,total_ttc,total_ht,tax_rate,tax_amount,
                      table_number,table_label,created_at,updated_at
               FROM caisse_orders WHERE id=%s""",
            (order_id,),
        ).fetchone()
        if not row:
            return None
        order = order_payload(conn, row)
        for key in ("phone","email","address","postal_code","city","total_ttc","total_ht","tax_rate","tax_amount","table_number","table_label"):
            order[key] = row.get(key)
        order["service_mode"] = "SALLE" if row.get("table_number") else ("LIVRAISON" if str(row.get("source") or "").upper() in {"LIVRAISON","DELIVERY"} else "EMPORTER")
        return order

    def _ensure_network_defaults(conn):
        conn.execute("""CREATE TABLE IF NOT EXISTS caisse_hardware_config (
            config_key TEXT PRIMARY KEY,
            config_value TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        defaults = {
            "printer_mode": "NETWORK",
            "printer_brand": "EPSON",
            "printer_model": "TM-m30II",
            "printer_host": DEFAULT_HOST,
            "printer_name": DEFAULT_DEVICE_ID,
        }
        for key, value in defaults.items():
            conn.execute(
                """INSERT INTO caisse_hardware_config(config_key,config_value,updated_at)
                   VALUES (%s,%s,NOW())
                   ON CONFLICT (config_key) DO UPDATE
                   SET config_value = CASE
                       WHEN caisse_hardware_config.config_value='' THEN EXCLUDED.config_value
                       WHEN %s='printer_mode' AND caisse_hardware_config.config_value='USB' THEN EXCLUDED.config_value
                       WHEN %s='printer_model' AND caisse_hardware_config.config_value='TM-m30' THEN EXCLUDED.config_value
                       WHEN %s='printer_host' AND caisse_hardware_config.config_value='192.168.250.175' THEN EXCLUDED.config_value
                       ELSE caisse_hardware_config.config_value
                   END,
                   updated_at=NOW()""",
                (key, value, key, key, key),
            )

    @app.get("/epson/print-client/<order_id>")
    def epson_print_client_navigation_phase6(order_id):
        try:
            with db() as conn:
                order = _load_print_order(conn, order_id)
                if not order:
                    return "Commande introuvable", 404
                identity = _load_identity(conn)
            return _assistant_launch_html(_client_xml(order, identity), "Ticket client")
        except Exception as exc:
            return "Impression Epson impossible : " + str(exc), 500

    @app.get("/epson/print-kitchen/<order_id>")
    def epson_print_kitchen_navigation_phase6(order_id):
        try:
            with db() as conn:
                order = _load_print_order(conn, order_id)
                if not order:
                    return "Commande introuvable", 404
            return _assistant_launch_html(_kitchen_xml(order), "Ticket cuisine")
        except Exception as exc:
            return "Impression Epson impossible : " + str(exc), 500

    @app.get("/epson/print-order-pack/<order_id>")
    def epson_print_order_pack_navigation_phase6(order_id):
        try:
            with db() as conn:
                order = _load_print_order(conn, order_id)
                if not order:
                    return "Commande introuvable", 404
                identity = _load_identity(conn)
            return _assistant_launch_html(_combined_xml(order, identity), "Cuisine + client")
        except Exception as exc:
            return "Impression Epson impossible : " + str(exc), 500

    @app.get("/epson/print-expense-note/<order_id>")
    def epson_print_expense_note_navigation_phase6(order_id):
        try:
            try:
                persons = int(request.args.get("persons") or 1)
            except (TypeError, ValueError):
                persons = 1
            persons = max(1, min(persons, 99))
            with db() as conn:
                order = _load_print_order(conn, order_id)
                if not order:
                    return "Commande introuvable", 404
                pay = conn.execute(
                    "SELECT payment_status,paid_amount FROM caisse_orders WHERE id=%s",
                    (order_id,),
                ).fetchone()
                payment_status = str((pay or {}).get("payment_status") or "").strip().upper()
                paid_amount = Decimal(str((pay or {}).get("paid_amount") or 0))
                if paid_amount <= 0 and payment_status not in {"PAYÉE","PAYEE","PAID","ENCAISSÉE","ENCAISSEE"}:
                    return "Note de frais disponible uniquement après encaissement.", 409
                identity = _load_identity(conn)
            return _assistant_launch_html(_expense_note_xml(order, identity, persons), "Note de frais")
        except Exception as exc:
            return "Impression Epson impossible : " + str(exc), 500

    @app.get("/api/epson/config-phase6")
    def epson_config_phase6():
        try:
            with db() as conn:
                with conn.transaction():
                    _ensure_network_defaults(conn)
                rows = conn.execute(
                    "SELECT config_key,config_value FROM caisse_hardware_config"
                ).fetchall()
            cfg = {r["config_key"]: r["config_value"] for r in rows}
            return jsonify({
                "ok": True,
                "host": cfg.get("printer_host") or DEFAULT_HOST,
                "device_id": cfg.get("printer_name") or DEFAULT_DEVICE_ID,
                "model": cfg.get("printer_model") or "TM-m30II",
                "mode": cfg.get("printer_mode") or "NETWORK",
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": "Configuration Epson indisponible", "detail": str(exc)}), 500

    @app.get("/api/epson/kitchen-xml/<order_id>")
    def epson_kitchen_xml_phase6(order_id):
        try:
            with db() as conn:
                order = _load_print_order(conn, order_id)
                if not order:
                    return "Commande introuvable", 404
            xml = _kitchen_xml(order)
            response = Response(xml, content_type="text/xml; charset=utf-8")
            response.headers["Cache-Control"] = "no-store"
            return response
        except Exception as exc:
            return "Ticket Epson indisponible : " + str(exc), 500

    @app.get("/api/epson/client-xml/<order_id>")
    def epson_client_xml_phase6(order_id):
        try:
            with db() as conn:
                order = _load_print_order(conn, order_id)
                if not order:
                    return "Commande introuvable", 404
                identity = _load_identity(conn)
            xml = _client_xml(order, identity)
            response = Response(xml, content_type="text/xml; charset=utf-8")
            response.headers["Cache-Control"] = "no-store"
            return response
        except Exception as exc:
            return "Ticket Epson indisponible : " + str(exc), 500

    @app.get("/api/epson/order-pack-xml/<order_id>")
    def epson_order_pack_xml_phase6(order_id):
        try:
            with db() as conn:
                order = _load_print_order(conn, order_id)
                if not order:
                    return "Commande introuvable", 404
                identity = _load_identity(conn)
            xml = _combined_xml(order, identity)
            response = Response(xml, content_type="text/xml; charset=utf-8")
            response.headers["Cache-Control"] = "no-store"
            return response
        except Exception as exc:
            return "Ticket Epson indisponible : " + str(exc), 500

    @app.get("/api/epson/expense-note-xml/<order_id>")
    def epson_expense_note_xml_phase6(order_id):
        try:
            try:
                persons = int(request.args.get("persons") or 1)
            except (TypeError, ValueError):
                persons = 1
            persons = max(1, min(persons, 99))
            with db() as conn:
                order = _load_print_order(conn, order_id)
                if not order:
                    return "Commande introuvable", 404
                pay = conn.execute(
                    "SELECT payment_status,paid_amount FROM caisse_orders WHERE id=%s",
                    (order_id,),
                ).fetchone()
                payment_status = str((pay or {}).get("payment_status") or "").strip().upper()
                paid_amount = Decimal(str((pay or {}).get("paid_amount") or 0))
                if paid_amount <= 0 and payment_status not in {"PAYÉE","PAYEE","PAID","ENCAISSÉE","ENCAISSEE"}:
                    return "Note de frais disponible uniquement après encaissement.", 409
                identity = _load_identity(conn)
            xml = _expense_note_xml(order, identity, persons)
            response = Response(xml, content_type="text/xml; charset=utf-8")
            response.headers["Cache-Control"] = "no-store"
            return response
        except Exception as exc:
            return "Note de frais Epson indisponible : " + str(exc), 500

    @app.after_request
    def inject_epson_network_phase6(response):
        if request.path not in ("/pos", "/historique-modification") or response.status_code != 200 or response.mimetype != "text/html":
            return response
        html = response.get_data(as_text=True)
        if 'id="bechefaa-epson-phase6"' in html:
            return response

        addon = r'''
<style id="bechefaa-epson-phase6">
#epson-status{position:fixed;right:12px;bottom:12px;z-index:99998;background:#111827;color:#fff;
border-radius:8px;padding:7px 10px;font:700 11px Arial,sans-serif;box-shadow:0 2px 8px #0004}
#epson-status.ok{background:#166534}#epson-status.err{background:#991b1b}#epson-status.work{background:#92400e}
</style>
<div id="epson-status">Epson : initialisation…</div>
<script>
(function(){
 const box=document.getElementById('epson-status');
 let cfg=null, nativeFetch=window.fetch.bind(window), printed=new Set();

 function status(kind,msg){box.className=kind||'';box.textContent=msg}
 function epsonDiag(stage){
   try{
     const standalone=window.matchMedia&&window.matchMedia('(display-mode: standalone)').matches;
     const navStandalone=window.navigator.standalone===true;
     sessionStorage.setItem('bechefaa_epson_diag',JSON.stringify({
       stage:stage||'',href:window.location.href,standalone:!!standalone,navStandalone:!!navStandalone,
       ua:String(navigator.userAgent||'').slice(0,180),ts:Date.now()
     }));
   }catch(e){}
 }

 async function getConfig(){
   if(cfg)return cfg;
   const r=await nativeFetch('/api/epson/config-phase6',{cache:'no-store'});
   const d=await r.json();
   if(!r.ok||!d.ok)throw new Error(d.error||'Configuration Epson impossible');
   cfg=d;return d;
 }

 async function openPrintAssistant(xml,label,orderId){
   if(xml.length>180000)throw new Error('Ticket trop volumineux pour TM Print Assistant');
   const assistantUrl='tmprintassistant://tmprintassistant.epson.com/print?'
     +'ver=1'
     +'&data-type=eposprintxml'
     +'&data='+encodeURIComponent(xml)
     +'&timeout=30000'
     +'&error-dialog=yes';
   if(orderId)printed.add(String(label)+':'+String(orderId));
   epsonDiag('before-assistant');
   status('work','Epson : ouverture TM Print Assistant…');
   window.location.href=assistantUrl;
   return true;
 }

 async function printClient(orderId){
   if(!orderId)return true;
   status('work','Epson : préparation du ticket client…');
   if(/Android/i.test(navigator.userAgent||'')){window.location.href='/epson/print-client/'+encodeURIComponent(orderId);return true;}
   const xr=await nativeFetch('/api/epson/client-xml/'+encodeURIComponent(orderId),{cache:'no-store'});
   if(!xr.ok)throw new Error('Ticket client introuvable');
   const xml=await xr.text();
   window.location.href='/impression/client/'+encodeURIComponent(orderId);
   return true;
 }

 async function printOrderPack(orderId){
   if(!orderId)return true;
   status('work','Epson : préparation cuisine + client…');
   if(/Android/i.test(navigator.userAgent||'')){window.location.href='/epson/print-order-pack/'+encodeURIComponent(orderId);return true;}
   const xr=await nativeFetch('/api/epson/order-pack-xml/'+encodeURIComponent(orderId),{cache:'no-store'});
   if(!xr.ok)throw new Error('Tickets cuisine/client introuvables');
   const xml=await xr.text();


   const c=await getConfig();
   const ports=[8143,443];
   let pr=null,usedPort=null,lastErr=null;
   for(const port of ports){
     const url='https://'+c.host+(port===443?'':':'+port)+'/cgi-bin/epos/service.cgi?devid='+encodeURIComponent(c.device_id||'local_printer')+'&timeout=10000';
     try{
       const candidate=await nativeFetch(url,{method:'POST',mode:'cors',cache:'no-store',headers:{'Content-Type':'text/xml; charset=utf-8'},body:xml});
       const candidateBody=await candidate.text();
       if(!candidate.ok)throw new Error('HTTP '+candidate.status+' sur port '+port);
       if(/Welcome to Socket\\.IO/i.test(candidateBody))throw new Error('Port '+port+' réservé à Socket.IO');
       if(/success\\s*=\\s*["']false["']/i.test(candidateBody))throw new Error('Epson a refusé les tickets sur port '+port);
       pr=candidate;usedPort=port;break;
     }catch(e){lastErr=e}
   }
   if(!pr)throw new Error('ePOS HTTPS inaccessible (8143/443)'+(lastErr?': '+(lastErr.message||lastErr):''));
   printed.add('order-pack:'+String(orderId));
   status('ok','Epson : cuisine + client imprimés • port '+usedPort);
   setTimeout(()=>status('ok','Epson TM-m30II prête'),3500);
   return true;
 }

 window.bechefaaPrintOrderPack=printOrderPack;

 async function printKitchen(orderId){
   if(!orderId)return true;
   status('work','Epson : préparation du ticket…');
   if(/Android/i.test(navigator.userAgent||'')){window.location.href='/epson/print-kitchen/'+encodeURIComponent(orderId);return true;}
   const xr=await nativeFetch('/api/epson/kitchen-xml/'+encodeURIComponent(orderId),{cache:'no-store'});
   if(!xr.ok)throw new Error('Ticket cuisine introuvable');
   const xml=await xr.text();

   // Android / Samsung Internet : méthode officielle Epson TM Print Assistant.
   // L'application reçoit l'ePOS-Print XML via le schéma URL et relaie
   // l'impression vers la TM-m30II déjà sélectionnée dans TM Print Assistant.

   // Secours hors Android : communication ePOS réseau directe.
   const c=await getConfig();
   const ports=[8143,443];
   let pr=null,body='',usedPort=null,lastErr=null;
   for(const port of ports){
     const url='https://'+c.host+(port===443?'':':'+port)+'/cgi-bin/epos/service.cgi?devid='+encodeURIComponent(c.device_id||'local_printer')+'&timeout=10000';
     try{
       const candidate=await nativeFetch(url,{
         method:'POST',
         mode:'cors',
         cache:'no-store',
         headers:{'Content-Type':'text/xml; charset=utf-8'},
         body:xml
       });
       const candidateBody=await candidate.text();
       if(!candidate.ok)throw new Error('HTTP '+candidate.status+' sur port '+port);
       if(/Welcome to Socket\\.IO/i.test(candidateBody))throw new Error('Port '+port+' réservé à Socket.IO');
       if(/success\\s*=\\s*["']false["']/i.test(candidateBody))throw new Error('Epson a refusé le ticket sur port '+port);
       pr=candidate;body=candidateBody;usedPort=port;break;
     }catch(e){lastErr=e}
   }
   if(!pr)throw new Error('ePOS HTTPS inaccessible (8143/443)'+(lastErr?': '+(lastErr.message||lastErr):''));
   printed.add(orderId);
   status('ok','Epson : ticket cuisine imprimé • port '+usedPort);
   setTimeout(()=>status('ok','Epson TM-m30II prête'),3500);
   return true;
 }
 async function printExpenseNote(orderId,persons){
   if(!orderId)return true;
   const n=Math.max(1,Math.min(99,parseInt(persons||1,10)||1));
   status('work','Epson : préparation de la note de frais…');
   if(/Android/i.test(navigator.userAgent||'')){window.location.href='/epson/print-expense-note/'+encodeURIComponent(orderId)+'?persons='+encodeURIComponent(n);return true;}
   const xr=await nativeFetch('/api/epson/expense-note-xml/'+encodeURIComponent(orderId)+'?persons='+encodeURIComponent(n),{cache:'no-store'});
   if(!xr.ok){
     const detail=await xr.text().catch(()=> '');
     throw new Error(detail||'Note de frais introuvable');
   }
   const xml=await xr.text();
   window.location.href='/impression/note-de-frais/'+encodeURIComponent(orderId)+'?persons='+encodeURIComponent(n);
   return true;
 }
 async function testConnection(){
   try{
     const c=await getConfig();
     status('ok','Epson TM-m30II • '+c.host);
   }catch(e){
     status('err','Epson : configuration indisponible');
   }
 }

 window.fetch=async function(input,init){
   const url=typeof input==='string'?input:(input&&input.url)||'';
   const method=String((init&&init.method)||'GET').toUpperCase();
   const res=await nativeFetch(input,init);
   if(method==='POST' && /\/api\/orders\/[^/]+\/send-kitchen(?:\?|$)/.test(url)){
     try{
       const d=await res.clone().json();
       if(res.ok && d && d.ok!==false && d.id){
         setTimeout(()=>printOrderPack(d.id).catch(e=>status('err','Epson : '+(e.message||'impression impossible'))),50);
       }
     }catch(e){}
   }
   return res;
 };

 // Permet au mode hors connexion de déclencher l'impression après resynchronisation
 // dès qu'il transmettra des identifiants de commandes réelles.
 if(navigator.serviceWorker){
   navigator.serviceWorker.addEventListener('message',e=>{
     const d=e.data||{};
     const ids=Array.isArray(d.print_order_ids)?d.print_order_ids:[];
     ids.forEach(id=>printOrderPack(id).catch(err=>status('err','Epson : '+(err.message||'impression impossible'))));
   });
 }

 window.bechefaaPrintKitchen=printKitchen;
 window.bechefaaPrintClient=printClient;
 window.bechefaaPrintExpenseNote=printExpenseNote;
 if(new URLSearchParams(window.location.search).get('epson')==='success'){
   epsonDiag('success-return');
   let d=null;try{d=JSON.parse(sessionStorage.getItem('bechefaa_epson_diag')||'null')}catch(e){}
   const standalone=window.matchMedia&&window.matchMedia('(display-mode: standalone)').matches;
   status(standalone?'ok':'err','DIAG EPSON : retour '+(standalone?'dans la PWA':'dans le navigateur'));
 }
 testConnection();
})();
</script>'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
