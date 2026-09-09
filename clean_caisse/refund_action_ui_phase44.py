"""Phase 4.4 — action de remboursement depuis l'Historique.

Module UI isolé. Le calcul et l'écriture financière restent entièrement gérés
par payment_transactions_phase44.py, déjà validé.
"""
from flask import request


def register_refund_action_ui_phase44(app):
    @app.after_request
    def inject_refund_action_ui_phase44(response):
        if request.path != "/historique-modification" or response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        addon = r'''
<style id="p44-refund-action-style">
.p44-refund-action-btn{border:0;border-radius:8px;padding:10px 12px;font-weight:900;font-size:12px;color:#fff;background:#c2410c;cursor:pointer;margin-top:7px;margin-left:6px}
.p44-refund-action-btn:disabled{opacity:.5;cursor:not-allowed}
.p44-refund-modal-backdrop{position:fixed;inset:0;background:rgba(15,23,42,.62);z-index:99990;display:flex;align-items:center;justify-content:center;padding:18px}
.p44-refund-modal{width:min(460px,96vw);background:#fff;border-radius:16px;padding:18px;box-shadow:0 20px 60px rgba(0,0,0,.28);font-family:Arial,sans-serif}
.p44-refund-modal h3{margin:0 0 10px;font-size:20px}.p44-refund-modal .info{font-size:14px;line-height:1.5;margin-bottom:12px}.p44-refund-modal label{display:block;font-size:12px;font-weight:900;margin:10px 0 5px}.p44-refund-modal input{width:100%;padding:11px;border:1px solid #cbd5e1;border-radius:9px;font-size:16px}.p44-refund-modal .actions{display:flex;gap:8px;margin-top:14px}.p44-refund-modal button{flex:1;border:0;border-radius:9px;padding:11px;font-weight:900;cursor:pointer}.p44-refund-cancel{background:#e2e8f0;color:#0f172a}.p44-refund-confirm{background:#c2410c;color:#fff}.p44-refund-confirm:disabled{opacity:.5;cursor:not-allowed}
</style>
<script id="p44-refund-action-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 function euro(v){return Number(v||0).toFixed(2).replace('.',',')+' €'}
 function orderId(card){
   const buttons=[...card.querySelectorAll('button')];
   for(const b of buttons){const oc=b.getAttribute('onclick')||'';let m=oc.match(/editOrder\('([^']+)'\)/);if(!m)m=oc.match(/viewOrder\('([^']+)'\)/);if(m)return m[1]}
   const a=card.querySelector('a[href*="/impression/client/"]');if(a){const m=(a.getAttribute('href')||'').match(/\/impression\/client\/([^/?#]+)/);if(m)return decodeURIComponent(m[1])}
   return null;
 }
 function historyMeta(){
   const now=Date.now();
   if(window.__p44HistoryMetaPromise && now-(window.__p44HistoryMetaAt||0)<1500)return window.__p44HistoryMetaPromise;
   window.__p44HistoryMetaAt=now;
   window.__p44HistoryMetaPromise=fetch('/api/orders/history-meta-phase44',{cache:'no-store'}).then(r=>r.json()).then(d=>(d&&d.ok&&d.orders)?d.orders:{}).catch(()=>({}));
   return window.__p44HistoryMetaPromise;
 }
 function txRefundable(txs,payment){
   let used=0;
   for(const t of txs){if(t.transaction_type==='REFUND'&&t.parent_transaction_id===payment.id&&(t.status==='SUCCEEDED'||t.status==='PENDING_EXTERNAL'))used+=Number(t.amount||0)}
   return Math.max(0,Math.round((Number(payment.amount||0)-used)*100)/100);
 }
 function openModal(card,id,btn){
   btn.disabled=true;
   fetch('/api/orders/'+encodeURIComponent(id)+'/payment-transactions-phase44',{cache:'no-store'}).then(async r=>{const d=await r.json();if(!r.ok||!d.ok)throw new Error(d.error||'Transactions indisponibles');return d}).then(d=>{
     const txs=d.transactions||[];const payments=txs.filter(t=>t.transaction_type==='PAYMENT'&&t.status==='SUCCEEDED').map(p=>({p,refundable:txRefundable(txs,p)})).filter(x=>x.refundable>0.001);
     if(!payments.length)throw new Error('Aucun montant remboursable');
     const choice=payments[0];
     const max=choice.refundable;
     const back=document.createElement('div');back.className='p44-refund-modal-backdrop';
     back.innerHTML='<div class="p44-refund-modal"><h3>Rembourser la commande #'+String(d.order.num||'')+'</h3><div class="info">Payé : <strong>'+euro(d.summary.paid)+'</strong><br>Déjà remboursé : <strong>'+euro(d.summary.refunded)+'</strong><br>Remboursable maintenant : <strong>'+euro(max)+'</strong></div><label>Montant à rembourser</label><input class="p44-refund-amount" type="number" min="0.01" step="0.01" max="'+max.toFixed(2)+'" value="'+max.toFixed(2)+'"><label>Motif du remboursement</label><input class="p44-refund-reason" type="text" maxlength="120" placeholder="Ex. erreur commande, geste commercial…"><div class="actions"><button class="p44-refund-cancel" type="button">Annuler</button><button class="p44-refund-confirm" type="button">Confirmer le remboursement</button></div></div>';
     document.body.appendChild(back);
     const close=()=>{back.remove();btn.disabled=false};back.querySelector('.p44-refund-cancel').onclick=close;
     back.addEventListener('click',e=>{if(e.target===back)close()});
     back.querySelector('.p44-refund-confirm').onclick=async function(){
       const amount=Number(back.querySelector('.p44-refund-amount').value||0);const reason=String(back.querySelector('.p44-refund-reason').value||'').trim();
       if(!(amount>0)||amount>max+0.0001){alert('Montant invalide. Maximum : '+euro(max));return}
       if(!reason){alert('Indiquez le motif du remboursement.');return}
       if(!confirm('Confirmer le remboursement de '+euro(amount)+' ?'))return;
       this.disabled=true;
       try{
         const r=await fetch('/api/orders/'+encodeURIComponent(id)+'/refund-phase44',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({transaction_id:choice.p.id,amount:amount,reason:reason,created_by:'CAISSE'})});
         const out=await r.json();if(!r.ok||!out.ok)throw new Error(out.error||'Remboursement impossible');
         back.remove();window.__p44HistoryMetaAt=0;window.__p44HistoryMetaPromise=null;
         if(typeof load==='function')await load();else location.reload();
       }catch(e){alert(e.message||'Remboursement impossible');this.disabled=false}
     };
   }).catch(e=>{alert(e.message||'Remboursement impossible');btn.disabled=false});
 }
 ready(function(){
   async function decorate(){
     const cards=[...document.querySelectorAll('#list .order')];if(!cards.length)return;
     const all=await historyMeta();
     for(const card of cards){if(card.querySelector('.p44-refund-action-btn'))continue;const id=orderId(card);if(!id)continue;const d=all[id];if(!d)continue;
       const ps=String(d.payment_status||'').toUpperCase();
       if(ps!=='PAYÉE'&&ps!=='PARTIELLEMENT REMBOURSÉE')continue;
       if(d.z_locked)continue;
       const btn=document.createElement('button');btn.type='button';btn.className='p44-refund-action-btn';btn.textContent='↩ Rembourser';btn.addEventListener('click',()=>openModal(card,id,btn));card.appendChild(btn);
     }
   }
   setTimeout(decorate,0);const list=document.getElementById('list');if(list)new MutationObserver(()=>setTimeout(decorate,80)).observe(list,{childList:true,subtree:true});
 });
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
