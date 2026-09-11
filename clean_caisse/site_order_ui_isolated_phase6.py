"""Phase 6 — affichage provenance SITE et notification visuelle caisse.

Correctif isolé :
- n'altère pas le cycle métier des commandes ;
- n'écrit aucune nouvelle donnée de commande ;
- expose simplement sales_channel dans les réponses cuisine ;
- adapte l'écran Cuisine pour afficher SITE et, pour une commande SITE à emporter,
  afficher uniquement le nom du client ;
- ajoute sur /pos une notification visuelle lorsqu'une nouvelle commande SITE arrive.
"""
import json

from flask import request


def _inject_sales_channel(db, body):
    if not isinstance(body, dict) or not isinstance(body.get("orders"), list):
        return body
    ids = [str(o.get("id") or "").strip() for o in body["orders"] if isinstance(o, dict)]
    ids = [x for x in ids if x]
    if not ids:
        return body
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT id, COALESCE(sales_channel, 'RESTO') AS sales_channel FROM caisse_orders WHERE id = ANY(%s)",
                (ids,),
            ).fetchall()
        channels = {str(r["id"]): str(r["sales_channel"] or "RESTO") for r in rows}
        for order in body["orders"]:
            if isinstance(order, dict):
                order["sales_channel"] = channels.get(str(order.get("id") or ""), "RESTO")
    except Exception:
        # Compatibilité si le champ n'existe pas encore sur une ancienne base.
        for order in body["orders"]:
            if isinstance(order, dict):
                order.setdefault("sales_channel", "RESTO")
    return body


def register_site_order_ui_isolated_phase6(app, db):
    @app.after_request
    def site_order_ui_phase6(response):
        if response.status_code != 200:
            return response

        if request.method == "GET" and request.path in ("/api/kitchen/orders", "/api/kitchen/board"):
            try:
                body = response.get_json(silent=True)
                body = _inject_sales_channel(db, body)
                response.set_data(json.dumps(body, ensure_ascii=False))
                response.content_type = "application/json; charset=utf-8"
                response.content_length = len(response.get_data())
            except Exception:
                return response
            return response

        if response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)

        if request.path == "/cuisine-preparation":
            # Le badge de provenance doit utiliser le canal commercial, pas le mode de service.
            html = html.replace(
                "${channelBadge(o.source)}${modeBadge(o.ticket_type)}",
                "${channelBadge(o.sales_channel||o.source)}${modeBadge(o.ticket_type)}",
            )
            html = html.replace(
                "SITE INTERNET</span>",
                "SITE</span>",
            )
            # Pour une commande SITE à emporter, le titre principal devient uniquement le nom client.
            marker = "function orderIdentity(o){"
            if marker in html and "SITE_ORDER_IDENTITY_PHASE6" not in html:
                html = html.replace(
                    marker,
                    "function orderIdentitySitePhase6(o){ /* SITE_ORDER_IDENTITY_PHASE6 */\n"
                    "  let channel=String((o&&o.sales_channel)||'').toUpperCase();\n"
                    "  let customer=String((o&&o.customer_name)||'').trim();\n"
                    "  let type=String((o&&o.ticket_type)||'').toLowerCase();\n"
                    "  if(channel==='SITE' && customer && !type.includes('livraison')) return customer;\n"
                    "  return null;\n"
                    "}\n" + marker,
                    1,
                )
                html = html.replace(
                    "function orderIdentity(o){\n  let table=String(o.table_label||'').trim();",
                    "function orderIdentity(o){\n  let siteIdentity=orderIdentitySitePhase6(o);if(siteIdentity)return siteIdentity;\n  let table=String(o.table_label||'').trim();",
                    1,
                )

        if request.path == "/pos" and "SITE_ORDER_TOAST_PHASE6" not in html:
            addon = r'''
<style>
#site-order-toast-phase6{position:fixed;right:20px;bottom:20px;z-index:10050;max-width:390px;background:#111827;color:#fff;border-radius:12px;padding:15px 18px;box-shadow:0 10px 32px rgba(0,0,0,.28);font-weight:800;display:none}
#site-order-toast-phase6.show{display:block}
#site-order-toast-phase6 .site-title{font-size:16px;margin-bottom:4px}
#site-order-toast-phase6 .site-detail{font-size:14px;font-weight:600;opacity:.92}
</style>
<script>
(function(){ /* SITE_ORDER_TOAST_PHASE6 */
 const KEY='bechefaa_phase6_last_site_order_num';
 let ready=false;
 function toast(order){
   let el=document.getElementById('site-order-toast-phase6');
   if(!el){el=document.createElement('div');el.id='site-order-toast-phase6';document.body.appendChild(el)}
   const name=String(order.customer_name||'Client').trim();
   const mode=String(order.ticket_type||'').toLowerCase().includes('livraison')?'Livraison':'À emporter';
   el.innerHTML='<div class="site-title">Nouvelle commande SITE</div><div class="site-detail">'+name+' • '+mode+'</div>';
   el.classList.add('show');
   clearTimeout(el._hideTimer);el._hideTimer=setTimeout(()=>el.classList.remove('show'),7000);
 }
 async function pollSiteOrders(){
   try{
     const r=await fetch('/api/kitchen/orders',{cache:'no-store'}),d=await r.json();
     if(!r.ok||!d||!Array.isArray(d.orders))return;
     const site=d.orders.filter(o=>String(o.sales_channel||'').toUpperCase()==='SITE');
     const nums=site.map(o=>Number(o.num)).filter(Number.isFinite);
     if(!nums.length){ready=true;return}
     const max=Math.max.apply(null,nums);
     const raw=localStorage.getItem(KEY);
     if(raw===null||!ready){localStorage.setItem(KEY,String(max));ready=true;return}
     const last=Number(raw);
     const newer=site.filter(o=>Number(o.num)>last).sort((a,b)=>Number(a.num)-Number(b.num));
     if(max>last)localStorage.setItem(KEY,String(max));
     if(newer.length)toast(newer[newer.length-1]);
   }catch(e){}
 }
 pollSiteOrders();setInterval(pollSiteOrders,4000);
})();
</script>
'''
            html = html.replace("</body>", addon + "</body>")

        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
