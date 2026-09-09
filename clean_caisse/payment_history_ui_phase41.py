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
.p41-paid-badge{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:7px 10px;font-weight:900;font-size:12px;color:#166534;background:#dcfce7;border:1px solid #86efac;margin-top:7px}
</style>
<script>
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 function euro(v){return Number(v||0).toFixed(2).replace('.',',')+' €'}
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
 function showPaid(card,payment){
   card.querySelectorAll('.p41-pay-btn').forEach(x=>x.remove());
   let badge=card.querySelector('.p41-paid-badge');
   if(!badge){badge=document.createElement('span');badge.className='p41-paid-badge';card.appendChild(badge)}
   const method=payment.payment_method||payment.payment||'Paiement';
   badge.textContent='✓ PAYÉE · '+method+' · '+euro(payment.paid_amount||payment.total);
 }
 async function pay(card,id,btn){
   btn.disabled=true;
   try{
     const s=await fetch('/api/orders/'+encodeURIComponent(id)+'/payment-phase41',{cache:'no-store'}).then(r=>r.json());
     if(!s.ok)throw new Error(s.error||'Encaissement indisponible');
     if(s.order.z_locked){alert('Commande clôturée par le Z : encaissement interdit');return}
     if(s.order.payment_status==='PAYÉE'){alert('Commande déjà payée par '+(s.order.payment_method||'paiement'));showPaid(card,s.order);return}
     const choice=prompt('Encaisser commande #'+s.order.num+' — '+euro(s.order.total)+'\n\nTapez :\n1 = Espèces\n2 = CB');
     if(choice===null)return;
     let payload={};
     if(String(choice).trim()==='1'){
       const received=prompt('Total : '+euro(s.order.total)+'\n\nMontant reçu en espèces (€) :',Number(s.order.total||0).toFixed(2));
       if(received===null)return;
       payload={method:'ESPÈCES',received:String(received).replace(',','.')};
     }else if(String(choice).trim()==='2'){
       payload={method:'CB'};
     }else{alert('Choix invalide. Tapez 1 pour Espèces ou 2 pour CB.');return}
     const res=await fetch('/api/orders/'+encodeURIComponent(id)+'/payment-phase41',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
     const d=await res.json();
     if(!res.ok||!d.ok)throw new Error(d.error||'Encaissement impossible');
     let msg='Commande #'+d.num+' encaissée\n\nTotal : '+euro(d.paid_amount);
     if(d.payment_method==='ESPÈCES'){
       msg+='\nReçu : '+euro(d.cash_received)+'\nÀ rendre : '+euro(d.change_due)+'\nEncaissé : '+euro(d.paid_amount)+' — Espèces';
     }else{
       msg+='\nEncaissé : '+euro(d.paid_amount)+' — '+d.payment_method;
     }
     alert(msg);
     showPaid(card,d);
   }catch(e){alert(e.message||'Encaissement impossible')}
   finally{if(btn&&btn.isConnected)btn.disabled=false}
 }
 async function decorate(){
   const cards=[...document.querySelectorAll('#list .order')];
   for(const card of cards){
     const existing=[...card.querySelectorAll('.p41-pay-btn')];
     if(existing.length>1)existing.slice(1).forEach(x=>x.remove());
     const paidBadges=[...card.querySelectorAll('.p41-paid-badge')];
     if(paidBadges.length>1)paidBadges.slice(1).forEach(x=>x.remove());
     if(card.dataset.p41PaymentLoading==='1')continue;
     const id=orderId(card);if(!id)continue;
     card.dataset.p41PaymentLoading='1';
     try{
       const d=await fetch('/api/orders/'+encodeURIComponent(id)+'/payment-phase41',{cache:'no-store'}).then(r=>r.json());
       if(!d.ok||!d.order)continue;
       if(d.order.payment_status==='PAYÉE'){
         showPaid(card,d.order);
         continue;
       }
       card.querySelectorAll('.p41-paid-badge').forEach(x=>x.remove());
       if(d.order.z_locked)continue;
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
