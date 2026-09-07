"""Phase 1 — Étape 6 : impression 80 mm BÉCHÉFAA.

Impression navigateur compatible avec une Epson TM-m30 installée comme imprimante système.
Deux tickets distincts : client et cuisine.
Aucun accès Wix / V1 / localStorage.
"""
from html import escape

from flask import Response, jsonify, request


def _ticket_type(source):
    value = str(source or "").upper()
    if value == "SALLE":
        return "Salle"
    if value in {"EMPORTER", "TAKEAWAY"}:
        return "Emporter"
    if value in {"LIVRAISON", "DELIVERY"}:
        return "Livraison"
    return "Comptoir"


def _money(value):
    try:
        return f"{float(value):.2f}".replace(".", ",") + " €"
    except Exception:
        return "0,00 €"


def _load_order(conn, ensure_order_schema, order_payload, order_id):
    ensure_order_schema(conn)
    conn.commit()
    row = conn.execute(
        """SELECT id, num, customer_name, phone, email, address, postal_code, city,
                  source, payment, status, total, created_at, updated_at
           FROM caisse_orders WHERE id=%s""",
        (order_id,),
    ).fetchone()
    if not row:
        return None
    payload = order_payload(conn, row)
    payload.update({
        "phone": row.get("phone") or "",
        "email": row.get("email") or "",
        "address": row.get("address") or "",
        "postal_code": row.get("postal_code") or "",
        "city": row.get("city") or "",
        "ticket_type": _ticket_type(row.get("source")),
    })
    return payload


def _base_css():
    return r'''
<style>
@page{size:80mm auto;margin:3mm}
*{box-sizing:border-box}html,body{margin:0;padding:0;background:#fff;color:#000;font-family:Arial,sans-serif}
.ticket80{width:74mm;margin:0 auto;font-size:12px;line-height:1.3}.center{text-align:center}.brand{font-size:22px;font-weight:900;letter-spacing:.4px}.big{font-size:28px;font-weight:900}.mode{font-size:18px;font-weight:900;margin:5px 0}.sep{border-top:1px dashed #000;margin:8px 0}.row{display:flex;justify-content:space-between;gap:8px}.item{padding:5px 0}.item-name{font-size:14px;font-weight:800}.opts{font-size:11px;margin-top:2px}.total{font-size:19px;font-weight:900}.muted{font-size:10px}.actions{margin:12px auto;width:74mm;display:flex;gap:8px}.actions button{flex:1;padding:10px;border:0;border-radius:6px;background:#111827;color:#fff;font-weight:800;cursor:pointer}
@media print{.actions{display:none!important}.ticket80{width:74mm}}
</style>
'''


def register_printing_phase1(app, db, ensure_order_schema, order_payload):
    @app.get("/impression/client/<order_id>")
    def print_client(order_id):
        try:
            with db() as conn:
                order = _load_order(conn, ensure_order_schema, order_payload, order_id)
            if not order:
                return "Commande introuvable", 404
        except Exception as exc:
            return f"Impression indisponible : {escape(str(exc))}", 500

        mode = order["ticket_type"]
        client_block = ""
        if mode != "Salle":
            parts = []
            if order.get("customer_name"):
                parts.append(f"<b>{escape(str(order['customer_name']))}</b>")
            if order.get("phone"):
                parts.append(escape(str(order["phone"])))
            if mode == "Livraison":
                address = " ".join(x for x in [order.get("address"), order.get("postal_code"), order.get("city")] if x)
                if address:
                    parts.append(escape(address))
            if parts:
                client_block = '<div class="sep"></div><div>' + "<br>".join(parts) + "</div>"

        items_html = "".join(
            f'''<div class="item"><div class="row"><span class="item-name">{escape(str(i.get("qty",1)))} × {escape(str(i.get("name") or ""))}</span><span>{_money(float(i.get("unit_price") or 0)*float(i.get("qty") or 1))}</span></div>{f'<div class="opts">{escape(str(i.get("options_text") or ""))}</div>' if i.get("options_text") else ''}</div>'''
            for i in order.get("items") or []
        )
        auto = request.args.get("auto") == "1"
        html = f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Ticket #{escape(str(order['num']))}</title>{_base_css()}</head><body>
