"""Phase 4.4 — affichage du numéro de ticket comptable dans l'historique.

Extension visuelle isolée. Les métadonnées sont chargées en une seule requête
groupée partagée avec l'interface d'annulation.
"""
from flask import request


def register_fiscal_ticket_ui_phase44(app):
    @app.after_request
    def inject_fiscal_ticket_ui_phase44(response):
        if request.path != "/historique-modification" or response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        addon = r'''
<style id="phase44-fiscal-ticket-ui">
.p44-ticket-badge{display:inline-flex;align-items:center;border-radius:999px;padding:7px 10px;font-weight:900;font-size:12px;color:#1e3a8a;background:#dbeafe;border:1px solid #93c5fd;margin-top:7px;margin-left:6px}
</style>
<script id="phase44-fiscal-ticket-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 function orderId(card){
   const buttons=[...card.querySelectorAll('button')];
   for(const b of buttons){
     const oc=b.getAttribute('onclick')||'';
     let m=oc.match(/editOrder\('([^']+)'\)/);if(!m)m=oc.match(/viewOrder\('([^']+)'\)/);
     if(m)return m[1];
   }
   const a=card.querySelector('a[href*="/impression/client/"]');
   if(a){const m=a.getAttribute('href').match(/\/impression\/client\/([^/?#]+)/);if(m)return decodeURIComponent(m[1])}
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
   async function decorate(){
     const cards=[...document.querySelectorAll('#list .order')];
     if(!cards.length)return;
     const all=await meta();
     for(const card of cards){
       const id=orderId(card);if(!id)continue;
       const d=all[id];if(!d)continue;
       let badge=card.querySelector('.p44-ticket-badge');
       if(d.fiscal_ticket_number!=null){
         if(!badge){badge=document.createElement('span');badge.className='p44-ticket-badge';card.appendChild(badge)}
         badge.textContent='Ticket comptable #'+d.fiscal_ticket_number;
       }else if(badge){badge.remove()}
     }
   }
   setTimeout(decorate,100);
   const list=document.getElementById('list');
   if(list)new MutationObserver(()=>setTimeout(decorate,80)).observe(list,{childList:true,subtree:true});
 })
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
