"""Phase 4.4 — interface d'annulation et masquage commercial.

Les commandes annulées restent en base pour audit mais sont retirées de
l'historique commercial. Le bouton Annuler n'est proposé qu'aux commandes
non payées ; le backend reste l'autorité finale.
"""
from flask import request


def register_order_cancellation_ui_phase44(app):
    @app.after_request
    def cancellation_ui_phase44(response):
        # Masque les commandes annulées de l'historique commercial normal.
        if request.path == "/api/orders/history" and response.status_code == 200 and response.is_json:
            try:
                data = response.get_json(silent=True) or {}
                if data.get("ok") and isinstance(data.get("orders"), list):
                    orders = [o for o in data["orders"] if str(o.get("status") or "").upper() != "ANNULÉE"]
                    data["orders"] = orders
                    data["count"] = len(orders)
                    response.set_data(app.json.dumps(data))
                    response.content_type = "application/json"
                    response.content_length = len(response.get_data())
            except Exception:
                pass
            return response

        if request.path != "/historique-modification" or response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        addon = r'''
<style id="phase44-cancel-ui">
.p44-cancel-btn{border:0;border-radius:8px;padding:10px 12px;font-weight:900;font-size:12px;color:#fff;background:#b42318;cursor:pointer;margin-top:7px}
.p44-cancel-btn:disabled{opacity:.55;cursor:not-allowed}
</style>
<script id="phase44-cancel-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 function orderId(card){
   const buttons=[...card.querySelectorAll('button')];
   for(const b of buttons){
     const oc=b.getAttribute('onclick')||'';
     let m=oc.match(/editOrder\('([^']+)'\)/);if(!m)m=oc.match(/viewOrder\('([^']+)'\)/);
     if(m)return m[1];
   }
   return null;
 }
 ready(function(){
   async function cancelOrder(card,id,btn){
     if(!confirm('Annuler cette commande non payée ?'))return;
     btn.disabled=true;
     try{
       const r=await fetch('/api/orders/'+encodeURIComponent(id)+'/cancel-phase44',{method:'POST'});
       const d=await r.json();
       if(!r.ok||!d.ok)throw new Error(d.error||'Annulation impossible');
       card.remove();
       if(typeof load==='function')setTimeout(()=>load(),100);
     }catch(e){alert(e.message||'Annulation impossible');btn.disabled=false}
   }
   async function decorate(){
     const cards=[...document.querySelectorAll('#list .order')];
     for(const card of cards){
       if(card.querySelector('.p44-cancel-btn')||card.dataset.p44CancelLoading==='1')continue;
       const id=orderId(card);if(!id)continue;card.dataset.p44CancelLoading='1';
       try{
         const d=await fetch('/api/orders/'+encodeURIComponent(id)+'/payment-phase41',{cache:'no-store'}).then(r=>r.json());
         if(!d.ok||!d.order)continue;
         const ps=String(d.order.payment_status||'').toUpperCase();
         const paid=Number(d.order.paid_amount||0)>0 || ps==='PAYÉE' || ps==='REMBOURSÉE' || ps==='PARTIELLEMENT REMBOURSÉE';
         if(paid||d.order.z_locked)continue;
         const btn=document.createElement('button');btn.type='button';btn.className='p44-cancel-btn';btn.textContent='✕ Annuler';btn.addEventListener('click',()=>cancelOrder(card,id,btn));card.appendChild(btn);
       }catch(e){}finally{delete card.dataset.p44CancelLoading}
     }
   }
   setTimeout(decorate,0);
   const list=document.getElementById('list');if(list)new MutationObserver(()=>setTimeout(decorate,40)).observe(list,{childList:true,subtree:true});
 });
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
