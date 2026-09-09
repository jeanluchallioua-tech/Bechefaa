"""Phase 4.2 — simplification de l'interface du mode de service.

Ne modifie ni la persistance ni les règles Salle/Table de Phase 3.6.
Les boutons principaux Salle / Emporter / Livraison restent l'unique choix
visible. Aucun mode n'est sélectionné par défaut : l'utilisateur choisit
explicitement le service à chaque nouvelle commande.
"""
from flask import request


def register_service_mode_ui_phase42(app):
    @app.after_request
    def simplify_service_mode_phase42(response):
        if request.path != "/pos" or response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        if "phase42-service-mode-ui" in html:
            return response

        addon = r'''
<style id="phase42-service-mode-ui">
#phase36-table-selector{display:none!important}
#phase42-table-grid{display:none;grid-template-columns:repeat(3,1fr);gap:6px;margin:8px 0 12px}
#phase42-table-grid button{padding:10px 6px;border:1px solid #ccd1d8;border-radius:8px;background:#fff;color:#17191c;font-weight:800;min-height:44px}
#phase42-table-grid button.active{background:#d97706;color:#fff}
</style>
<script id="phase42-service-mode-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   function init(){
     const ticket=document.querySelector('.ticket-choice');
     const selector=document.getElementById('phase36-table-selector');
     const legacyTables=document.getElementById('p36-tables');
     const salleLegacy=document.getElementById('p36-salle');
     const emporterLegacy=document.getElementById('p36-emporter');
     if(!ticket||!selector||!legacyTables||!salleLegacy||!emporterLegacy){setTimeout(init,50);return}

     let chosenMode=null;
     let selectedTable=null;

     let grid=document.getElementById('phase42-table-grid');
     if(!grid){
       grid=document.createElement('div');
       grid.id='phase42-table-grid';
       grid.innerHTML=Array.from({length:9},(_,i)=>`<button type="button" data-phase42-table="${i+1}">Table ${i+1}</button>`).join('');
       ticket.insertAdjacentElement('afterend',grid);
     }

     function paintTables(){
       grid.querySelectorAll('[data-phase42-table]').forEach(b=>b.classList.toggle('active',Number(b.dataset.phase42Table)===selectedTable));
     }
     function hideTables(){grid.style.display='none'}
     function showTables(){grid.style.display='grid'}
     function clearChoice(){
       chosenMode=null;
       selectedTable=null;
       ticket.querySelectorAll('[data-ticket]').forEach(b=>b.classList.remove('active'));
       paintTables();
       hideTables();
     }
     function sync(mode,button){
       chosenMode=String(mode||'').toLowerCase();
       ticket.querySelectorAll('[data-ticket]').forEach(b=>b.classList.toggle('active',b===button));
       if(chosenMode==='salle'){
         salleLegacy.click();
         showTables();
       }else{
         selectedTable=null;
         emporterLegacy.click();
         paintTables();
         hideTables();
       }
     }

     /* Le module tactile historique clique automatiquement sur Salle au chargement.
        On ignore ces clics synthétiques et on force un état neutre après son initialisation. */
     [120,300,600].forEach(ms=>setTimeout(clearChoice,ms));

     ticket.addEventListener('click',function(e){
       const b=e.target.closest('[data-ticket]');
       if(!b || !e.isTrusted)return;
       sync(b.dataset.ticket,b);
     },true);

     grid.addEventListener('click',function(e){
       const b=e.target.closest('[data-phase42-table]');
       if(!b)return;
       selectedTable=Number(b.dataset.phase42Table);
       const legacy=legacyTables.querySelector(`[data-p36-table="${selectedTable}"]`);
       if(legacy)legacy.click();
       paintTables();
     });

     /* Sécurité : aucune commande ne part sans choix explicite du mode. */
     const nativeFetch=window.fetch.bind(window);
     window.fetch=function(input,init){
       const url=typeof input==='string'?input:(input&&input.url)||'';
       if(url==='/api/orders' && init && String(init.method||'GET').toUpperCase()==='POST'){
         if(!chosenMode){
           const msg=document.getElementById('order-message');
           if(msg)msg.innerHTML='<div class="error"><b>Choisissez Salle, Emporter ou Livraison.</b></div>';
           return Promise.reject(new Error('Choisissez Salle, Emporter ou Livraison'));
         }
         if(chosenMode==='salle' && !selectedTable){
           const msg=document.getElementById('order-message');
           if(msg)msg.innerHTML='<div class="error"><b>Choisissez une table de 1 à 9.</b></div>';
           return Promise.reject(new Error('Choisissez une table de 1 à 9'));
         }
       }
       return nativeFetch(input,init);
     };

     /* Après envoi cuisine réussi, on repart sans mode sélectionné pour la commande suivante. */
     const msg=document.getElementById('order-message');
     if(msg){
       new MutationObserver(function(){
         const text=(msg.textContent||'').toLowerCase();
         if(text.includes('envoyée en cuisine'))setTimeout(clearChoice,80);
       }).observe(msg,{childList:true,subtree:true,characterData:true});
     }
   }
   init();
 });
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
