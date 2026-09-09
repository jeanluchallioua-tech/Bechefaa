"""Phase 4.3 — interface tactile d'encaissement dans Historique.

Le backend payment_core_phase41 reste l'unique source de vérité.
Cette phase remplace seulement les prompt() par une fenêtre tactile et expose
les quatre moyens déjà supportés par le socle : Espèces, CB, Chèque, Virement.
Le chargement des états de paiement utilise désormais les métadonnées groupées
Phase 4.4 afin d'éviter une requête HTTP par commande affichée.
"""
from flask import request


def register_payment_history_ui_phase41(app):
    @app.after_request
    def inject_payment_history_ui_phase41(response):
        if request.path != "/historique-modification" or response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        addon = r'''
<style id="phase43-payment-ui">
.p41-pay-btn{border:0;border-radius:8px;padding:10px 12px;font-weight:900;font-size:12px;color:#fff;background:#16a34a;cursor:pointer;margin-top:7px}
.p41-pay-btn:disabled{opacity:.55;cursor:not-allowed}
.p41-paid-badge{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:7px 10px;font-weight:900;font-size:12px;color:#166534;background:#dcfce7;border:1px solid #86efac;margin-top:7px}
.p43-overlay{display:none;position:fixed;inset:0;z-index:20000;background:#0009;padding:18px;align-items:center;justify-content:center}
.p43-overlay.open{display:flex}
.p43-modal{width:min(560px,96vw);max-height:92vh;overflow:auto;background:#fff;border-radius:18px;padding:20px;box-shadow:0 24px 70px #0007}
.p43-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:14px}
.p43-head h2{margin:0;font-size:22px}.p43-head p{margin:4px 0 0;color:#667085;font-weight:700}
.p43-close{border:0;background:#eef1f4;border-radius:9px;width:42px;height:42px;font-size:24px;font-weight:900;cursor:pointer}
.p43-total{font-size:28px;font-weight:950;text-align:center;padding:14px;background:#f7f8fa;border-radius:12px;margin-bottom:14px}
.p43-methods{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.p43-method{min-height:68px;border:2px solid #d0d5dd;border-radius:12px;background:#fff;font-size:17px;font-weight:900;cursor:pointer}
.p43-method.active{border-color:#111827;background:#111827;color:#fff}
.p43-cash{display:none;margin-top:14px;padding:14px;border:1px solid #e4e7ec;border-radius:12px;background:#fafafa}
.p43-cash.show{display:block}.p43-cash label{display:block;font-weight:900;margin-bottom:7px}.p43-cash input{width:100%;box-sizing:border-box;min-height:52px;border:1px solid #cfd4dc;border-radius:9px;padding:10px;font-size:20px;font-weight:800}
.p43-change{margin-top:10px;font-weight:900;font-size:16px}.p43-error{min-height:22px;color:#b42318;font-weight:800;margin-top:10px}
.p43-actions{display:flex;gap:10px;margin-top:14px}.p43-actions button{flex:1;min-height:52px;border:0;border-radius:10px;font-size:16px;font-weight:900;cursor:pointer}.p43-cancel{background:#eef1f4}.p43-confirm{background:#16a34a;color:#fff}.p43-confirm:disabled{opacity:.55;cursor:not-allowed}
@media(max-width:520px){.p43-methods{grid-template-columns:1fr}.p43-modal{padding:15px}.p43-total{font-size:24px}}
</style>
<div id="p43-overlay" class="p43-overlay" aria-hidden="true">
  <div class="p43-modal" role="dialog" aria-modal="true" aria-labelledby="p43-title">
    <div class="p43-head"><div><h2 id="p43-title">Encaisser</h2><p id="p43-order"></p></div><button type="button" class="p43-close" aria-label="Fermer">×</button></div>
    <div id="p43-total" class="p43-total">0,00 €</div>
    <div class="p43-methods">
      <button type="button" class="p43-method" data-method="ESPÈCES">💶 Espèces</button>
      <button type="button" class="p43-method" data-method="CB">💳 Carte bancaire</button>
      <button type="button" class="p43-method" data-method="CHÈQUE">🧾 Chèque</button>
      <button type="button" class="p43-method" data-method="VIREMENT">🏦 Virement</button>
    </div>
    <div id="p43-cash" class="p43-cash"><label for="p43-received">Montant reçu</label><input id="p43-received" inputmode="decimal" autocomplete="off"><div id="p43-change" class="p43-change"></div></div>
    <div id="p43-error" class="p43-error"></div>
    <div class="p43-actions"><button type="button" class="p43-cancel">Annuler</button><button type="button" id="p43-confirm" class="p43-confirm" disabled>Valider l’encaissement</button></div>
  </div>
</div>
<script id="phase43-payment-script">
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
 ready(function(){
   const overlay=document.getElementById('p43-overlay'),totalEl=document.getElementById('p43-total'),orderEl=document.getElementById('p43-order'),cashBox=document.getElementById('p43-cash'),received=document.getElementById('p43-received'),changeEl=document.getElementById('p43-change'),errorEl=document.getElementById('p43-error'),confirmBtn=document.getElementById('p43-confirm');
   if(!overlay)return;
   let current=null,method=null,decorateTimer=null;
   function close(){overlay.classList.remove('open');overlay.setAttribute('aria-hidden','true');current=null;method=null;document.querySelectorAll('.p43-method').forEach(b=>b.classList.remove('active'));cashBox.classList.remove('show');received.value='';changeEl.textContent='';errorEl.textContent='';confirmBtn.disabled=true}
   function calcChange(){if(!current||method!=='ESPÈCES')return;const v=Number(String(received.value||'').replace(',','.'));const t=Number(current.order.total||0);changeEl.textContent=Number.isFinite(v)?(v>=t?'À rendre : '+euro(v-t):'Il manque : '+euro(t-v)):''}
   document.querySelector('.p43-close').onclick=close;document.querySelector('.p43-cancel').onclick=close;overlay.addEventListener('click',e=>{if(e.target===overlay)close()});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&overlay.classList.contains('open'))close()});received.addEventListener('input',calcChange);
   document.querySelectorAll('.p43-method').forEach(btn=>btn.addEventListener('click',()=>{method=btn.dataset.method;document.querySelectorAll('.p43-method').forEach(b=>b.classList.toggle('active',b===btn));cashBox.classList.toggle('show',method==='ESPÈCES');errorEl.textContent='';confirmBtn.disabled=false;if(method==='ESPÈCES'){received.value=Number(current.order.total||0).toFixed(2);calcChange();setTimeout(()=>received.focus(),30)}}));
   async function openPayment(card,id,btn){
     btn.disabled=true;
     try{
       const s=await fetch('/api/orders/'+encodeURIComponent(id)+'/payment-phase41',{cache:'no-store'}).then(r=>r.json());
       if(!s.ok)throw new Error(s.error||'Encaissement indisponible');
       if(s.order.z_locked){alert('Commande clôturée par le Z : encaissement interdit');return}
       if(s.order.payment_status==='PAYÉE'){showPaid(card,s.order);return}
       current={card,id,order:s.order,button:btn};method=null;orderEl.textContent='Commande #'+s.order.num;totalEl.textContent=euro(s.order.total);overlay.classList.add('open');overlay.setAttribute('aria-hidden','false');
     }catch(e){alert(e.message||'Encaissement impossible')}
     finally{btn.disabled=false}
   }
   confirmBtn.addEventListener('click',async()=>{
     if(!current||!method)return;
     errorEl.textContent='';confirmBtn.disabled=true;
     let payload={method};
     if(method==='ESPÈCES'){
       const value=Number(String(received.value||'').replace(',','.'));
       if(!Number.isFinite(value)){errorEl.textContent='Montant reçu invalide.';confirmBtn.disabled=false;return}
       if(value<Number(current.order.total||0)){errorEl.textContent='Le montant reçu est insuffisant.';confirmBtn.disabled=false;return}
       payload.received=value;
     }
     try{
       const res=await fetch('/api/orders/'+encodeURIComponent(current.id)+'/payment-phase41',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
       const d=await res.json();if(!res.ok||!d.ok)throw new Error(d.error||'Encaissement impossible');
       const card=current.card;showPaid(card,d);close();
     }catch(e){errorEl.textContent=e.message||'Encaissement impossible';confirmBtn.disabled=false}
   });
   async function decorate(){
     let meta={};
     try{
       const r=await fetch('/api/orders/history-meta-phase44',{cache:'no-store'});
       const d=await r.json();
       if(r.ok&&d.ok&&d.orders)meta=d.orders;
     }catch(e){return}
     const cards=[...document.querySelectorAll('#list .order')];
     for(const card of cards){
       const id=orderId(card);if(!id)continue;
       const order=meta[id];if(!order)continue;
       const existing=[...card.querySelectorAll('.p41-pay-btn')];if(existing.length>1)existing.slice(1).forEach(x=>x.remove());
       const paidBadges=[...card.querySelectorAll('.p41-paid-badge')];if(paidBadges.length>1)paidBadges.slice(1).forEach(x=>x.remove());
       if(order.payment_status==='PAYÉE'){showPaid(card,order);continue}
       card.querySelectorAll('.p41-paid-badge').forEach(x=>x.remove());
       if(order.z_locked||card.querySelector('.p41-pay-btn'))continue;
       const btn=document.createElement('button');btn.type='button';btn.className='p41-pay-btn';btn.textContent='💳 Encaisser';btn.addEventListener('click',()=>openPayment(card,id,btn));card.appendChild(btn);
     }
   }
   function scheduleDecorate(){clearTimeout(decorateTimer);decorateTimer=setTimeout(decorate,80)}
   scheduleDecorate();const list=document.getElementById('list');if(list)new MutationObserver(scheduleDecorate).observe(list,{childList:true,subtree:true});
 });
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
