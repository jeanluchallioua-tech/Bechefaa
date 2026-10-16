"""Finition ergonomique POS : options en modale et upsell uniquement à l'enregistrement.

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
.pos-v3-service .ticket-choice button{display:flex!important;align-items:center!important;justify-content:center!important;gap:10px!important}
.pos-final-mode-icon{font-size:20px!important;line-height:1!important;display:inline-block!important}

/* Catégories : une seule ligne, lisible, sans ascenseur horizontal. */
.cats{display:flex!important;flex-wrap:nowrap!important;align-items:center!important;justify-content:space-between!important;gap:6px!important;padding:10px 16px 11px!important;overflow:hidden!important;white-space:nowrap!important}
.cat{flex:0 1 auto!important;min-width:0!important;padding:10px 12px!important;font-size:11.5px!important;line-height:1.1!important;white-space:nowrap!important}
@media(max-width:1500px){.cats{gap:4px!important;padding-left:10px!important;padding-right:10px!important}.cat{padding:9px 9px!important;font-size:10.5px!important}}

/* Tablette Samsung : catégories compactes sur 2 lignes, boutons plus hauts. */
html.bechefaa-tablet .cats{
  display:grid!important;
  grid-template-columns:repeat(5,160px)!important;
  grid-auto-rows:56px!important;
  gap:6px 8px!important;
  padding:8px 10px 10px!important;
  overflow:hidden!important;
  white-space:normal!important;
  align-items:stretch!important;
  justify-content:center!important;
}
html.bechefaa-tablet .cat{
  width:100%!important;
  min-width:0!important;
  height:56px!important;
  padding:6px 8px!important;
  font-size:17px!important;
  line-height:1.08!important;
  white-space:normal!important;
  display:flex!important;
  align-items:center!important;
  justify-content:center!important;
  text-align:center!important;
}

/* Options produit en fenêtre modale. */
.pos-final-options-overlay{display:none;position:fixed;inset:0;z-index:32000;background:rgba(17,24,39,.38);align-items:center;justify-content:center;padding:22px}
.pos-final-options-overlay.open{display:flex}
.pos-final-options-panel{width:min(760px,96vw);max-height:90vh;display:flex;flex-direction:column;background:#fff;border:1px solid #d9dde3;border-radius:16px;box-shadow:0 24px 70px #0004;overflow:hidden;color:#111827}
.pos-final-options-head{display:flex;align-items:center;gap:12px;padding:16px 18px;border-bottom:1px solid #e5e7eb;background:#fff}
.pos-final-options-head h2{margin:0;font-size:24px;color:#111827;font-weight:900}.pos-final-options-titlewrap{flex:1;min-width:0}.pos-final-options-desc{display:none;margin:8px 0 0;color:#374151;font-size:17px;line-height:1.42;font-weight:650}.pos-final-options-desc.show{display:block}.pos-final-options-diag{margin:7px 0 0;padding:6px 8px;border:1px solid #fed7aa;border-radius:6px;background:#fff7ed;color:#9a3412;font-size:11px;line-height:1.35;word-break:break-word}
.pos-final-options-close{width:42px;height:42px;border-radius:9px;border:1px solid #d1d5db;background:#f3f4f6;color:#111827;font-size:26px;font-weight:800;cursor:pointer}
.pos-final-options-body{padding:14px;overflow:auto;min-height:0}
.pos-final-options-overlay #options{display:block!important;margin:0!important;background:#fff!important;color:#111827!important;border:0!important;padding:0!important}
.pos-final-options-overlay #options .action.add{position:sticky!important;bottom:0!important;z-index:5!important;margin:14px 0 0!important;min-height:56px!important;background:linear-gradient(180deg,#f0c568,#e4ad43)!important;color:#111!important;border-radius:9px!important;font-size:15px!important;font-weight:950!important;box-shadow:0 -8px 18px #fff!important}
body.pos-ref-options-closed .pos-final-options-overlay.open #options{display:block!important}
.cart #options{display:none!important}

/* Thème clair commun options + upsell, proche du site. */
.pos-final-options-overlay .selection-summary{background:#f8fafc!important;color:#111827!important;border:1px solid #e5e7eb!important;font-size:17px!important}
.pos-final-options-overlay .opt-group{border-top-color:#e5e7eb!important}
.pos-final-options-overlay .opt-head,.pos-final-options-overlay .opt-head b{color:#111827!important;font-size:18px!important}
.pos-final-options-overlay .rule{color:#6b7280!important;font-size:14px!important}
.pos-final-options-overlay .opt-value{background:#fff!important;color:#111827!important;border:1px solid #d1d5db!important;font-size:17px!important;min-height:50px!important}
.pos-final-options-overlay .opt-value.selected{background:#fff7df!important;color:#111827!important;border:2px solid #d6a62d!important}
.pos-ref-upsell-overlay{background:rgba(17,24,39,.38)!important}
.pos-ref-upsell-overlay .pos-ref-modal{background:#fff!important;color:#111827!important;border:1px solid #d9dde3!important;box-shadow:0 24px 70px #0004!important}
.pos-ref-upsell-overlay .pos-ref-modal h2{color:#111827!important;font-size:24px!important;font-weight:900!important}
.pos-ref-upsell-overlay .pos-ref-upsell-item{background:#fff!important;color:#111827!important;border:1px solid #d1d5db!important;min-height:68px!important}
.pos-ref-upsell-overlay .pos-ref-upsell-item b{font-size:18px!important;color:#111827!important}
.pos-ref-upsell-overlay .pos-ref-upsell-price{font-size:18px!important;color:#8a6410!important}
.pos-ref-upsell-overlay .pos-ref-no{background:#f3f4f6!important;color:#111827!important;border:1px solid #d1d5db!important;font-size:17px!important;min-height:52px!important}

/* Tablette Samsung : options et groupes d'options plus lisibles. */
html.bechefaa-tablet .pos-final-options-panel{
  width:min(900px,94vw)!important;
}
html.bechefaa-tablet .pos-final-options-head{
  padding:18px 20px!important;
}
html.bechefaa-tablet .pos-final-options-head h2{
  font-size:26px!important;
}
html.bechefaa-tablet .pos-final-options-desc{
  font-size:18px!important;
  line-height:1.45!important;
}
html.bechefaa-tablet .pos-final-options-body{
  padding:18px!important;
}
html.bechefaa-tablet .pos-final-options-overlay .selection-summary{
  font-size:17px!important;
  line-height:1.35!important;
  padding:14px!important;
}
html.bechefaa-tablet .pos-final-options-overlay .selection-summary b{
  font-size:19px!important;
}
html.bechefaa-tablet .pos-final-options-overlay .selection-price{
  font-size:22px!important;
}
html.bechefaa-tablet .pos-final-options-overlay .opt-group{
  padding-top:16px!important;
  margin-top:16px!important;
}
html.bechefaa-tablet .pos-final-options-overlay .opt-head{
  margin-bottom:10px!important;
}
html.bechefaa-tablet .pos-final-options-overlay .opt-head b{
  font-size:20px!important;
  line-height:1.2!important;
}
html.bechefaa-tablet .pos-final-options-overlay .rule{
  font-size:15px!important;
  line-height:1.25!important;
}
html.bechefaa-tablet .pos-final-options-overlay .opt-value{
  min-height:54px!important;
  font-size:18px!important;
  line-height:1.25!important;
  padding:12px 14px!important;
  margin:7px 0!important;
  align-items:center!important;
}
html.bechefaa-tablet .pos-final-options-overlay #options .action.add{
  min-height:62px!important;
  font-size:19px!important;
}

/* Heure / utilisateur dans la barre supérieure globale. */
.top .pos-v3-clock{display:flex!important;position:static!important;grid-column:auto!important;grid-row:auto!important;margin:0!important;align-items:center!important;gap:9px!important;color:#aeb4ba!important}
.top .pos-v3-time{font-size:16px!important;color:#fff!important}.top .pos-v3-user{width:34px!important;height:34px!important;flex:0 0 34px!important}
.top{padding-left:16px!important}
</style>
<script id="pos-options-modal-final-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   const norm=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
   const euro=v=>Number(v||0).toFixed(2).replace('.',',')+' €';
   const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

   function paintModes(){
     const salle=document.querySelector('.ticket-choice [data-ticket="Salle"]');
     const emp=document.querySelector('.ticket-choice [data-ticket="Emporter"]');
     const liv=document.querySelector('.ticket-choice [data-ticket="Livraison"]');
     if(salle)salle.innerHTML='<span class="pos-final-mode-icon">🍴</span><span>SUR PLACE</span>';
     if(emp)emp.innerHTML='<span class="pos-final-mode-icon">🛍️</span><span>À EMPORTER</span>';
     if(liv)liv.innerHTML='<span class="pos-final-mode-icon">🛵</span><span>LIVRAISON</span>';
   }
   paintModes();setTimeout(paintModes,150);setTimeout(paintModes,500);

   /* Déplace heure + Administrateur + AD dans la barre tout en haut à gauche. */
   const top=document.querySelector('.top');
   const clock=document.querySelector('.pos-v3-clock');
   if(top&&clock&&clock.parentNode!==top)top.insertBefore(clock,top.firstChild);

   const options=document.getElementById('options');
   if(!options)return;

   const overlay=document.createElement('div');overlay.className='pos-final-options-overlay';
   overlay.innerHTML='<div class="pos-final-options-panel"><div class="pos-final-options-head"><div class="pos-final-options-titlewrap"><h2 id="pos-final-options-title">Options produit</h2><p id="pos-final-options-desc" class="pos-final-options-desc"></p></div><button type="button" class="pos-final-options-close" aria-label="Fermer">×</button></div><div class="pos-final-options-body"></div></div>';
   document.body.appendChild(overlay);
   overlay.querySelector('.pos-final-options-body').appendChild(options);
   const modalTitle=overlay.querySelector('#pos-final-options-title');
   const modalDesc=overlay.querySelector('#pos-final-options-desc');
   const closeBtn=overlay.querySelector('.pos-final-options-close');
   function refreshProductDescription(){
     const p=(typeof currentProduct!=='undefined'&&currentProduct)?currentProduct:null;
     const desc=p&&p.description!=null?String(p.description).trim():'';
     if(modalDesc){
       modalDesc.textContent=desc;
       modalDesc.classList.toggle('show',!!desc);
     }
   }
   const descDiagObserver=new MutationObserver(function(){
     setTimeout(()=>{refreshProductDescription()},0);
     setTimeout(()=>{refreshProductDescription()},80);
   });
   descDiagObserver.observe(options,{childList:true,subtree:true,characterData:true});

   function openOptions(name){
     document.body.classList.remove('pos-ref-options-closed');
     modalTitle.textContent=name?'Options • '+name:'Options produit';
     refreshProductDescription();
     
     setTimeout(()=>{refreshProductDescription()},120);
     setTimeout(()=>{refreshProductDescription()},400);
     overlay.classList.add('open');
   }
   function closeOptions(){overlay.classList.remove('open')}
   closeBtn.addEventListener('click',closeOptions);
   overlay.addEventListener('click',e=>{if(e.target===overlay)closeOptions()});
   document.addEventListener('keydown',e=>{if(e.key==='Escape')closeOptions()});

   /* Un clic produit ouvre uniquement ses options. Aucun upsell ici. */
   document.addEventListener('click',function(e){
     const p=e.target.closest('.product');
     if(!p)return;
     setTimeout(()=>openOptions(p.dataset.name||''),0);
   },true);

   /* Add the selected product once, without any drink/dessert upsell flow. */
   options.addEventListener('click',function(e){
     const add=e.target.closest('[data-action="add-current"]');
     if(!add)return;
     e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
     const before=(typeof ORDER!=='undefined'&&Array.isArray(ORDER))?ORDER.length:0;
     if(typeof addCurrent==='function')addCurrent();
     if(typeof ORDER!=='undefined'&&ORDER.length>before)closeOptions();
   },true);
 })
})();
</script>
<script src="/static/pos-pending-edit.js?v=2" defer></script>
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
                response.headers["X-Bechefaa-POS-Options"] = "modal-upsell-save-only-v2"
        except Exception:
            pass
        return response

    app.view_functions["pos"] = pos_options_modal_view
    app._bechefaa_pos_options_modal_final = True