<div class="ticket80"><div class="center brand">BÉCHÉFAA</div><div class="center">Ticket client</div><div class="sep"></div><div class="center big">#{escape(str(order['num']))}</div><div class="center mode">{escape(mode.upper())}</div>{client_block}<div class="sep"></div>{items_html}<div class="sep"></div><div class="row total"><span>TOTAL</span><span>{_money(order.get('total'))}</span></div><div class="row"><span>Paiement</span><span>{escape(str(order.get('payment') or 'À ENCAISSER'))}</span></div><div class="sep"></div><div class="center muted">Merci et à bientôt chez BÉCHÉFAA</div></div>
<div class="actions"><button onclick="window.print()">Imprimer</button><button onclick="window.close()">Fermer</button></div>{'<script>window.addEventListener("load",()=>setTimeout(()=>window.print(),150));</script>' if auto else ''}</body></html>'''
        return Response(html, content_type="text/html; charset=utf-8")

    @app.get("/impression/cuisine/<order_id>")
    def print_kitchen(order_id):
        try:
            with db() as conn:
                order = _load_order(conn, ensure_order_schema, order_payload, order_id)
            if not order:
                return "Commande introuvable", 404
        except Exception as exc:
            return f"Impression indisponible : {escape(str(exc))}", 500

        mode = order["ticket_type"]
        client_line = ""
        if mode != "Salle" and order.get("customer_name"):
            client_line = f'<div class="center"><b>{escape(str(order["customer_name"]))}</b></div>'
        items_html = "".join(
            f'''<div class="item"><div class="item-name">{escape(str(i.get("qty",1)))} × {escape(str(i.get("name") or ""))}</div>{f'<div class="opts">{escape(str(i.get("options_text") or ""))}</div>' if i.get("options_text") else ''}</div>'''
            for i in order.get("items") or []
        )
        auto = request.args.get("auto") == "1"
        html = f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Cuisine #{escape(str(order['num']))}</title>{_base_css()}<style>.item-name{{font-size:18px}}.opts{{font-size:14px;font-weight:700}}.item{{padding:8px 0;border-bottom:1px dashed #000}}</style></head><body>
<div class="ticket80"><div class="center brand">BÉCHÉFAA • CUISINE</div><div class="sep"></div><div class="center big">#{escape(str(order['num']))}</div><div class="center mode">{escape(mode.upper())}</div>{client_line}<div class="sep"></div>{items_html}</div>
<div class="actions"><button onclick="window.print()">Imprimer</button><button onclick="window.close()">Fermer</button></div>{'<script>window.addEventListener("load",()=>setTimeout(()=>window.print(),150));</script>' if auto else ''}</body></html>'''
        return Response(html, content_type="text/html; charset=utf-8")

    @app.after_request
    def inject_print_buttons(response):
        if request.path != "/pos" or response.status_code != 200 or response.mimetype != "text/html":
            return response
        html = response.get_data(as_text=True)
        addon = r'''
<style>.print-actions{display:flex;gap:8px;margin-top:8px}.print-actions a{flex:1;text-align:center;text-decoration:none;border-radius:8px;padding:10px 8px;font-weight:800;font-size:12px}.print-client{background:#2563eb;color:white}.print-kitchen{background:#d97706;color:white}</style>
<script>
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   let lastOrderId=null;
   const nativeFetch=window.fetch.bind(window);
   window.fetch=async function(input,init){
     const url=typeof input==='string'?input:(input&&input.url)||'';
     const res=await nativeFetch(input,init);
     try{
       const method=String((init&&init.method)||'GET').toUpperCase();
       if((url==='/api/orders'&&method==='POST')||(url.includes('/send-kitchen')&&method==='POST')){
         const clone=res.clone(),data=await clone.json();
         if(data&&data.ok!==false&&data.id)lastOrderId=data.id;
         setTimeout(addButtons,80);
       }
     }catch(e){}
     return res;
   };
   function addButtons(){
     if(!lastOrderId)return;
     const msg=document.getElementById('order-message');if(!msg)return;
     if(msg.querySelector('.print-actions'))return;
     const wrap=document.createElement('div');wrap.className='print-actions';
     wrap.innerHTML='<a class="print-client" target="_blank" href="/impression/client/'+encodeURIComponent(lastOrderId)+'">Ticket client 80 mm</a><a class="print-kitchen" target="_blank" href="/impression/cuisine/'+encodeURIComponent(lastOrderId)+'">Ticket cuisine 80 mm</a>';
     msg.appendChild(wrap);
   }
   const msg=document.getElementById('order-message');if(msg)new MutationObserver(()=>setTimeout(addButtons,50)).observe(msg,{childList:true,subtree:true});
 });
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
