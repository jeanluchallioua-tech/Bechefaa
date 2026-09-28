"""DIAG temporaire — commandes SITE / Cuisine.

Lecture seule : aucune écriture PostgreSQL et aucun changement de commande.
"""
from flask import jsonify, request


def register_site_order_runtime_diag_phase6(app, db, ensure_order_schema):
    @app.get("/api/diag/site-orders-runtime")
    def diag_site_orders_runtime_phase6():
        try:
            with db() as conn:
                ensure_order_schema(conn)
                rows = conn.execute(
                    """
                    SELECT id,num,customer_name,status,payment_status,payment_method,
                           total,source,sales_channel,created_at,updated_at
                    FROM caisse_orders
                    WHERE UPPER(COALESCE(sales_channel,''))='SITE'
                    ORDER BY created_at DESC
                    LIMIT 5
                    """
                ).fetchall()

            orders = []
            for row in rows:
                status = str(row.get("status") or "").strip()
                orders.append({
                    "id": row.get("id"),
                    "num": row.get("num"),
                    "customer_name": row.get("customer_name"),
                    "status": status,
                    "payment_status": row.get("payment_status"),
                    "payment_method": row.get("payment_method"),
                    "total": float(row.get("total") or 0),
                    "source": row.get("source"),
                    "sales_channel": row.get("sales_channel"),
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
                    "should_be_on_kitchen_board": status in ("À préparer", "En préparation", "Prête"),
                })

            return jsonify({"ok": True, "count": len(orders), "orders": orders})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.after_request
    def inject_site_order_runtime_diag_phase6(response):
        if request.path != "/pos" or response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        if "site-order-runtime-diag" in html:
            return response

        addon = r"""
<style id="site-order-runtime-diag-style">
#site-order-runtime-diag{
  position:fixed;left:205px;bottom:8px;z-index:40000;
  width:min(820px,calc(100vw - 660px));max-height:180px;overflow:auto;
  background:#111827;color:#f9fafb;border:1px solid #f59e0b;border-radius:9px;
  padding:9px 11px;font:12px/1.35 Arial,sans-serif;box-shadow:0 8px 24px #0007
}
#site-order-runtime-diag b{color:#fbbf24}
#site-order-runtime-diag .bad{color:#fca5a5;font-weight:900}
#site-order-runtime-diag .good{color:#86efac;font-weight:900}
#site-order-runtime-diag .muted{color:#9ca3af}
@media(max-width:1000px){
 #site-order-runtime-diag{left:8px;right:8px;width:auto;bottom:8px;max-height:150px}
}
</style>
<div id="site-order-runtime-diag"><b>DIAG SITE/CUISINE :</b> chargement…</div>
<script id="site-order-runtime-diag">
(function(){
 const el=document.getElementById('site-order-runtime-diag');
 if(!el)return;
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const euro=v=>Number(v||0).toFixed(2).replace('.',',')+' €';
 async function load(){
   try{
     const r=await fetch('/api/diag/site-orders-runtime',{cache:'no-store'});
     const d=await r.json();
     if(!r.ok||!d.ok)throw new Error(d.error||'Erreur DIAG');
     if(!d.orders.length){
       el.innerHTML='<b>DIAG SITE/CUISINE :</b> aucune commande SITE trouvée';
       return;
     }
     el.innerHTML='<b>DIAG SITE/CUISINE</b><br>'+d.orders.map(o=>{
       const kitchen=o.should_be_on_kitchen_board
         ? '<span class="good">CUISINE: OUI</span>'
         : '<span class="bad">CUISINE: NON</span>';
       return '#'+esc(o.num)+' · '+esc(o.customer_name||'Client')
         +' · <b>status='+esc(o.status||'(vide)')+'</b>'
         +' · paiement='+esc(o.payment_status||'(vide)')
         +' '+esc(o.payment_method||'')
         +' · '+euro(o.total)
         +' · source='+esc(o.source||'(vide)')
         +' · channel='+esc(o.sales_channel||'(vide)')
         +' · '+kitchen;
     }).join('<br>');
   }catch(e){
     el.innerHTML='<b>DIAG SITE/CUISINE :</b> <span class="bad">'+esc(e.message)+'</span>';
   }
 }
 load();setInterval(load,4000);
})();
</script>
"""
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
