"""Phase 6 — impression Epson ePOS-Print sur TM-m30II réseau.

Le navigateur de la tablette envoie directement le XML ePOS à l'imprimante locale.
Clever Cloud ne tente jamais d'accéder au LAN du restaurant.

Configuration actuelle restaurant:
- Epson TM-m30II
- IP 192.168.250.175
- ePOS-Print activé
- Device ID local_printer
"""
from xml.sax.saxutils import escape

from flask import Response, jsonify, request


DEFAULT_HOST = "192.168.250.175"
DEFAULT_DEVICE_ID = "local_printer"


def _line(text=""):
    return '<text>' + escape(str(text or "")) + '</text><feed line="1"/>'


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


def _kitchen_xml(order):
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<epos-print xmlns="http://www.epson-pos.com/schemas/2011/03/epos-print">',
        '<text align="center" font="font_a" width="2" height="2"/>',
        _line("BECHEFAA"),
        '<text width="1" height="1"/>',
        _line("--------------------------------"),
        '<text width="2" height="2"/>',
        _line("COMMANDE " + str(order.get("num") or "")),
        '<text width="1" height="1"/>',
    ]

    customer = str(order.get("customer_name") or "").strip()
    if customer and customer.lower() not in {"client comptoir", "client livraison"}:
        parts.append(_line(customer))

    source = str(order.get("source") or "").upper()
    if source in {"LIVRAISON", "DELIVERY"}:
        parts.append(_line("LIVRAISON"))
    else:
        parts.append(_line("A EMPORTER"))

    parts.append(_line("--------------------------------"))

    for item in order.get("items") or []:
        qty = item.get("qty") or 1
        name = str(item.get("name") or "")
        parts.append('<text width="2" height="1"/>')
        parts.append(_line(f"{qty} x {name}"))
        parts.append('<text width="1" height="1"/>')
        opts = _option_text(item)
        if opts:
            # ePOS text handles wrapping; split logical option groups for readability.
            for chunk in [x.strip() for x in opts.replace(" • ", "|").split("|") if x.strip()]:
                parts.append(_line("  - " + chunk))

    parts.extend([
        _line("--------------------------------"),
        '<feed line="3"/>',
        '<cut type="feed"/>',
        '</epos-print>',
    ])
    return "".join(parts)


def register_epson_epos_network_phase6(app, db, ensure_order_schema, order_payload):
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
                       ELSE caisse_hardware_config.config_value
                   END,
                   updated_at=NOW()""",
                (key, value, key, key),
            )

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
                ensure_order_schema(conn)
                conn.commit()
                row = conn.execute(
                    """SELECT id,num,customer_name,source,payment,status,total,created_at,updated_at
                       FROM caisse_orders WHERE id=%s""",
                    (order_id,),
                ).fetchone()
                if not row:
                    return "Commande introuvable", 404
                order = order_payload(conn, row)
            xml = _kitchen_xml(order)
            response = Response(xml, content_type="text/xml; charset=utf-8")
            response.headers["Cache-Control"] = "no-store"
            return response
        except Exception as exc:
            return "Ticket Epson indisponible : " + str(exc), 500

    @app.after_request
    def inject_epson_network_phase6(response):
        if request.path != "/pos" or response.status_code != 200 or response.mimetype != "text/html":
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

 async function getConfig(){
   if(cfg)return cfg;
   const r=await nativeFetch('/api/epson/config-phase6',{cache:'no-store'});
   const d=await r.json();
   if(!r.ok||!d.ok)throw new Error(d.error||'Configuration Epson impossible');
   cfg=d;return d;
 }

 async function printKitchen(orderId){
   if(!orderId||printed.has(orderId))return true;
   status('work','Epson : impression…');
   const c=await getConfig();
   const xr=await nativeFetch('/api/epson/kitchen-xml/'+encodeURIComponent(orderId),{cache:'no-store'});
   if(!xr.ok)throw new Error('Ticket cuisine introuvable');
   const xml=await xr.text();
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
         setTimeout(()=>printKitchen(d.id).catch(e=>status('err','Epson : '+(e.message||'impression impossible'))),50);
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
     ids.forEach(id=>printKitchen(id).catch(err=>status('err','Epson : '+(err.message||'impression impossible'))));
   });
 }

 window.bechefaaPrintKitchen=printKitchen;
 testConnection();
})();
</script>'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
