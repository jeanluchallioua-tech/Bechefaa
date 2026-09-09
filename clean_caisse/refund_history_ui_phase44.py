"""Phase 4.4 — protection isolée des remboursements dans Historique.

Aucune écriture financière. Un endpoint groupé retourne les montants remboursés.
Pour les commandes remboursées, le bouton Encaisser hérité de Phase 4.3 reste
neutralisé sans être supprimé du DOM. Le badge de remboursement n'est plus
affiché : le détail est disponible via l'action Rembourser.
"""
from flask import jsonify, request


def register_refund_history_ui_phase44(app, db):
    @app.get("/api/orders/refund-meta-phase44")
    def refund_meta_phase44():
        try:
            with db() as conn:
                rows = conn.execute("""
                    SELECT o.id,
                           o.num,
                           o.payment_status,
                           o.payment_method,
                           COALESCE(SUM(CASE WHEN t.transaction_type='PAYMENT' AND t.status='SUCCEEDED' THEN t.amount ELSE 0 END),0) AS paid,
                           COALESCE(SUM(CASE WHEN t.transaction_type='REFUND' AND t.status='SUCCEEDED' THEN t.amount ELSE 0 END),0) AS refunded,
                           COALESCE(SUM(CASE WHEN t.transaction_type='REFUND' AND t.status='PENDING_EXTERNAL' THEN t.amount ELSE 0 END),0) AS pending_refund
                    FROM caisse_orders o
                    LEFT JOIN caisse_payment_transactions t ON t.order_id=o.id
                    WHERE COALESCE(o.cancellation_hidden,FALSE)=FALSE
                      AND UPPER(COALESCE(o.status,'')) <> 'ANNULÉE'
                      AND (to_timestamp(o.created_at / 1000.0) AT TIME ZONE 'Europe/Paris')::date
                          = (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Paris')::date
                    GROUP BY o.id,o.num,o.payment_status,o.payment_method,o.created_at
                    HAVING COALESCE(SUM(CASE WHEN t.transaction_type='REFUND' AND t.status IN ('SUCCEEDED','PENDING_EXTERNAL') THEN t.amount ELSE 0 END),0) > 0
                    ORDER BY o.created_at DESC
                """).fetchall()
            return jsonify({"ok": True, "orders": {
                str(r["id"]): {
                    "id": r["id"], "num": r["num"],
                    "payment_status": r["payment_status"], "payment_method": r["payment_method"],
                    "paid": float(r["paid"] or 0), "refunded": float(r["refunded"] or 0),
                    "pending_refund": float(r["pending_refund"] or 0),
                    "net_paid": round(float(r["paid"] or 0)-float(r["refunded"] or 0),2),
                } for r in rows
            }})
        except Exception as exc:
            return jsonify({"ok": False, "error": "Métadonnées remboursement indisponibles", "detail": str(exc)}), 500

    @app.after_request
    def inject_refund_history_ui_phase44(response):
        if request.path != "/historique-modification" or response.status_code != 200 or response.mimetype != "text/html":
            return response
        html = response.get_data(as_text=True)
        addon = r'''
<style id="p44-refund-ui-style">
.p41-pay-btn[data-p44-refund-locked="1"]{display:none!important}
</style>
<script id="p44-refund-ui-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 function orderId(card){
   const buttons=[...card.querySelectorAll('button')];
   for(const b of buttons){const oc=b.getAttribute('onclick')||'';let m=oc.match(/editOrder\('([^']+)'\)/);if(!m)m=oc.match(/viewOrder\('([^']+)'\)/);if(m)return m[1]}
   const a=card.querySelector('a[href*="/impression/client/"]');
   if(a){const m=a.getAttribute('href').match(/\/impression\/client\/([^/?#]+)/);if(m)return decodeURIComponent(m[1])}
   return null;
 }
 ready(function(){
   let data={};let timer=null;
   async function load(){try{const r=await fetch('/api/orders/refund-meta-phase44',{cache:'no-store'});const d=await r.json();if(r.ok&&d.ok)data=d.orders||{}}catch(e){}}
   function decorate(){
     for(const card of document.querySelectorAll('#list .order')){
       const id=orderId(card);if(!id||!data[id])continue;
       card.querySelectorAll('.p41-pay-btn').forEach(b=>{b.disabled=true;b.setAttribute('data-p44-refund-locked','1')});
       card.querySelectorAll('.p41-paid-badge').forEach(b=>b.remove());
       card.querySelectorAll('.p44-refund-badge').forEach(b=>b.remove());
     }
   }
   function schedule(){clearTimeout(timer);timer=setTimeout(decorate,100)}
   (async()=>{await load();decorate();const list=document.getElementById('list');if(list)new MutationObserver(schedule).observe(list,{childList:true,subtree:true})})();
 });
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
