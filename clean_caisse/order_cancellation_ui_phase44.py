"""Phase 4.4 — interface d'annulation et masquage commercial.

Les commandes annulées restent en base pour audit mais sont retirées de
l'historique commercial. Les métadonnées sont chargées en une seule requête
groupée pour éviter un appel réseau par commande.
"""
from flask import request


def register_order_cancellation_ui_phase44(app):
    @app.after_request
    def cancellation_ui_phase44(response):
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
 function meta(){
   const now=Date.now();
   if(window.__p44HistoryMetaPromise && now-(window.__p44HistoryMetaAt||0)<1500)return window.__p44HistoryMetaPromise;
   window.__p44HistoryMetaAt=now;
   window.__p44HistoryMetaPromise=fetch('/api/orders/history-meta-phase44',{cache:'no-store'})
     .then(r=>r.json()).then(d=>(d&&d.ok&&d.orders)?d.orders:{}).catch(()=>({}));
   return window.__p44HistoryMetaPromise;
 }
 ready(function(){
   async function cancelOrder(card,id,btn){
     if(!confirm('Annuler cette commande non payée ?'))return;
     btn.disabled=true;
     try{
       const r=await fetch('/api/orders/'+encodeURIComponent(id)+'/cancel-phase44',{method:'POST'});
       const d=await r.json();
       if(!r.ok||!d.ok)throw new Error(d.error||'Annulation impossible');
       card.remove();window.__p44HistoryMetaAt=0;window.__p44HistoryMetaPromise=null;
       if(typeof load==='function')setTimeout(()=>load(),100);
     }catch(e){alert(e.message||'Annulation impossible');btn.disabled=false}
   }
   async function decorate(){
     const cards=[...document.querySelectorAll('#list .order')];
     if(!cards.length)return;
     const all=await meta();
     for(const card of cards){
       if(card.querySelector('.p44-cancel-btn'))continue;
       const id=orderId(card);if(!id)continue;
       const d=all[id];if(!d)continue;
       const ps=String(d.payment_status||'').toUpperCase();
       const paid=Number(d.paid_amount||0)>0 || ps==='PAYÉE' || ps==='REMBOURSÉE' || ps==='PARTIELLEMENT REMBOURSÉE';
       if(paid||d.z_locked)continue;
       const btn=document.createElement('button');btn.type='button';btn.className='p44-cancel-btn';btn.textContent='✕ Annuler';btn.addEventListener('click',()=>cancelOrder(card,id,btn));card.appendChild(btn);
     }
   }
   setTimeout(decorate,0);
   const list=document.getElementById('list');if(list)new MutationObserver(()=>setTimeout(decorate,60)).observe(list,{childList:true,subtree:true});
 });
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
