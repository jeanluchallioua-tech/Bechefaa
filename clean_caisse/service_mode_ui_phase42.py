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
#phase36-table-selector > div:first-child,
#phase36-table-selector > div:nth-child(2){display:none!important}
#phase36-table-selector{margin:8px 0 12px!important;display:none}
#p36-tables{margin-top:0!important}
</style>
<script id="phase42-service-mode-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   function init(){
     const ticket=document.querySelector('.ticket-choice');
     const selector=document.getElementById('phase36-table-selector');
     const tables=document.getElementById('p36-tables');
     const salleLegacy=document.getElementById('p36-salle');
     const emporterLegacy=document.getElementById('p36-emporter');
     if(!ticket||!selector||!tables||!salleLegacy||!emporterLegacy){setTimeout(init,50);return}

     let chosenMode=null;
     let userInteracted=false;

     function ensureTables(){
       if(!tables.querySelector('[data-p36-table]')){
         tables.innerHTML=Array.from({length:9},(_,i)=>`<button type="button" data-p36-table="${i+1}" style="padding:9px;border:1px solid #ccd1d8;border-radius:8px;background:#fff;font-weight:800">Table ${i+1}</button>`).join('');
       }
     }
     function hideTables(){
       selector.style.setProperty('display','none','important');
       tables.style.setProperty('display','none','important');
     }
     function showTables(){
       ensureTables();
       selector.style.setProperty('display','block','important');
       tables.style.setProperty('display','grid','important');
     }
     function clearChoice(){
       if(userInteracted)return;
       chosenMode=null;
       ticket.querySelectorAll('[data-ticket]').forEach(b=>b.classList.remove('active'));
       hideTables();
     }
     function sync(mode,button){
       chosenMode=String(mode||'').toLowerCase();
       ticket.querySelectorAll('[data-ticket]').forEach(b=>b.classList.toggle('active',b===button));
       if(chosenMode==='salle'){
         salleLegacy.click();
         showTables();
       }else{
         emporterLegacy.click();
         hideTables();
       }
     }

     /* Le vieux code sélectionne Salle automatiquement au chargement.
        On annule ce choix, même si son initialisation arrive légèrement après la nôtre. */
     hideTables();
     [80,180,350].forEach(ms=>setTimeout(clearChoice,ms));

     ticket.addEventListener('click',function(e){
       const b=e.target.closest('[data-ticket]');
       if(!b)return;
       userInteracted=true;
       sync(b.dataset.ticket,b);
     },true);

     /* Sécurité : aucune commande ne part sans choix explicite du mode. */
     const nativeFetch=window.fetch.bind(window);
     window.fetch=function(input,init){
       const url=typeof input==='string'?input:(input&&input.url)||'';
       if(url==='/api/orders' && init && String(init.method||'GET').toUpperCase()==='POST' && !chosenMode){
         const msg=document.getElementById('order-message');
         if(msg)msg.innerHTML='<div class="error"><b>Choisissez Salle, Emporter ou Livraison.</b></div>';
         return Promise.reject(new Error('Choisissez Salle, Emporter ou Livraison'));
       }
       return nativeFetch(input,init);
     };

     /* Après envoi cuisine réussi, on repart sans mode sélectionné pour la commande suivante. */
     const msg=document.getElementById('order-message');
     if(msg){
       new MutationObserver(function(){
         const text=(msg.textContent||'').toLowerCase();
         if(text.includes('envoyée en cuisine')){
           userInteracted=false;
           setTimeout(clearChoice,80);
         }
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
