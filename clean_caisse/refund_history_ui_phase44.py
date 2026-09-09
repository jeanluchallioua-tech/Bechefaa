"""Phase 4.4 — affichage isolé des remboursements dans Historique.

Aucune écriture financière. Un endpoint groupé retourne les montants remboursés,
puis un after_request ajoute un badge aux cartes concernées.
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
                    "id": r["id"],
                    "num": r["num"],
                    "payment_status": r["payment_status"],
                    "payment_method": r["payment_method"],
                    "paid": float(r["paid"] or 0),
                    "refunded": float(r["refunded"] or 0),
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
.p44-refund-badge{display:block;margin-top:7px;padding:8px 10px;border-radius:10px;background:#fff7ed;border:1px solid #fdba74;color:#9a3412;font-size:12px;font-weight:900;line-height:1.45}
.p44-refund-badge strong{display:block;font-size:12px;margin-bottom:2px}
</style>
<script id="p44-refund-ui-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 function euro(v){return Number(v||0).toFixed(2).replace('.',',')+' €'}
 function orderId(card){
   const buttons=[...card.querySelectorAll('button')];
   for(const b of buttons){const oc=b.getAttribute('onclick')||'';let m=oc.match(/editOrder\('([^']+)'\)/);if(!m)m=oc.match(/viewOrder\('([^']+)'\)/);if(m)return m[1]}
   const a=card.querySelector('a[href*="/impression/client/"]');
   if(a){const m=a.getAttribute('href').match(/\/impression\/client\/([^/?#]+)/);if(m)return decodeURIComponent(m[1])}
   return null;
 }
 ready(async function(){
   let data={};
   try{const r=await fetch('/api/orders/refund-meta-phase44',{cache:'no-store'});const d=await r.json();if(!r.ok||!d.ok)return;data=d.orders||{}}catch(e){return}
   for(const card of document.querySelectorAll('#list .order')){
     const id=orderId(card);if(!id||!data[id])continue;
     const o=data[id];let badge=card.querySelector('.p44-refund-badge');if(!badge){badge=document.createElement('div');badge.className='p44-refund-badge';card.appendChild(badge)}
     const pending=Number(o.pending_refund||0);
     badge.innerHTML='<strong>'+String(o.payment_status||'REMBOURSEMENT')+' · '+String(o.payment_method||'')+'</strong>'+
       'Payé '+euro(o.paid)+' · Remboursé '+euro(o.refunded)+' · Net '+euro(o.net_paid)+(pending>0?' · En attente '+euro(pending):'');
   }
 });
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
