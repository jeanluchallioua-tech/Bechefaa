"""Phase 4.2 — choix unique du mode de service dans la caisse.

Cette couche ne persiste rien elle-même. Elle enrichit uniquement la requête
POST /api/orders avec service_mode, ticket_type et table_number.
La persistance et la validation appartiennent à clean_caisse.app.
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
#phase42-table-grid{display:none;grid-template-columns:repeat(3,1fr);gap:8px;margin:8px 16px 12px}
#phase42-table-grid.show{display:grid}
#phase42-table-grid button{padding:12px 8px;border:1px solid #ccd1d8;border-radius:8px;background:#fff;color:#17191c;font-weight:900;min-height:48px;font-size:15px}
#phase42-table-grid button.active{background:#d9a62e;color:#111;border-color:#d9a62e}
</style>
<script id="phase42-service-mode-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   const ticket=document.querySelector('.ticket-choice');
   if(!ticket)return;

   let chosenMode=null;
   let selectedTable=null;

   let grid=document.getElementById('phase42-table-grid');
   if(!grid){
     grid=document.createElement('div');
     grid.id='phase42-table-grid';
     grid.innerHTML=Array.from({length:9},(_,i)=>'<button type="button" data-phase42-table="'+(i+1)+'">Table '+(i+1)+'</button>').join('');
     const toolbar=ticket.closest('.pos-v3-toolbar');
     (toolbar||ticket.parentElement).insertAdjacentElement('afterend',grid);
   }

   function paint(){
     ticket.querySelectorAll('[data-ticket]').forEach(b=>{
       const mode=String(b.dataset.ticket||'').toLowerCase();
       b.classList.toggle('active',mode===chosenMode);
     });
     grid.classList.toggle('show',chosenMode==='salle');
     grid.querySelectorAll('[data-phase42-table]').forEach(b=>b.classList.toggle('active',Number(b.dataset.phase42Table)===selectedTable));
   }
   function clearChoice(){
     chosenMode=null;
     selectedTable=null;
     paint();
   }

   ticket.addEventListener('click',function(e){
     const b=e.target.closest('[data-ticket]');
     if(!b)return;
     const mode=String(b.dataset.ticket||'').toLowerCase();
     chosenMode=mode==='livraison'?'livraison':(mode==='salle'?'salle':'emporter');
     if(chosenMode!=='salle')selectedTable=null;
     paint();
   },true);

   grid.addEventListener('click',function(e){
     const b=e.target.closest('[data-phase42-table]');
     if(!b)return;
     selectedTable=Number(b.dataset.phase42Table);
     chosenMode='salle';
     paint();
   });

   const nativeFetch=window.fetch.bind(window);
   window.fetch=function(input,init){
     const url=typeof input==='string'?input:(input&&input.url)||'';
     if(url==='/api/orders' && init && String(init.method||'GET').toUpperCase()==='POST'){
       if(!chosenMode){
         const msg=document.getElementById('order-message');
         if(msg)msg.innerHTML='<div class="error"><b>Choisissez Sur place, À emporter ou Livraison.</b></div>';
         return Promise.reject(new Error('Choisissez le mode de service'));
       }
       if(chosenMode==='salle' && !selectedTable){
         const msg=document.getElementById('order-message');
         if(msg)msg.innerHTML='<div class="error"><b>Choisissez une table de 1 à 9.</b></div>';
         return Promise.reject(new Error('Choisissez une table de 1 à 9'));
       }
       try{
         const p=JSON.parse(init.body||'{}');
         p.service_mode=chosenMode==='salle'?'SALLE':(chosenMode==='livraison'?'LIVRAISON':'EMPORTER');
         p.ticket_type=chosenMode==='salle'?'Salle':(chosenMode==='livraison'?'Livraison':'Emporter');
         p.table_number=chosenMode==='salle'?selectedTable:null;
         init=Object.assign({},init,{body:JSON.stringify(p)});
       }catch(e){}
     }
     return nativeFetch(input,init);
   };

   document.addEventListener('bechefaa:new-order',clearChoice);
   clearChoice();
 });
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
