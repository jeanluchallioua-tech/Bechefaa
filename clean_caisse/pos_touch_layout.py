"""Ergonomie tactile isolée pour la caisse BÉCHÉFAA.
Transforme la fiche client existante en fenêtre et garde les commandes essentielles visibles.
Aucun changement PostgreSQL / commandes / Wix.
"""


def register_pos_touch_layout(app):
    @app.after_request
    def inject_touch_layout(response):
        if request.path != "/pos" or response.status_code != 200 or response.mimetype != "text/html":
            return response
        html = response.get_data(as_text=True)
        addon = r'''
<style>
/* Phase 1 — ergonomie tactile */
@media(min-width:901px){
  .cart{position:relative;height:calc(100vh - 64px);overflow-y:auto;overscroll-behavior:contain}
  .main,.cats{overscroll-behavior:contain;-webkit-overflow-scrolling:touch}
}
.touch-client-summary{background:#f7f8fa;border:1px solid #d9dde3;border-radius:10px;padding:10px 12px;margin:8px 0 12px;display:flex;align-items:center;gap:10px;cursor:pointer;min-height:54px;touch-action:manipulation}
.touch-client-summary .tc-main{flex:1;min-width:0}.touch-client-summary b{display:block;font-size:14px}.touch-client-summary span{display:block;font-size:12px;color:#667085;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.touch-client-summary .tc-edit{font-weight:800;font-size:13px;background:#111827;color:#fff;padding:9px 11px;border-radius:8px}
.customer-box.touch-modal{display:none;position:fixed!important;z-index:10000;inset:0!important;margin:0!important;border:0!important;border-radius:0!important;background:#0008!important;padding:20px!important;overflow:auto}
.customer-box.touch-modal.open{display:flex!important;align-items:flex-start;justify-content:center}
.customer-box.touch-modal .touch-client-panel{width:min(620px,96vw);background:#fff;border-radius:16px;padding:18px;margin-top:max(12px,5vh);box-shadow:0 18px 55px #0005;position:relative}
.touch-client-close{position:absolute;right:12px;top:10px;border:0;background:#eef0f3;border-radius:9px;width:42px;height:42px;font-size:24px;font-weight:800;cursor:pointer;touch-action:manipulation}
.customer-box.touch-modal h3{font-size:22px;padding-right:50px;margin-bottom:14px}.customer-box.touch-modal input{font-size:16px;min-height:46px}.customer-box.touch-modal button{min-height:44px}
.ticket-choice{position:sticky;top:0;z-index:15;background:#fff;padding:4px 0 8px;margin-top:0}.ticket-choice button{min-height:48px;font-size:15px;touch-action:manipulation}
.order-box{scroll-margin-top:70px}
@media(max-width:900px){.customer-box.touch-modal{display:none}.customer-box.touch-modal.open{display:flex!important}.touch-client-summary{display:flex}.cart.touch-cart-mobile{display:block;position:fixed;z-index:500;right:8px;bottom:8px;width:min(390px,calc(100vw - 16px));max-height:70vh;border:1px solid #ddd;border-radius:14px;box-shadow:0 8px 30px #0003}}
</style>
<script>
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   const box=document.querySelector('.customer-box');
   const cart=document.querySelector('.cart');
   const ticket=document.querySelector('.ticket-choice');
   if(!box||!cart||!ticket)return;

   /* Le choix Comptoir/Livraison reste le premier élément fonctionnel de la colonne. */
   if(ticket.parentNode===cart) cart.insertBefore(ticket,cart.firstChild);

   const summary=document.createElement('div');
   summary.className='touch-client-summary';
   summary.innerHTML='<div class="tc-main"><b id="tc-name">Client comptoir</b><span id="tc-detail">Toucher pour rechercher ou enregistrer un client</span></div><div class="tc-edit">Client</div>';
   ticket.insertAdjacentElement('afterend',summary);

   /* Emballe le contenu de la fiche existante sans recréer sa logique. */
   const panel=document.createElement('div');panel.className='touch-client-panel';
   while(box.firstChild)panel.appendChild(box.firstChild);
   const close=document.createElement('button');close.type='button';close.className='touch-client-close';close.setAttribute('aria-label','Fermer');close.textContent='×';panel.insertBefore(close,panel.firstChild);box.appendChild(panel);box.classList.add('touch-modal');
   document.body.appendChild(box);

   function updateSummary(){
     const first=document.getElementById('cust-first')?.value.trim()||'';
     const last=document.getElementById('cust-last')?.value.trim()||'';
     const phone=document.getElementById('cust-phone')?.value.trim()||'';
     const city=document.getElementById('cust-city')?.value.trim()||'';
     const name=(first+' '+last).trim();
     document.getElementById('tc-name').textContent=name||'Client comptoir';
     document.getElementById('tc-detail').textContent=[phone,city].filter(Boolean).join(' • ')||'Toucher pour rechercher ou enregistrer un client';
   }
   function open(){box.classList.add('open');setTimeout(()=>document.getElementById('cust-search')?.focus(),80)}
   function shut(){box.classList.remove('open');updateSummary()}
   summary.onclick=open;close.onclick=shut;
   box.addEventListener('click',e=>{if(e.target===box)shut()});
   document.addEventListener('keydown',e=>{if(e.key==='Escape'&&box.classList.contains('open'))shut()});
   panel.addEventListener('input',updateSummary);
   panel.addEventListener('click',e=>{if(e.target.closest('#cust-save')||e.target.closest('#cust-clear')||e.target.closest('.customer-result'))setTimeout(updateSummary,100)});
   updateSummary();

   /* Sur tactile, les zones scrollent indépendamment au doigt. */
   document.querySelectorAll('.main,.cats,.cart').forEach(el=>{el.style.webkitOverflowScrolling='touch'});
 });
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response

    from flask import request
