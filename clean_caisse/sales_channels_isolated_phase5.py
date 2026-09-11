"""Canaux de vente isolés — RESTO / SITE / UBER_EATS / DELIVEROO.

Le mode de service historique reste dans ``source`` (Salle/Emporter/Livraison).
Le canal commercial est conservé séparément dans ``sales_channel``.

Phase 6 ajoute uniquement deux lectures d'interface :
- exposition de ``sales_channel`` dans les réponses cuisine ;
- notification visuelle sur /pos lorsqu'une nouvelle commande SITE arrive.
Le cycle métier des commandes n'est pas modifié.
"""

import json

from flask import g, request


SALES_CHANNELS = ("RESTO", "SITE", "UBER_EATS", "DELIVEROO")


def _normalize_sales_channel(value):
    raw = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "": "RESTO",
        "CAISSE": "RESTO",
        "RESTAURANT": "RESTO",
        "RESTO": "RESTO",
        "WEB": "SITE",
        "WIX": "SITE",
        "SITE": "SITE",
        "SITE_INTERNET": "SITE",
        "UBER": "UBER_EATS",
        "UBEREAT": "UBER_EATS",
        "UBEREATS": "UBER_EATS",
        "UBER_EATS": "UBER_EATS",
        "DELIVEROO": "DELIVEROO",
    }
    return aliases.get(raw, "RESTO")


def _add_sales_channels_to_orders(db, body):
    if not isinstance(body, dict) or not isinstance(body.get("orders"), list):
        return body

    ids = [
        str(order.get("id") or "").strip()
        for order in body["orders"]
        if isinstance(order, dict)
    ]
    ids = [order_id for order_id in ids if order_id]
    if not ids:
        return body

    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT id, COALESCE(sales_channel, 'RESTO') AS sales_channel "
                "FROM caisse_orders WHERE id = ANY(%s)",
                (ids,),
            ).fetchall()
        channels = {
            str(row["id"]): _normalize_sales_channel(row["sales_channel"])
            for row in rows
        }
        for order in body["orders"]:
            if isinstance(order, dict):
                order["sales_channel"] = channels.get(
                    str(order.get("id") or ""), "RESTO"
                )
    except Exception:
        # Compatibilité avec une base plus ancienne : aucune erreur métier.
        for order in body["orders"]:
            if isinstance(order, dict):
                order.setdefault("sales_channel", "RESTO")
    return body


def register_sales_channels_isolated_phase5(app, db):
    @app.before_request
    def capture_sales_channel_phase5():
        if request.path != "/api/orders" or request.method != "POST":
            return None
        payload = request.get_json(silent=True) or {}
        g.phase5_sales_channel = _normalize_sales_channel(
            payload.get("sales_channel") or payload.get("channel")
        )
        return None

    @app.after_request
    def persist_sales_channel_phase5(response):
        if request.path != "/api/orders" or request.method != "POST":
            return response
        if response.status_code < 200 or response.status_code >= 300:
            return response

        try:
            body = response.get_json(silent=True)
            if not isinstance(body, dict):
                body = json.loads(response.get_data(as_text=True) or "{}")
            order_id = str(body.get("id") or "").strip()
            if not order_id:
                return response

            channel = _normalize_sales_channel(
                getattr(g, "phase5_sales_channel", "RESTO")
            )
            with db() as conn:
                with conn.transaction():
                    conn.execute(
                        "ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS "
                        "sales_channel TEXT NOT NULL DEFAULT 'RESTO'"
                    )
                    conn.execute(
                        "UPDATE caisse_orders SET sales_channel=%s WHERE id=%s",
                        (channel, order_id),
                    )
        except Exception:
            # Une commande créée ne devient jamais une erreur à cause du canal.
            return response

        return response

    @app.after_request
    def expose_sales_channel_and_site_notice_phase6(response):
        if response.status_code != 200:
            return response

        if request.method == "GET" and request.path in (
            "/api/kitchen/orders",
            "/api/kitchen/board",
        ):
            try:
                body = response.get_json(silent=True)
                body = _add_sales_channels_to_orders(db, body)
                response.set_data(json.dumps(body, ensure_ascii=False))
                response.content_type = "application/json; charset=utf-8"
                response.content_length = len(response.get_data())
            except Exception:
                pass
            return response

        if request.path != "/pos" or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        if "SITE_ORDER_TOAST_PHASE6" in html:
            return response

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
 let initialized=false;
 function showSiteOrder(order){
   let el=document.getElementById('site-order-toast-phase6');
   if(!el){el=document.createElement('div');el.id='site-order-toast-phase6';document.body.appendChild(el)}
   const name=String(order.customer_name||'Client').trim();
   const mode=String(order.ticket_type||'').toLowerCase().includes('livraison')?'Livraison':'À emporter';
   el.innerHTML='<div class="site-title">Nouvelle commande SITE</div><div class="site-detail">'+name+' • '+mode+'</div>';
   el.classList.add('show');
   clearTimeout(el._hideTimer);
   el._hideTimer=setTimeout(()=>el.classList.remove('show'),7000);
 }
 async function pollSiteOrders(){
   try{
     const r=await fetch('/api/kitchen/orders',{cache:'no-store'}),d=await r.json();
     if(!r.ok||!d||!Array.isArray(d.orders))return;
     const site=d.orders.filter(o=>String(o.sales_channel||'').toUpperCase()==='SITE');
     const nums=site.map(o=>Number(o.num)).filter(Number.isFinite);
     if(!nums.length){initialized=true;return}
     const max=Math.max.apply(null,nums);
     const raw=localStorage.getItem(KEY);
     if(raw===null||!initialized){localStorage.setItem(KEY,String(max));initialized=true;return}
     const last=Number(raw);
     const newer=site.filter(o=>Number(o.num)>last).sort((a,b)=>Number(a.num)-Number(b.num));
     if(max>last)localStorage.setItem(KEY,String(max));
     if(newer.length)showSiteOrder(newer[newer.length-1]);
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
