"""Diagnostic read-only des commandes récentes BÉCHÉFAA.

Permet de vérifier rapidement les écarts Historique / Cuisine / Encaissement
sans modifier aucune commande.
"""
from flask import jsonify, redirect


def register_orders_live_diag_phase6(app, db, ensure_order_schema):
    @app.get("/api/orders/live-diagnostic-phase6")
    def orders_live_diagnostic_phase6():
        try:
            with db() as conn:
                ensure_order_schema(conn)
                rows=conn.execute("""
                    SELECT o.id,o.num,o.table_number,o.table_label,o.customer_name,
                           o.source,o.status,o.payment,o.total,o.created_at,o.updated_at,
                           COALESCE(o.payment_status,'') AS payment_status,
                           COALESCE(o.paid_amount,0) AS paid_amount,
                           COUNT(i.id) AS item_count
                    FROM caisse_orders o
                    LEFT JOIN caisse_order_items i ON i.order_id=o.id
                    GROUP BY o.id,o.num,o.table_number,o.table_label,o.customer_name,
                             o.source,o.status,o.payment,o.total,o.created_at,o.updated_at,
                             o.payment_status,o.paid_amount
                    ORDER BY o.created_at DESC
                    LIMIT 20
                """).fetchall()
            return jsonify({
                "ok":True,
                "read_only":True,
                "orders":[{
                    "id":r["id"],"num":r["num"],
                    "table_number":r.get("table_number"),
                    "table_label":r.get("table_label"),
                    "customer_name":r.get("customer_name"),
                    "source":r.get("source"),
                    "status":r.get("status"),
                    "payment":r.get("payment"),
                    "payment_status":r.get("payment_status"),
                    "paid_amount":float(r.get("paid_amount") or 0),
                    "total":float(r.get("total") or 0),
                    "item_count":int(r.get("item_count") or 0),
                    "created_at":r.get("created_at"),
                    "updated_at":r.get("updated_at"),
                    "visible_in_kitchen":r.get("status") in ("À préparer","En préparation"),
                } for r in rows]
            })
        except Exception as exc:
            return jsonify({"ok":False,"error":"Diagnostic commandes indisponible","detail":str(exc)}),500


    @app.post("/api/orders/<order_id>/repair-kitchen-phase6")
    def repair_kitchen_phase6(order_id):
        """Répare uniquement une commande restée Enregistrée après création."""
        try:
            with db() as conn:
                with conn.transaction():
                    ensure_order_schema(conn)
                    row=conn.execute(
                        "SELECT id,num,status,table_number,table_label FROM caisse_orders WHERE id=%s FOR UPDATE",
                        (order_id,),
                    ).fetchone()
                    if not row:
                        return jsonify({"ok":False,"error":"Commande introuvable"}),404
                    if row["status"] in ("À préparer","En préparation"):
                        return jsonify({"ok":True,"already_visible":True,"id":row["id"],"num":row["num"],"status":row["status"]})
                    if row["status"]!="Enregistrée":
                        return jsonify({"ok":False,"error":"Réparation refusée pour ce statut","status":row["status"]}),409
                    conn.execute(
                        "UPDATE caisse_orders SET status='À préparer',updated_at=(EXTRACT(EPOCH FROM clock_timestamp())*1000)::bigint WHERE id=%s",
                        (order_id,),
                    )
            return jsonify({
                "ok":True,"repaired":True,"id":row["id"],"num":row["num"],
                "status":"À préparer","table_number":row.get("table_number"),"table_label":row.get("table_label")
            })
        except Exception as exc:
            return jsonify({"ok":False,"error":"Réparation cuisine impossible","detail":str(exc)}),500


    @app.get("/orders/<order_id>/repair-kitchen-phase6")
    def repair_kitchen_phase6_navigation(order_id):
        """Même réparation, via navigation classique sans fetch JavaScript."""
        try:
            with db() as conn:
                with conn.transaction():
                    ensure_order_schema(conn)
                    row=conn.execute(
                        "SELECT id,status FROM caisse_orders WHERE id=%s FOR UPDATE",
                        (order_id,),
                    ).fetchone()
                    if not row:
                        return "Commande introuvable",404
                    if row["status"]=="Enregistrée":
                        conn.execute(
                            "UPDATE caisse_orders SET status='À préparer',updated_at=(EXTRACT(EPOCH FROM clock_timestamp())*1000)::bigint WHERE id=%s",
                            (order_id,),
                        )
                    elif row["status"] not in ("À préparer","En préparation"):
                        return "Cette commande ne peut pas être envoyée en cuisine depuis cet écran.",409
            return redirect("/historique-modification",code=303)
        except Exception as exc:
            return "Envoi cuisine impossible : "+str(exc),500

    @app.after_request
    def inject_kitchen_repair_ui_phase6(response):
        from flask import request
        if request.path!="/historique-modification" or response.status_code!=200 or response.mimetype!="text/html":
            return response
        html=response.get_data(as_text=True)
        addon=r"""
<style id="bechefaa-kitchen-repair-ui-phase6">
.kitchen-repair-btn{border:0;border-radius:8px;padding:10px 12px;font-weight:900;font-size:12px;color:#fff;background:#d97706;cursor:pointer;margin-left:6px}
</style>
<script id="bechefaa-kitchen-repair-script-phase6">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 function oid(card){for(const b of card.querySelectorAll('button')){const s=b.getAttribute('onclick')||'';let m=s.match(/viewOrder\('([^']+)'\)/);if(!m)m=s.match(/editOrder\('([^']+)'\)/);if(m)return m[1]}return ''}
 function decorate(){
   if(typeof ORDERS==='undefined')return;
   document.querySelectorAll('#list .order').forEach(card=>{
     if(card.querySelector('.kitchen-repair-btn'))return;
     const id=oid(card),o=ORDERS.find(x=>x.id===id);
     if(!o||o.status!=='Enregistrée')return;
     const b=document.createElement('button');b.type='button';b.className='kitchen-repair-btn';b.textContent='Envoyer en cuisine';
     b.onclick=()=>{window.location.href='/orders/'+encodeURIComponent(id)+'/repair-kitchen-phase6'};
     card.appendChild(b);
   });
 }
 ready(()=>{decorate();const t=document.getElementById('list')||document.body;new MutationObserver(decorate).observe(t,{childList:true,subtree:true})});
})();
</script>
"""
        html=html.replace("</body>",addon+"</body>")
        response.set_data(html);response.content_length=len(response.get_data())
        return response
