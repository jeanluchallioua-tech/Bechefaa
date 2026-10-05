"""Fenêtre de choix du mode de service au démarrage d'une commande.

Cette couche d'interface pilote les boutons service existants sans modifier
la logique métier Phase 4.2. Elle s'affiche à l'ouverture de /pos et après
l'événement bechefaa:new-order.
"""
from flask import request


def register_pos_service_launcher_phase6(app):
    @app.after_request
    def pos_service_launcher_phase6(response):
        if request.path != "/pos" or response.status_code != 200 or response.mimetype != "text/html":
            return response
        html = response.get_data(as_text=True)
        if "bechefaa-service-launcher-phase6" in html:
            return response

        addon = r'''
<style id="bechefaa-service-launcher-phase6">
#svc-launcher{position:fixed;inset:0;z-index:200000;background:rgba(9,12,16,.72);backdrop-filter:blur(7px);display:flex;align-items:center;justify-content:center;padding:22px}
#svc-launcher.hidden{display:none}
#svc-card{position:relative;width:min(920px,96vw);background:#fff;border-radius:26px;box-shadow:0 30px 90px #0007;overflow:hidden;border:1px solid #e7e7e7}
#svc-close{position:absolute;top:14px;right:14px;z-index:2;width:42px;height:42px;border:0;border-radius:50%;background:#111827;color:#fff;font-size:25px;font-weight:900;line-height:1;cursor:pointer;display:grid;place-items:center;box-shadow:0 5px 14px #0003}
#svc-close:hover{background:#2a3038}
#svc-head{padding:26px 30px 18px;text-align:center;background:linear-gradient(180deg,#fff,#faf7ef)}
#svc-head h2{margin:0;font:900 30px Arial,sans-serif;color:#111827}
#svc-head p{margin:8px 0 0;color:#687180;font:700 14px Arial,sans-serif}
#svc-modes{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;padding:22px 26px 28px}
.svc-mode{min-height:220px;border:2px solid #ece7da;border-radius:22px;background:#fff;cursor:pointer;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:13px;transition:.15s transform,.15s box-shadow,.15s border-color;padding:20px}
.svc-mode:hover{transform:translateY(-3px);border-color:#d8a72c;box-shadow:0 14px 28px #1112}
.svc-icon{width:92px;height:92px;border-radius:25px;display:grid;place-items:center;background:#111827;color:#f0bd45;font-size:48px;box-shadow:0 10px 22px #1113}
.svc-mode b{font:1000 21px Arial,sans-serif;color:#17191d}
.svc-mode small{font:700 13px Arial,sans-serif;color:#7b8490;text-align:center;line-height:1.35}
#svc-table-step{display:none;padding:8px 28px 30px}
#svc-table-step.show{display:block}
#svc-table-step h3{text-align:center;margin:4px 0 16px;font:900 21px Arial,sans-serif;color:#111827}
#svc-tables{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;max-width:650px;margin:0 auto}
#svc-tables button{min-height:66px;border:2px solid #e3e5e8;border-radius:14px;background:#fff;font:900 17px Arial,sans-serif;cursor:pointer}
#svc-tables button:hover{background:#fff8e6;border-color:#d9a62e}
#svc-back{display:block;margin:18px auto 0;border:0;background:transparent;color:#6c7480;text-decoration:underline;font-weight:800;cursor:pointer}
#svc-current{display:none;position:static;transform:none;z-index:auto;background:#111827;color:#fff;border-radius:999px;padding:9px 14px;font:900 12px Arial,sans-serif;box-shadow:none;cursor:pointer;border:1px solid #343a42;white-space:nowrap;justify-self:start}
#svc-current.show{display:block}
#svc-current span{color:#f0bd45;margin-left:5px}
.pos-v3-service{display:none!important}
@media(max-width:800px){#svc-modes{grid-template-columns:1fr}.svc-mode{min-height:150px;flex-direction:row}.svc-icon{width:72px;height:72px;font-size:38px}.svc-mode small{text-align:left}#svc-tables{grid-template-columns:repeat(3,1fr)}}
</style>
<div id="svc-launcher" aria-modal="true" role="dialog">
  <div id="svc-card">
    <button type="button" id="svc-close" aria-label="Fermer" title="Fermer">×</button>
    <div id="svc-head"><h2>Nouvelle commande</h2><p>Choisissez le mode de service avant de commencer.</p></div>
    <div id="svc-modes">
      <button type="button" class="svc-mode" data-svc="salle"><span class="svc-icon">🍽️</span><b>SUR PLACE</b><small>Choisir ensuite la table.</small></button>
      <button type="button" class="svc-mode" data-svc="emporter"><span class="svc-icon">🛍️</span><b>À EMPORTER</b><small>Commande comptoir à récupérer.</small></button>
      <button type="button" class="svc-mode" data-svc="livraison"><span class="svc-icon">🛵</span><b>LIVRAISON</b><small>Commande avec informations client.</small></button>
    </div>
    <div id="svc-table-step"><h3>Choisissez la table</h3><div id="svc-tables"></div><button type="button" id="svc-back">← Retour aux modes de service</button></div>
  </div>
</div>
<button type="button" id="svc-current" title="Modifier le mode de service">Commande : <span>—</span> · Modifier</button>
<script id="bechefaa-service-launcher-script-phase6">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   const modal=document.getElementById('svc-launcher'),modes=document.getElementById('svc-modes'),tableStep=document.getElementById('svc-table-step'),tables=document.getElementById('svc-tables'),current=document.getElementById('svc-current');
   if(!modal||!modes||!tableStep||!tables||!current)return;
   const toolbar=document.querySelector('.pos-v3-toolbar');
   if(toolbar)toolbar.appendChild(current);
   tables.innerHTML=Array.from({length:9},(_,i)=>'<button type="button" data-table="'+(i+1)+'">Table '+(i+1)+'</button>').join('');

   function findNative(mode){
     const btns=[...document.querySelectorAll('.ticket-choice [data-ticket]')];
     if(mode==='livraison')return btns.find(b=>String(b.dataset.ticket||'').toLowerCase()==='livraison');
     if(mode==='salle')return btns.find(b=>String(b.dataset.ticket||'').toLowerCase()==='salle');
     return btns.find(b=>!['livraison','salle'].includes(String(b.dataset.ticket||'').toLowerCase()));
   }
   function setCurrent(label){current.querySelector('span').textContent=label;current.classList.add('show')}
   function openModes(){modes.style.display='grid';tableStep.classList.remove('show');modal.classList.remove('hidden')}
   function closeModal(){modal.classList.add('hidden')}
   function chooseMode(mode){
     if(mode==='salle'){modes.style.display='none';tableStep.classList.add('show');return}
     const b=findNative(mode);if(!b)return;
     b.click();
     setCurrent(mode==='livraison'?'LIVRAISON':'À EMPORTER');
     closeModal();
     // Réutilise le sélecteur client existant : recherche d'un client ou création.
     // Le flux historique garde ensuite le nom sur la commande et sur le ticket cuisine.
     setTimeout(()=>{
       const summary=document.querySelector('.touch-client-summary:not(.hidden)');
       if(summary)summary.click();
       else{
         const box=document.querySelector('.customer-box.touch-modal');
         if(box)box.classList.add('open');
       }
     },80);
   }
   modes.addEventListener('click',e=>{const b=e.target.closest('[data-svc]');if(b)chooseMode(b.dataset.svc)});
   tables.addEventListener('click',e=>{
     const b=e.target.closest('[data-table]');if(!b)return;
     const nativeSalle=findNative('salle');if(nativeSalle)nativeSalle.click();
     setTimeout(()=>{
       const nativeTable=document.querySelector('#phase42-table-grid [data-phase42-table="'+b.dataset.table+'"]');
       if(nativeTable)nativeTable.click();
       setCurrent('SUR PLACE · TABLE '+b.dataset.table);
       closeModal();
     },0);
   });
   document.getElementById('svc-back').addEventListener('click',openModes);
   current.addEventListener('click',openModes);
   document.getElementById('svc-close').addEventListener('click',closeModal);
   document.addEventListener('bechefaa:new-order',()=>{current.classList.remove('show');openModes()});
   openModes();
 });
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
