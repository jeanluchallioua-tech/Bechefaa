"""Phase 4.2 — simplification de l'interface du mode de service.

Ne modifie ni la persistance ni les règles Salle/Table de Phase 3.6.
Les boutons principaux Salle / Emporter / Livraison restent l'unique choix
visible. En mode Salle, seules les 9 tables du sélecteur existant sont affichées.
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
/* Le choix principal Salle / Emporter / Livraison suffit.
   Le sélecteur Phase 3.6 reste actif techniquement mais ses boutons doublons sont masqués. */
#phase36-table-selector > div:first-child,
#phase36-table-selector > div:nth-child(2){display:none!important}
#phase36-table-selector{margin:8px 0 12px!important}
#p36-tables{margin-top:0!important}
</style>
<script id="phase42-service-mode-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   setTimeout(function(){
     const ticket=document.querySelector('.ticket-choice');
     const selector=document.getElementById('phase36-table-selector');
     const tables=document.getElementById('p36-tables');
     const salleLegacy=document.getElementById('p36-salle');
     const emporterLegacy=document.getElementById('p36-emporter');
     if(!ticket||!selector||!tables||!salleLegacy||!emporterLegacy)return;

     function sync(mode){
       const value=String(mode||'Salle').toLowerCase();
       if(value==='salle'){
         /* Réutilise exactement la logique Table 1 à 9 déjà validée en Phase 3.6. */
         salleLegacy.click();
         selector.style.display='block';
         tables.style.display='grid';
       }else{
         /* Emporter et Livraison n'ont pas de table. */
         emporterLegacy.click();
         selector.style.display='none';
       }
     }

     ticket.addEventListener('click',function(e){
       const b=e.target.closest('[data-ticket]');
       if(!b)return;
       setTimeout(function(){sync(b.dataset.ticket)},0);
     });

     const active=ticket.querySelector('[data-ticket].active');
     sync(active?active.dataset.ticket:'Salle');
   },0);
 });
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
