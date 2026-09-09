"""Phase 4.4 — affichage du numéro de ticket comptable dans l'historique.

Extension visuelle isolée : aucune modification de l'interface d'encaissement
Phase 4.3. Le badge apparaît uniquement lorsqu'un numéro comptable existe.
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
 ready(function(){
   async function decorate(){
     const cards=[...document.querySelectorAll('#list .order')];
     for(const card of cards){
       if(card.dataset.p44TicketLoading==='1')continue;
       const id=orderId(card);if(!id)continue;
       card.dataset.p44TicketLoading='1';
       try{
         const r=await fetch('/api/orders/'+encodeURIComponent(id)+'/payment-phase41',{cache:'no-store'});
         const d=await r.json();
         if(!r.ok||!d.ok||!d.order)continue;
         let badge=card.querySelector('.p44-ticket-badge');
         if(d.order.fiscal_ticket_number!=null){
           if(!badge){badge=document.createElement('span');badge.className='p44-ticket-badge';card.appendChild(badge)}
           badge.textContent='Ticket comptable #'+d.order.fiscal_ticket_number;
         }else if(badge){badge.remove()}
       }catch(e){}finally{delete card.dataset.p44TicketLoading}
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
