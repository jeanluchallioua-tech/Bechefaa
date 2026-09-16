"""Finition ergonomique POS : options en modale et upsell à l'enregistrement.

Couche d'interface uniquement : réutilise showOptions/renderOptions/addCurrent/saveOrder
sans modifier les règles métier, les prix, PostgreSQL ou la cuisine.
"""


def register_pos_options_modal_final(app):
    if getattr(app, "_bechefaa_pos_options_modal_final", False):
        return
    original = app.view_functions.get("pos")
    if original is None:
        return

    addon = r'''
<style id="pos-options-modal-final-style">
/* Modes de service avec icônes visibles. */
.pos-v3-service .ticket-choice button{display:flex!important;align-items:center!important;justify-content:center!important;gap:10px!important}
.pos-final-mode-icon{font-size:20px!important;line-height:1!important;display:inline-block!important}

/* Catégories : une seule ligne, lisible, sans ascenseur horizontal. */
.cats{display:flex!important;flex-wrap:nowrap!important;align-items:center!important;justify-content:space-between!important;gap:6px!important;padding:10px 16px 11px!important;overflow:hidden!important;white-space:nowrap!important}
.cat{flex:0 1 auto!important;min-width:0!important;padding:10px 12px!important;font-size:11.5px!important;line-height:1.1!important;white-space:nowrap!important}
@media(max-width:1500px){.cats{gap:4px!important;padding-left:10px!important;padding-right:10px!important}.cat{padding:9px 9px!important;font-size:10.5px!important}}

/* Le bloc options quitte la colonne commande et devient une fenêtre tactile. */
.pos-final-options-overlay{display:none;position:fixed;inset:0;z-index:32000;background:rgba(0,0,0,.78);align-items:center;justify-content:center;padding:22px}
.pos-final-options-overlay.open{display:flex}
.pos-final-options-panel{width:min(760px,96vw);max-height:90vh;display:flex;flex-direction:column;background:#0f1316;border:1px solid #343b42;border-radius:16px;box-shadow:0 28px 80px #000b;overflow:hidden;color:#fff}
.pos-final-options-head{display:flex;align-items:center;gap:12px;padding:16px 18px;border-bottom:1px solid #2a3036;background:#0b0e11}
.pos-final-options-head h2{margin:0;flex:1;font-size:20px;color:#fff}
.pos-final-options-close{width:42px;height:42px;border-radius:9px;border:1px solid #3b4249;background:#171c21;color:#fff;font-size:26px;font-weight:800;cursor:pointer}
.pos-final-options-body{padding:14px;overflow:auto;min-height:0}
.pos-final-options-overlay #options{display:block!important;margin:0!important;background:#0f1316!important;border:0!important;padding:0!important}
.pos-final-options-overlay #options .action.add{position:sticky!important;bottom:0!important;z-index:5!important;margin:14px 0 0!important;min-height:56px!important;background:linear-gradient(180deg,#f0c568,#e4ad43)!important;color:#111!important;border-radius:9px!important;font-size:15px!important;font-weight:950!important;box-shadow:0 -8px 18px #0f1316!important}
body.pos-ref-options-closed .pos-final-options-overlay.open #options{display:block!important}

/* Le panneau commande reste compact maintenant que les options sont en modale. */
.cart #options{display:none!important}
</style>
<script id="pos-options-modal-final-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   const norm=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();

   /* Icônes et libellés des trois modes. */
   function paintModes(){
     const salle=document.querySelector('.ticket-choice [data-ticket="Salle"]');
     const emp=document.querySelector('.ticket-choice [data-ticket="Emporter"]');
     const liv=document.querySelector('.ticket-choice [data-ticket="Livraison"]');
     if(salle)salle.innerHTML='<span class="pos-final-mode-icon">🍴</span><span>SUR PLACE</span>';
     if(emp)emp.innerHTML='<span class="pos-final-mode-icon">🛍️</span><span>À EMPORTER</span>';
     if(liv)liv.innerHTML='<span class="pos-final-mode-icon">🛵</span><span>LIVRAISON</span>';
   }
   paintModes();setTimeout(paintModes,150);setTimeout(paintModes,500);

   const options=document.getElementById('options');
   if(!options)return;

   /* Création de la modale options en réutilisant le vrai #options du moteur actuel. */
   const overlay=document.createElement('div');overlay.className='pos-final-options-overlay';
   overlay.innerHTML='<div class="pos-final-options-panel"><div class="pos-final-options-head"><h2 id="pos-final-options-title">Options produit</h2><button type="button" class="pos-final-options-close" aria-label="Fermer">×</button></div><div class="pos-final-options-body"></div></div>';
   document.body.appendChild(overlay);
   overlay.querySelector('.pos-final-options-body').appendChild(options);
   const modalTitle=overlay.querySelector('#pos-final-options-title');
   const closeBtn=overlay.querySelector('.pos-final-options-close');

   let upsellFlow=false;
   let upsellPhase='drink';
   let waitingUpsellProduct=false;
   let savingAfterUpsell=false;
   const upsell=document.querySelector('.pos-ref-upsell-overlay');
   const upsellList=upsell?.querySelector('.pos-ref-upsell-list');
   const upsellNo=upsell?.querySelector('.pos-ref-no');
   const upsellModal=upsell?.querySelector('.pos-ref-modal');
   const upsellTitle=upsellModal?.querySelector('h2');

   function openOptions(name){
     document.body.classList.remove('pos-ref-options-closed');
     modalTitle.textContent=name?'Options • '+name:'Options produit';
     overlay.classList.add('open');
   }
   function closeOptions(){overlay.classList.remove('open')}
   closeBtn.addEventListener('click',closeOptions);
   overlay.addEventListener('click',e=>{if(e.target===overlay)closeOptions()});
   document.addEventListener('keydown',e=>{if(e.key==='Escape')closeOptions()});

   /* Ouvre la modale à chaque clic produit. Le moteur existant remplit #options. */
   document.addEventListener('click',function(e){
     const p=e.target.closest('.product');
     if(!p)return;
     setTimeout(()=>openOptions(p.dataset.name||''),0);
   },true);

   /* Ajouter à la commande depuis la modale : conserve addCurrent() et ferme ensuite. */
   options.addEventListener('click',function(e){
     const add=e.target.closest('[data-action="add-current"]');
     if(!add)return;
     e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
     const before=(typeof ORDER!=='undefined'&&Array.isArray(ORDER))?ORDER.length:0;
     if(typeof addCurrent==='function')addCurrent();
     const after=(typeof ORDER!=='undefined'&&Array.isArray(ORDER))?ORDER.length:before;
     if(after>before){
       closeOptions();
       if(waitingUpsellProduct){
         waitingUpsellProduct=false;
         setTimeout(function(){
           if(upsellPhase==='drink'){upsellPhase='dessert';openUpsellPhase()}
           else finishUpsellAndSave();
         },80);
       }
     }
   },true);

   function upsellItems(category){
     try{
       if(typeof DATA==='undefined'||!DATA||!Array.isArray(DATA.items)||typeof ORDER==='undefined')return[];
       const inCart=new Set((ORDER||[]).map(x=>String(x.product_id||'')));
       return DATA.items.filter(p=>p&&p.active!==false&&!inCart.has(String(p.id||''))&&norm(p.category)===category);
     }catch(e){return[]}
   }
   function euro(v){return Number(v||0).toFixed(2).replace('.',',')+' €'}
   function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
   function renderUpsell(){
     if(!upsell||!upsellList||!upsellNo)return;
     const cat=upsellPhase==='drink'?'boissons':'desserts';
     if(upsellTitle)upsellTitle.textContent=upsellPhase==='drink'?'Une boisson avec votre commande ?':'Un dessert pour terminer ?';
     upsellNo.textContent='Non merci';
     const items=upsellItems(cat);
     upsellList.innerHTML=items.length?items.map(p=>'<button type="button" class="pos-ref-upsell-item" data-final-upsell-id="'+esc(p.id)+'" data-final-upsell-name="'+esc(p.name)+'">'+(p.photo?'<img src="'+esc(p.photo)+'" alt="">':'')+'<b>'+esc(p.name)+'</b><span class="pos-ref-upsell-price">'+euro(p.price)+'</span></button>').join(''):'<div style="color:#a7adb4;padding:12px">Aucun produit disponible.</div>';
   }
   function openUpsellPhase(){
     if(!upsell){finishUpsellAndSave();return}
     upsellFlow=true;upsell.classList.add('open');setTimeout(renderUpsell,0);
   }
   function finishUpsellAndSave(){
     if(savingAfterUpsell)return;
     savingAfterUpsell=true;upsellFlow=false;if(upsell)upsell.classList.remove('open');
     setTimeout(()=>{try{if(typeof saveOrder==='function')saveOrder()}finally{setTimeout(()=>{savingAfterUpsell=false},300)}},40);
   }

   if(upsell){
     /* Bloque les ouvertures automatiques héritées : upsell uniquement lors de l'enregistrement. */
     new MutationObserver(function(){
       if(upsell.classList.contains('open')&&!upsellFlow)upsell.classList.remove('open');
     }).observe(upsell,{attributes:true,attributeFilter:['class']});

     upsell.addEventListener('click',function(e){
       const item=e.target.closest('[data-final-upsell-id]');
       if(item){
         e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
         upsell.classList.remove('open');
         waitingUpsellProduct=true;
         if(typeof showOptions==='function')showOptions(item.dataset.finalUpsellId,item.dataset.finalUpsellName);
         setTimeout(()=>openOptions(item.dataset.finalUpsellName),0);
         return;
       }
       if(e.target.closest('.pos-ref-no')){
         e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
         upsell.classList.remove('open');
         if(upsellPhase==='drink'){upsellPhase='dessert';setTimeout(openUpsellPhase,50)}else finishUpsellAndSave();
       }
     },true);
   }

   /* Enregistrer = Boissons -> Desserts -> enregistrement réel. */
   document.addEventListener('click',function(e){
     const save=e.target.closest('[data-action="save-order"]');
     if(!save||savingAfterUpsell)return;
     e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
     if(typeof ORDER==='undefined'||!Array.isArray(ORDER)||!ORDER.length)return;
     upsellPhase='drink';waitingUpsellProduct=false;openUpsellPhase();
   },true);
 })
})();
</script>
'''

    def pos_options_modal_view(*args, **kwargs):
        response = app.make_response(original(*args, **kwargs))
        try:
            if response.status_code == 200 and response.mimetype == "text/html":
                html = response.get_data(as_text=True)
                if "pos-options-modal-final-style" not in html:
                    html = html.replace("</body>", addon + "</body>")
                    response.set_data(html)
                    response.content_length = len(response.get_data())
                response.headers["X-Bechefaa-POS-Options"] = "modal-upsell-on-save"
        except Exception:
            pass
        return response

    app.view_functions["pos"] = pos_options_modal_view
    app._bechefaa_pos_options_modal_final = True
