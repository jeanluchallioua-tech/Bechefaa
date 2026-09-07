"""Ergonomie tactile isolée pour la caisse BÉCHÉFAA.

- La fiche client existante devient une fenêtre modale.
- Trois modes de commande : Salle, Emporter, Livraison.
- Salle n'utilise pas de coordonnées client.
- Le client courant est effacé après envoi réussi en cuisine.
- Aucun Wix / V1 / localStorage.
"""
import importlib
import json

from flask import g, request


def register_pos_touch_layout(app, db):
    # Harmonise l'affichage des types de tickets dans toutes les vues propres.
    core = importlib.import_module("clean_caisse.app")

    def clean_ticket_type(source):
        value = str(source or "").upper()
        if value == "SALLE":
            return "Salle"
        if value in {"EMPORTER", "TAKEAWAY"}:
            return "Emporter"
        if value in {"LIVRAISON", "DELIVERY"}:
            return "Livraison"
        return "Comptoir"  # compatibilité des anciens tickets déjà enregistrés

    core.ticket_type = clean_ticket_type

    @app.before_request
    def capture_order_mode():
        if request.path == "/api/orders" and request.method == "POST":
            payload = request.get_json(silent=True) or {}
            mode = str(payload.get("ticket_type") or "Salle").strip().lower()
            if mode == "livraison":
                g.pos_order_mode = "LIVRAISON"
            elif mode == "emporter":
                g.pos_order_mode = "EMPORTER"
            else:
                g.pos_order_mode = "SALLE"

    @app.after_request
    def apply_order_mode_and_touch_layout(response):
        # Le backend historique ne connaissait que CAISSE/LIVRAISON.
        # On conserve le cœur stable et on spécialise la source après création.
        if request.path == "/api/orders" and request.method == "POST" and response.status_code == 201:
            mode = getattr(g, "pos_order_mode", "SALLE")
            try:
                data = response.get_json(silent=True) or {}
                order_id = data.get("id")
                if order_id and mode in {"SALLE", "EMPORTER"}:
                    with db() as conn:
                        with conn.transaction():
                            conn.execute("UPDATE caisse_orders SET source=%s WHERE id=%s", (mode, order_id))
                data["ticket_type"] = clean_ticket_type(mode)
                response.set_data(json.dumps(data, ensure_ascii=False))
                response.content_type = "application/json; charset=utf-8"
            except Exception:
                pass
            return response

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
.ticket-choice{position:sticky;top:0;z-index:15;background:#fff;padding:4px 0 8px;margin:0;gap:7px}
.ticket-choice button{min-height:52px;font-size:14px;touch-action:manipulation;padding:8px 5px}
.touch-client-summary{background:#f7f8fa;border:1px solid #d9dde3;border-radius:10px;padding:10px 12px;margin:8px 0 12px;display:flex;align-items:center;gap:10px;cursor:pointer;min-height:54px;touch-action:manipulation}
.touch-client-summary.hidden{display:none!important}.touch-client-summary .tc-main{flex:1;min-width:0}.touch-client-summary b{display:block;font-size:14px}.touch-client-summary span{display:block;font-size:12px;color:#667085;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.touch-client-summary .tc-edit{font-weight:800;font-size:13px;background:#111827;color:#fff;padding:9px 11px;border-radius:8px}
.customer-box.touch-modal{display:none!important;position:fixed!important;z-index:10000;inset:0!important;margin:0!important;border:0!important;border-radius:0!important;background:#0008!important;padding:20px!important;overflow:auto!important}
.customer-box.touch-modal.open{display:flex!important;align-items:flex-start;justify-content:center}
.customer-box.touch-modal .touch-client-panel{width:min(620px,96vw);background:#fff;border-radius:16px;padding:18px;margin-top:max(12px,5vh);box-shadow:0 18px 55px #0005;position:relative}
.touch-client-close{position:absolute;right:12px;top:10px;border:0;background:#eef0f3;border-radius:9px;width:42px;height:42px;font-size:24px;font-weight:800;cursor:pointer;touch-action:manipulation}
.customer-box.touch-modal h3{font-size:22px;padding-right:50px;margin-bottom:14px}.customer-box.touch-modal input{font-size:16px;min-height:46px}.customer-box.touch-modal button{min-height:44px}.order-box{scroll-margin-top:70px}
</style>
<script>
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   const box=document.querySelector('.customer-box'),cart=document.querySelector('.cart'),ticket=document.querySelector('.ticket-choice');
   if(!box||!cart||!ticket)return;

   if(ticket.parentNode===cart)cart.insertBefore(ticket,cart.firstChild);
   ticket.innerHTML='<button class="active" data-ticket="Salle">Salle</button><button data-ticket="Emporter">Emporter</button><button data-ticket="Livraison">Livraison</button>';

   const summary=document.createElement('div');summary.className='touch-client-summary hidden';
   summary.innerHTML='<div class="tc-main"><b id="tc-name">Client</b><span id="tc-detail">Toucher pour rechercher ou enregistrer un client</span></div><div class="tc-edit">Client</div>';
   ticket.insertAdjacentElement('afterend',summary);

   const panel=document.createElement('div');panel.className='touch-client-panel';
   while(box.firstChild)panel.appendChild(box.firstChild);
   const close=document.createElement('button');close.type='button';close.className='touch-client-close';close.setAttribute('aria-label','Fermer');close.textContent='×';panel.insertBefore(close,panel.firstChild);box.appendChild(panel);box.classList.add('touch-modal');document.body.appendChild(box);

   function updateSummary(){
     const first=document.getElementById('cust-first')?.value.trim()||'',last=document.getElementById('cust-last')?.value.trim()||'',phone=document.getElementById('cust-phone')?.value.trim()||'',city=document.getElementById('cust-city')?.value.trim()||'';
     const name=(first+' '+last).trim();document.getElementById('tc-name').textContent=name||'Client';document.getElementById('tc-detail').textContent=[phone,city].filter(Boolean).join(' • ')||'Toucher pour rechercher ou enregistrer un client';
   }
   function clearCustomer(){document.getElementById('cust-clear')?.click();updateSummary()}
   function open(){box.classList.add('open');setTimeout(()=>document.getElementById('cust-search')?.focus(),80)}
   function shut(){box.classList.remove('open');updateSummary()}
   function applyMode(mode){
     summary.classList.toggle('hidden',mode==='Salle');
     if(mode==='Salle'){shut();clearCustomer()}
     else document.getElementById('tc-name').textContent=(mode==='Livraison'?'Client livraison':'Client emporter');
   }
   summary.onclick=open;close.onclick=shut;box.addEventListener('click',e=>{if(e.target===box)shut()});document.addEventListener('keydown',e=>{if(e.key==='Escape')shut()});panel.addEventListener('input',updateSummary);
   panel.addEventListener('click',e=>{
     if(e.target.closest('#cust-clear'))setTimeout(updateSummary,100);
     if(e.target.closest('.customer-result[data-i]'))setTimeout(()=>{updateSummary();shut()},120);
     if(e.target.closest('#cust-save'))setTimeout(updateSummary,100);
   });

   const note=document.getElementById('cust-note');
   if(note){
     new MutationObserver(()=>{
       const text=(note.textContent||'').toLowerCase();
       if(text.includes('client enregistré'))setTimeout(()=>{updateSummary();shut()},120);
     }).observe(note,{childList:true,subtree:true,characterData:true});
   }

   ticket.addEventListener('click',e=>{const b=e.target.closest('[data-ticket]');if(!b)return;setTimeout(()=>applyMode(b.dataset.ticket),0)});
   document.querySelectorAll('.main,.cats,.cart').forEach(el=>{el.style.webkitOverflowScrolling='touch'});

   /* Une fois l'envoi cuisine confirmé, prépare immédiatement la caisse pour le client suivant. */
   const msg=document.getElementById('order-message');
   if(msg){
     const observer=new MutationObserver(function(){
       const text=(msg.textContent||'').toLowerCase();
       if(text.includes('envoyée en cuisine')){
         clearCustomer();
         shut();
         const mode=ticket.querySelector('[data-ticket].active')?.dataset.ticket||'Salle';
         if(mode!=='Salle')document.getElementById('tc-name').textContent=(mode==='Livraison'?'Client livraison':'Client emporter');
       }
     });
     observer.observe(msg,{childList:true,subtree:true,characterData:true});
   }

   updateSummary();applyMode('Salle');
   /* Déclenche aussi le gestionnaire natif de la caisse afin que TICKET_TYPE devienne Salle. */
   ticket.querySelector('[data-ticket="Salle"]')?.click();
 });
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
