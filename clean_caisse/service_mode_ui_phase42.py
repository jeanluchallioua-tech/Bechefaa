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
#phase42-table-grid button.table-occupied,#svc-tables button.table-occupied{background:#b42318!important;color:#fff!important;border-color:#b42318!important;opacity:1;cursor:not-allowed}
#phase42-table-grid button.table-selected,#svc-tables button.table-selected{background:#d9a62e!important;color:#111!important;border-color:#d9a62e!important}
#phase42-table-grid button:disabled,#svc-tables button:disabled{cursor:not-allowed}
</style>
<script id="phase42-service-mode-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   const ticket=document.querySelector('.ticket-choice');if(!ticket)return;
   let chosenMode=null,selectedTable=null,known=false,states=[],choosing=false,refreshing=null,renewing=false,choiceVersion=0;
   const nativeFetch=window.fetch.bind(window);
   let token='';
   try{token=sessionStorage.getItem('bechefaa_table_session')||''}catch(_){}
   if(!token){token=Array.from(crypto.getRandomValues(new Uint8Array(24)),b=>b.toString(16).padStart(2,'0')).join('');try{sessionStorage.setItem('bechefaa_table_session',token)}catch(_){}}
   let grid=document.getElementById('phase42-table-grid');
   if(!grid){grid=document.createElement('div');grid.id='phase42-table-grid';grid.innerHTML=Array.from({length:9},(_,i)=>'<button type="button" data-phase42-table="'+(i+1)+'">Table '+(i+1)+'</button>').join('');const toolbar=ticket.closest('.pos-v3-toolbar');(toolbar||ticket.parentElement).insertAdjacentElement('afterend',grid)}
   function message(text){
     const target=document.getElementById('order-message');if(target){const error=document.createElement('div');error.className='error';error.textContent=text;target.replaceChildren(error)}
     let note=document.getElementById('svc-table-message');
     const step=document.getElementById('svc-table-step');
     if(!note&&step){note=document.createElement('p');note.id='svc-table-message';note.setAttribute('role','status');note.style.cssText='color:#9d261d;text-align:center;font-weight:800';step.appendChild(note)}
     if(note)note.textContent=text;
   }
   function paint(){
     ticket.querySelectorAll('[data-ticket]').forEach(b=>b.classList.toggle('active',String(b.dataset.ticket||'').toLowerCase()===chosenMode));
     grid.classList.toggle('show',chosenMode==='salle');
     document.querySelectorAll('[data-phase42-table],#svc-tables [data-table]').forEach(b=>{
       const number=Number(b.dataset.phase42Table||b.dataset.table),state=states.find(s=>s.table_number===number);
       const mine=!!state&&state.mine&&!state.occupied,on=number===selectedTable;
       const busy=!!state&&(state.occupied||(state.reserved&&!state.mine));
       b.disabled=!known||choosing||busy;b.classList.toggle('active',on);b.classList.toggle('table-occupied',busy);b.classList.toggle('table-selected',on||mine);
       b.setAttribute('aria-pressed',on?'true':'false');
       b.textContent='Table '+number+(!known?' · Vérification…':busy?' · Occupée':on||mine?' · Sélectionnée':' · Libre');
       b.title=state&&state.order_num?'Occupée · commande #'+state.order_num:busy?'Table réservée pour une autre commande':'';
     });
   }
   async function refresh(){
     if(refreshing)return refreshing;
     refreshing=(async()=>{
       try{
         const r=await nativeFetch('/api/tables-phase36/availability',{cache:'no-store',headers:{'X-BECHEFAA-TABLE-TOKEN':token}}),d=await r.json();
         if(!r.ok||!d.ok||!Array.isArray(d.tables))throw Error();
         states=d.tables;known=true;paint();return true;
       }catch(_){known=false;paint();return false}
       finally{refreshing=null}
     })();return refreshing;
   }
   let reservationQueue=Promise.resolve();
   function reservation(number,renewOnly=false,previousTable=null){
     const operation=async()=>{
     const r=await nativeFetch('/api/tables-phase36/reservation',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({token,table_number:number,renew_only:renewOnly,previous_table:previousTable})});
     const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Réservation impossible');return d;
     };
     const pending=reservationQueue.then(operation,operation);reservationQueue=pending.catch(()=>{});return pending;
   }
   function release(){choiceVersion++;const old=selectedTable;selectedTable=null;if(old)reservation(null,false,old).catch(()=>{});paint()}
   function clearChoice(){release();chosenMode=null;paint();refresh()}
   async function select(number){
     if(choosing)return false;const version=++choiceVersion;choosing=true;paint();
     try{
       await reservation(number);if(version!==choiceVersion){await reservation(null,false,number);return false}selectedTable=number;chosenMode='salle';
       if(typeof TICKET_TYPE!=='undefined')TICKET_TYPE='Salle';
       if(typeof renderOrder==='function')renderOrder();
       const note=document.getElementById('svc-table-message');if(note)note.textContent='';
       return true;
     }catch(error){message(error.message||'Impossible de réserver cette table.');return false}
     finally{choosing=false;await refresh();paint()}
   }
   ticket.addEventListener('click',function(e){
     const b=e.target.closest('[data-ticket]');if(!b)return;if(choosing){e.preventDefault();e.stopImmediatePropagation();return}
     const mode=String(b.dataset.ticket||'').toLowerCase();
     if(mode==='salle'&&chosenMode==='salle'){clearChoice();return}
     chosenMode=mode==='livraison'?'livraison':mode==='salle'?'salle':'emporter';
     if(chosenMode!=='salle')release();paint();refresh();
   },true);
   grid.addEventListener('click',e=>{const b=e.target.closest('[data-phase42-table]');if(b&&!b.disabled)select(Number(b.dataset.phase42Table))});
   window.bechefaaTables={select,refresh,release};
   window.fetch=async function(input,init){
     const url=typeof input==='string'?input:(input&&input.url)||'';
     const creating=url==='/api/orders'&&init&&String(init.method||'GET').toUpperCase()==='POST';
     if(creating){
       if(!chosenMode){message('Choisissez Sur place, À emporter ou Livraison.');throw Error('Choisissez le mode de service')}
       if(chosenMode==='salle'&&!selectedTable){message('Choisissez une table libre de 1 à 9.');throw Error('Choisissez une table libre')}
       const p=JSON.parse(init.body||'{}');
       p.service_mode=chosenMode==='salle'?'SALLE':chosenMode==='livraison'?'LIVRAISON':'EMPORTER';
       p.ticket_type=chosenMode==='salle'?'Salle':chosenMode==='livraison'?'Livraison':'Emporter';
       p.table_number=chosenMode==='salle'?selectedTable:null;p.table_reservation_token=token;
       init=Object.assign({},init,{body:JSON.stringify(p)});
     }
     const response=await nativeFetch(input,init);
     if(creating&&response.ok){
       try{const d=await response.clone().json();if(d.ok&&d.id){selectedTable=null;chosenMode=null;paint();refresh()}}catch(_){}
     }else if(url.includes('/api/orders/')&&init&&String(init.method||'GET').toUpperCase()!=='GET'){refresh()}
     return response;
   };
   document.addEventListener('bechefaa:new-order',clearChoice);
   document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh()});
   setInterval(()=>{if(!document.hidden)refresh()},5000);
   setInterval(async()=>{
     if(!selectedTable||document.hidden||renewing||choosing)return;
     renewing=true;const number=selectedTable;
     try{await reservation(number,true)}catch(error){if(selectedTable!==number)return;selectedTable=null;message(error.message||'Table indisponible : choisissez une table libre.');paint();refresh()}
     finally{renewing=false}
   },25000);
   paint();refresh();
 });
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response

