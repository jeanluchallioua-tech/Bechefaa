"""Phase 4.1 — interface d'encaissement isolée dans Historique.

Ajoute un bouton Encaisser aux commandes encore à encaisser. Le backend
payment_core_phase41 reste l'unique source de vérité pour l'encaissement.
"""
from flask import request


def register_payment_history_ui_phase41(app):
    @app.after_request
    def inject_payment_history_ui_phase41(response):
        if request.path != "/historique-modification" or response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        addon = r'''
<style>
.p41-pay-btn{border:0;border-radius:8px;padding:10px 12px;font-weight:900;font-size:12px;color:#fff;background:#16a34a;cursor:pointer;margin-top:7px}
.p41-pay-btn:disabled{opacity:.55;cursor:not-allowed}
</style>
<script>
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 function orderId(card){
   const buttons=[...card.querySelectorAll('button')];
   for(const b of buttons){
     const oc=b.getAttribute('onclick')||'';
     let m=oc.match(/editOrder\('([^']+)'\)/); if(!m)m=oc.match(/viewOrder\('([^']+)'\)/);
     if(m)return m[1];
   }
   const a=card.querySelector('a[href*="/impression/client/"]');
   if(a){const m=a.getAttribute('href').match(/\/impression\/client\/([^/?#]+)/);if(m)return decodeURIComponent(m[1])}
   return null;
 }
 async function pay(card,id,btn){
   btn.disabled=true;
   try{
     const s=await fetch('/api/orders/'+encodeURIComponent(id)+'/payment-phase41',{cache:'no-store'}).then(r=>r.json());
     if(!s.ok)throw new Error(s.error||'Encaissement indisponible');
     if(s.order.z_locked){alert('Commande clôturée par le Z : encaissement interdit');return}
     if(s.order.payment_status==='PAYÉE'){alert('Commande déjà payée par '+(s.order.payment_method||'paiement'));btn.remove();return}
     const choice=prompt('Encaisser commande #'+s.order.num+' — '+Number(s.order.total||0).toFixed(2)+' €\n\nTapez :\n1 = Espèces\n2 = CB');
     if(choice===null)return;
     let payload={};
     if(String(choice).trim()==='1'){
       const received=prompt('Montant reçu en espèces (€) :',Number(s.order.total||0).toFixed(2));
       if(received===null)return;
       payload={method:'ESPÈCES',received:String(received).replace(',','.')};
     }else if(String(choice).trim()==='2'){
       payload={method:'CB'};
     }else{alert('Choix invalide. Tapez 1 pour Espèces ou 2 pour CB.');return}
     const res=await fetch('/api/orders/'+encodeURIComponent(id)+'/payment-phase41',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
     const d=await res.json();
     if(!res.ok||!d.ok)throw new Error(d.error||'Encaissement impossible');
     let msg='Commande #'+d.num+' encaissée — '+d.payment_method+' — '+Number(d.paid_amount||0).toFixed(2)+' €';
     if(d.payment_method==='ESPÈCES')msg+='\nMonnaie à rendre : '+Number(d.change_due||0).toFixed(2)+' €';
     alert(msg);
     card.querySelectorAll('.p41-pay-btn').forEach(x=>x.remove());
   }catch(e){alert(e.message||'Encaissement impossible')}
   finally{if(btn&&btn.isConnected)btn.disabled=false}
 }
 async function decorate(){
   const cards=[...document.querySelectorAll('#list .order')];
   for(const card of cards){
     const existing=[...card.querySelectorAll('.p41-pay-btn')];
     if(existing.length){existing.slice(1).forEach(x=>x.remove());continue}
     if(card.dataset.p41PaymentLoading==='1')continue;
     const id=orderId(card);if(!id)continue;
     card.dataset.p41PaymentLoading='1';
     try{
       const d=await fetch('/api/orders/'+encodeURIComponent(id)+'/payment-phase41',{cache:'no-store'}).then(r=>r.json());
       if(!d.ok||!d.order||d.order.z_locked||d.order.payment_status==='PAYÉE')continue;
       if(card.querySelector('.p41-pay-btn'))continue;
       const btn=document.createElement('button');btn.type='button';btn.className='p41-pay-btn';btn.textContent='💳 Encaisser';
       btn.addEventListener('click',()=>pay(card,id,btn));card.appendChild(btn);
     }catch(e){}
     finally{delete card.dataset.p41PaymentLoading}
   }
 }
 ready(function(){setTimeout(decorate,0);const list=document.getElementById('list');if(list)new MutationObserver(()=>setTimeout(decorate,50)).observe(list,{childList:true,subtree:true})});
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
