"""Hotfix visuel/ergonomique du POS sombre.

Aucune modification métier, PostgreSQL, paiement ou cuisine.
"""


def register_pos_reference_hotfix(app):
    if getattr(app, "_bechefaa_pos_reference_hotfix", False):
        return
    original = app.view_functions.get("pos")
    if original is None:
        return

    addon = r'''
<style id="pos-reference-hotfix-style">
/* Logo / marque */
.pos-v3-brand{height:156px!important;width:100%!important;margin:0 0 12px!important;padding:6px 0!important;display:flex!important;flex-direction:column!important;align-items:center!important;justify-content:center!important;gap:9px!important;overflow:visible!important;transform:none!important}
.pos-v3-brand .pos-ref-logo{display:block!important;width:92px!important;height:92px!important;max-width:92px!important;object-fit:contain!important;margin:0 auto!important}
.pos-v3-brand .pos-ref-brandname{display:block!important;width:100%!important;text-align:center!important;color:#e8b44a!important;font-size:19px!important;font-weight:950!important;letter-spacing:3px!important;line-height:1.1!important;white-space:nowrap!important;overflow:visible!important}

/* Tables uniquement après clic explicite Sur place */
.pos-ref-tablebar{display:none!important}.pos-ref-tablebar.show{display:grid!important}

/* Catégories : jamais de fond blanc au survol */
.cat:hover{background:#171c21!important;color:#fff!important;border-color:#6e572c!important}
.cat.active,.cat.active:hover{background:linear-gradient(180deg,#f0c56a,#dca83e)!important;color:#111!important;border-color:#e7b34a!important}

/* Messages commande */
.cart #order-message{color:#fff!important}.cart .success{background:#10271c!important;color:#e7f8ed!important;border:1px solid #28593c!important}.cart .success b,.cart .success a{color:#f2c35b!important}.cart .error{background:#311614!important;color:#ffd9d5!important;border:1px solid #6f302b!important}.cart .error b{color:#fff!important}.cart #order-message a{color:#f2c35b!important}

/* Commandes récentes */
.pos-recent-backdrop{background:rgba(0,0,0,.78)!important}.pos-recent-panel{background:#0f1316!important;color:#fff!important;border:1px solid #30363d!important}.pos-recent-head{background:#0f1316!important;border-bottom:1px solid #2b3137!important;color:#fff!important}.pos-recent-head h2{color:#fff!important}.pos-recent-close{background:#20262c!important;color:#fff!important}.pos-recent-list{background:#0f1316!important;color:#fff!important}.pos-recent-row{background:#11161a!important;border:1px solid #2d3339!important;color:#fff!important}.pos-recent-title{color:#fff!important}.pos-recent-meta,.pos-recent-empty{color:#a7adb4!important}.pos-recent-actions a{color:#fff!important}
.pos-ref-history-link,.pos-ref-recent{background:transparent!important;border:1px solid transparent!important}.pos-ref-history-link:hover,.pos-ref-recent:hover{background:#15191e!important;border-color:#262c33!important}

/* Upsell : plus large, tous les produits pertinents */
.pos-ref-upsell-overlay .pos-ref-modal{width:min(760px,96vw)!important;max-height:88vh!important;display:flex!important;flex-direction:column!important}.pos-ref-upsell-list{grid-template-columns:repeat(2,minmax(0,1fr))!important;overflow:auto!important;max-height:62vh!important;padding-right:4px!important}.pos-ref-upsell-item{min-height:74px!important}.pos-ref-no{flex:0 0 auto!important}
@media(max-width:700px){.pos-ref-upsell-list{grid-template-columns:1fr!important}}
</style>
<script id="pos-reference-hotfix-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   const norm=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
   const euro=v=>Number(v||0).toFixed(2).replace('.',',')+' €';
   const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

   /* Marque */
   const rail=document.querySelector('.pos-v3-rail');
   const brand=rail?.querySelector('.pos-v3-brand');
   if(brand)brand.innerHTML='<img class="pos-ref-logo" src="https://bechefaa.fr/logo-bechefaa.jpg" alt="BÉCHÉFAA"><div class="pos-ref-brandname">BÉCHÉFAA</div>';

   /* Tables : masquées au départ, affichées uniquement après clic Sur place. */
   const tablebar=document.querySelector('.pos-ref-tablebar');
   function hideTables(){tablebar?.classList.remove('show')}
   hideTables();setTimeout(hideTables,80);setTimeout(hideTables,250);
   document.addEventListener('click',function(e){
     const b=e.target.closest('.ticket-choice [data-ticket]');if(!b)return;
     if(b.dataset.ticket==='Salle')tablebar?.classList.add('show');else tablebar?.classList.remove('show');
   },true);

   /* Rail : Commandes -> Historique + Commandes récentes séparé. */
   if(rail){
     const recent=rail.querySelector('.pos-ref-recent');
     if(recent){
       recent.innerHTML='<span>◷</span><span class="pos-ref-recent-label">Commandes récentes</span>';
       if(!rail.querySelector('.pos-ref-history-link')){
         const hist=document.createElement('a');hist.className='pos-v3-nav pos-ref-history-link';hist.href='/historique';hist.innerHTML='<span>▤</span>Commandes';
         rail.insertBefore(hist,recent);
       }
     }
   }

   /* Options : fermer après ajout et après envoi cuisine, rouvrir sur clic produit. */
   document.addEventListener('click',function(e){
     if(e.target.closest('.product'))document.body.classList.remove('pos-ref-options-closed');
     if(e.target.closest('[data-action="add-current"]'))setTimeout(()=>document.body.classList.add('pos-ref-options-closed'),0);
     if(e.target.closest('[data-action="send-kitchen"]')||e.target.closest('.pos-ref-kitchen'))setTimeout(()=>document.body.classList.add('pos-ref-options-closed'),0);
   },true);

   /* Masque les catégories de test indésirables. */
   function cleanCats(){document.querySelectorAll('.cat').forEach(b=>{const t=norm(b.textContent);if(t==='carte du soir'||t==='test v2')b.style.display='none'})}
   cleanCats();const cats=document.getElementById('cats');if(cats)new MutationObserver(cleanCats).observe(cats,{childList:true,subtree:true});

   /* Upsell : remplacer la limite de 3 par TOUS les produits pertinents. */
   const overlay=document.querySelector('.pos-ref-upsell-overlay');
   const list=overlay?.querySelector('.pos-ref-upsell-list');
   function renderAllUpsell(){
     if(!overlay||!list||!overlay.classList.contains('open'))return;
     try{
       if(typeof DATA==='undefined'||!DATA||!Array.isArray(DATA.items)||typeof ORDER==='undefined')return;
       const inCart=new Set((ORDER||[]).map(x=>String(x.product_id||'')));
       const allowed=new Set(['boissons','accompagnement','desserts']);
       const products=DATA.items.filter(p=>p&&p.active!==false&&!inCart.has(String(p.id||''))&&allowed.has(norm(p.category)));
       list.innerHTML=products.length?products.map(p=>'<button type="button" class="pos-ref-upsell-item" data-hotfix-upsell-id="'+esc(p.id)+'" data-hotfix-upsell-name="'+esc(p.name)+'">'+(p.photo?'<img src="'+esc(p.photo)+'" alt="">':'')+'<b>'+esc(p.name)+'</b><span class="pos-ref-upsell-price">'+euro(p.price)+'</span></button>').join(''):'<div style="color:#a7adb4;padding:12px">Aucune suggestion disponible.</div>';
     }catch(e){}
   }
   if(overlay){new MutationObserver(renderAllUpsell).observe(overlay,{attributes:true,attributeFilter:['class']});overlay.addEventListener('click',function(e){const b=e.target.closest('[data-hotfix-upsell-id]');if(!b)return;overlay.classList.remove('open');if(typeof showOptions==='function')showOptions(b.dataset.hotfixUpsellId,b.dataset.hotfixUpsellName)});}
 })
})();
</script>
'''

    def pos_hotfix_view(*args, **kwargs):
        response = app.make_response(original(*args, **kwargs))
        try:
            if response.status_code == 200 and response.mimetype == "text/html":
                html = response.get_data(as_text=True)
                if "pos-reference-hotfix-style" not in html:
                    html = html.replace("</body>", addon + "</body>")
                    response.set_data(html)
                    response.content_length = len(response.get_data())
                response.headers["X-Bechefaa-POS-Hotfix"] = "ergonomy-1"
        except Exception:
            pass
        return response

    app.view_functions["pos"] = pos_hotfix_view
    app._bechefaa_pos_reference_hotfix = True
