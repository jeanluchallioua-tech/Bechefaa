"""Couche visuelle POS calée sur la maquette sombre BÉCHÉFAA.

Aucune logique métier n'est modifiée. La couche enveloppe la vue /pos existante,
recolore/recompose le rendu et synchronise le bouton Sur place avec le sélecteur
de tables Phase 3.6 déjà existant.
"""


def register_pos_reference_dark(app):
    if getattr(app, "_bechefaa_pos_reference_dark", False):
        return

    original = app.view_functions.get("pos")
    if original is None:
        return

    addon = r'''
<style id="pos-reference-dark-style">
:root{
  --ref-bg:#080a0c;--ref-panel:#0d1013;--ref-panel2:#12161a;--ref-panel3:#171c21;
  --ref-line:#272d33;--ref-line2:#343b43;--ref-text:#f5f3ef;--ref-muted:#8d949d;
  --ref-gold:#e8b44a;--ref-gold2:#f2c35b;--ref-red:#c85448;--ref-green:#40b779;
}
body{background:var(--ref-bg)!important;color:var(--ref-text)!important}
.top{height:58px!important;min-height:58px!important;background:#090b0d!important;border-bottom:1px solid #20252b!important;color:#fff!important;padding:0 22px 0 220px!important}
.top>b{display:none!important}.top .status{margin-left:auto!important;color:#c7ccd1!important;font-size:12px!important}.layout{grid-template-columns:210px minmax(0,1fr) 440px!important;height:calc(100vh - 58px)!important;background:var(--ref-bg)!important}

/* rail gauche, proche de la maquette */
.pos-v3-rail{min-width:210px!important;width:210px!important;background:#0b0e11!important;border-right:1px solid #20252b!important;padding:20px 12px!important;align-items:stretch!important;gap:8px!important}
.pos-v3-brand{width:100%!important;height:128px!important;background:transparent!important;color:var(--ref-gold)!important;border-radius:0!important;box-shadow:none!important;margin:0 0 14px!important;font-size:0!important;position:relative!important}
.pos-v3-brand:before{content:'B';display:block;text-align:center;font-family:Georgia,serif;font-size:66px;line-height:66px;color:var(--ref-gold);font-weight:400}
.pos-v3-brand:after{content:'BÉCHÉFAA\A GOOD FOOD';white-space:pre;display:block;text-align:center;font-size:15px;letter-spacing:4px;line-height:26px;color:var(--ref-gold)}
.pos-v3-nav{min-height:60px!important;width:100%!important;display:flex!important;flex-direction:row!important;justify-content:flex-start!important;align-items:center!important;gap:15px!important;padding:0 18px!important;border-radius:9px!important;color:#b9bec5!important;font-size:14px!important;text-align:left!important}
.pos-v3-nav span{font-size:22px!important;width:26px;text-align:center}.pos-v3-nav:hover{background:#15191e!important;border-color:#262c33!important}.pos-v3-nav.active{background:linear-gradient(90deg,#3a2d15,#221b10)!important;border:1px solid #745b28!important;color:#fff!important;box-shadow:inset 3px 0 0 var(--ref-gold)!important}
.pos-v3-nav.active:after{content:'Nouvelle commande';font-size:14px}.pos-v3-nav.active{font-size:0!important}.pos-v3-nav.active span{font-size:22px!important}.pos-v3-rail-spacer{flex:1!important}

/* centre sombre */
.main{background:#090b0e!important;color:#fff!important;overflow:auto!important}.pos-v3-toolbar{position:sticky!important;top:0!important;z-index:50!important;background:#0c0f12!important;border-bottom:1px solid #20252b!important;padding:15px 18px 13px!important;display:grid!important;grid-template-columns:1fr auto!important;gap:12px!important}.pos-v3-service{grid-column:1/2!important;display:grid!important;grid-template-columns:repeat(3,1fr)!important;gap:12px!important}.pos-v3-service .ticket-choice{display:contents!important}.pos-v3-service .ticket-choice button{height:66px!important;border:1px solid #30363d!important;border-radius:8px!important;background:#101418!important;color:#f0f1f2!important;font-size:15px!important;font-weight:900!important;letter-spacing:.3px!important}.pos-v3-service .ticket-choice button.active{background:linear-gradient(180deg,#302716,#201a0f)!important;color:#f6d17a!important;border:2px solid var(--ref-gold)!important;box-shadow:0 0 0 1px rgba(232,180,74,.12),inset 0 0 25px rgba(232,180,74,.05)!important}.pos-v3-clock{grid-column:2!important;grid-row:1!important;color:#aeb4ba!important}.pos-v3-time{color:#fff!important}.pos-v3-user{background:#11161b!important;border:1px solid #2c333a!important}.pos-v3-search{grid-column:1/3!important;height:56px!important;border:1px solid #30363d!important;border-radius:8px!important;background:#101418!important;color:#fff!important;padding:0 18px!important;font-size:15px!important}.pos-v3-search::placeholder{color:#777f88}.pos-v3-search:focus{border-color:#6c5730!important;box-shadow:none!important;background:#11161a!important}
.title{display:none!important}
.cats{background:#0b0e11!important;padding:12px 18px!important;gap:10px!important;border-bottom:1px solid #20252b!important;overflow-x:auto!important}.cat{background:#111519!important;color:#e7e8e9!important;border:1px solid #2a3037!important;border-radius:8px!important;padding:13px 22px!important;font-size:13px!important}.cat:hover{background:#171c21!important;border-color:#4b4030!important}.cat.active{background:linear-gradient(180deg,#f0c56a,#dca83e)!important;color:#111!important;border-color:#e7b34a!important}
.grid{padding:18px!important;grid-template-columns:repeat(auto-fill,minmax(190px,1fr))!important;gap:14px!important}.product{background:#0f1316!important;border:1px solid #292f35!important;border-radius:8px!important;padding:10px!important;min-height:250px!important;color:#fff!important;box-shadow:none!important}.product:hover{transform:none!important;border-color:#6e572c!important;box-shadow:0 0 0 1px rgba(232,180,74,.1)!important}.product-photo{height:148px!important;border-radius:6px!important;background:#090b0d!important}.name{font-size:15px!important;color:#f7f7f6!important}.meta{color:#747c84!important}.badge{background:#302715!important;color:#e7bd5d!important}.price{color:var(--ref-gold2)!important;font-size:20px!important}.product:after{content:'+';display:flex;align-items:center;justify-content:center;width:38px;height:38px;border-radius:50%;background:var(--ref-gold);color:#111;font-size:24px;font-weight:900;position:absolute;right:12px;bottom:11px}.product{position:relative!important}.price{padding-right:48px!important}

/* tables sur place */
#phase36-table-selector{display:none!important;margin:0!important;padding:0 18px 14px!important;background:#0c0f12!important}
body.pos-ref-salle #phase36-table-selector{display:block!important}#phase36-table-selector>div:first-child{display:none!important}#phase36-table-selector>div:nth-child(2){display:none!important}#p36-tables{display:grid!important;grid-template-columns:repeat(9,minmax(72px,1fr))!important;gap:7px!important;margin:0!important}#p36-tables button{height:44px!important;background:#111519!important;color:#e9eaeb!important;border:1px solid #30363d!important;border-radius:7px!important;font-size:12px!important;font-weight:900!important}#p36-tables button[style*="d97706"],#p36-tables button[style*="rgb(217, 119, 6)"]{background:var(--ref-gold)!important;color:#111!important;border-color:var(--ref-gold)!important}

/* droite */
.cart{background:#0b0e11!important;color:#fff!important;border-left:1px solid #252b31!important;box-shadow:none!important}.cart:before{content:'Commande en cours'!important;padding:20px 18px 14px!important;font-size:20px!important;letter-spacing:0!important;color:#fff!important;text-transform:none!important;border-bottom:1px solid #242a30!important}.cart>.ticket-choice{display:none!important}.pos-recent-orders-btn{background:#101418!important;color:#e7e9eb!important;border:1px solid #2d3339!important;margin:10px 16px!important;width:calc(100% - 32px)!important}.touch-client-summary{background:#101418!important;color:#fff!important;border-color:#2c3238!important}.touch-client-summary span{color:#8f969e!important}.touch-client-summary .tc-edit{background:#1b2026!important}.order-box{padding:8px 18px 12px!important}.order-box>h2{display:none!important}.empty{color:#858c94!important}.order-line{border-bottom:1px solid #262c32!important}.order-line-head{color:#fff!important}.order-opts{color:#a9afb5!important}.remove{color:#d46a60!important}.order-total{border-top:1px solid #343a40!important;color:#fff!important;font-size:28px!important}.order-total span:last-child{color:var(--ref-gold2)!important}
#options{background:#0f1316!important;border:1px solid #2a3036!important;color:#fff!important}.selection-summary{background:#0b0e11!important;border-color:#292f35!important;color:#fff!important}.opt-group{border-top-color:#292f35!important}.rule{color:#858c94!important}.opt-value{background:#151a1f!important;color:#e7e9ea!important;border-color:#2b3239!important}.opt-value:hover{background:#1a2026!important}.opt-value.selected{background:#2b2415!important;color:#f2c45e!important;border-color:#7b612d!important}.action.add{background:var(--ref-gold)!important;color:#111!important}.action.save{background:#13171b!important;color:#fff!important;border:1px solid #484f56!important;min-height:64px!important;font-size:16px!important}.action.kitchen{background:linear-gradient(180deg,#f0c568,#e4ad43)!important;color:#111!important;min-height:64px!important;font-size:16px!important}
.pos-v2-upsell{background:#101418!important;border:1px solid #34302a!important;color:#fff!important;margin:8px 16px 14px!important}.pos-v2-upsell-head b{color:#fff!important}.pos-v2-upsell-head small{color:#d9ab4e!important}.pos-v2-upsell-item{background:#0b0e11!important;border-color:#2b3036!important;color:#fff!important}.pos-v2-upsell-price{color:var(--ref-gold)!important}.pos-v2-upsell-add{background:var(--ref-gold)!important;color:#111!important}
.note{display:none!important}

@media(max-width:1250px){.layout{grid-template-columns:175px minmax(0,1fr) 380px!important}.pos-v3-rail{min-width:175px!important;width:175px!important}.grid{grid-template-columns:repeat(auto-fill,minmax(165px,1fr))!important}#p36-tables{grid-template-columns:repeat(5,1fr)!important}}
</style>
<script id="pos-reference-dark-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   // Libellés de la maquette
   const salle=document.querySelector('.ticket-choice [data-ticket="Salle"]');
   const emporter=document.querySelector('.ticket-choice [data-ticket="Emporter"]');
   const livraison=document.querySelector('.ticket-choice [data-ticket="Livraison"]');
   if(salle)salle.textContent='🍴  SUR PLACE';
   if(emporter)emporter.textContent='🛍  À EMPORTER';
   if(livraison)livraison.textContent='🛵  LIVRAISON';

   // Complète le rail comme sur la référence sans modifier les routes existantes.
   const rail=document.querySelector('.pos-v3-rail');
   if(rail){
     const links=rail.querySelectorAll('.pos-v3-nav');
     if(links[0]){links[0].innerHTML='<span>＋</span>';links[0].classList.add('active')}
     if(links[1])links[1].innerHTML='<span>▤</span>Commandes';
     if(links[2])links[2].innerHTML='<span>♨</span>Cuisine';
     const spacer=rail.querySelector('.pos-v3-rail-spacer');
     if(spacer&&!rail.querySelector('[data-ref-clients]')){
       const clients=document.createElement('a');clients.className='pos-v3-nav';clients.href='/clients';clients.dataset.refClients='1';clients.innerHTML='<span>♙</span>Clients';rail.insertBefore(clients,spacer);
       const admin=document.createElement('a');admin.className='pos-v3-nav';admin.href='/administration';admin.innerHTML='<span>▥</span>Administration';rail.insertBefore(admin,spacer);
     }
     const last=rail.querySelector('.pos-v3-nav:last-child');if(last)last.innerHTML='<span>⚙</span>Paramètres';
   }

   function selector(){return document.getElementById('phase36-table-selector')}
   function moveSelector(){
     const s=selector(),main=document.querySelector('.main'),toolbar=document.querySelector('.pos-v3-toolbar');
     if(s&&main&&toolbar&&s.parentNode!==main)toolbar.insertAdjacentElement('afterend',s);
   }
   moveSelector();setTimeout(moveSelector,100);

   function setMode(mode){
     document.body.classList.toggle('pos-ref-salle',mode==='Salle');
     setTimeout(moveSelector,0);
     if(mode==='Salle')document.getElementById('p36-salle')?.click();
     else if(mode==='Emporter')document.getElementById('p36-emporter')?.click();
   }
   document.addEventListener('click',function(e){const b=e.target.closest('.ticket-choice [data-ticket]');if(b)setMode(b.dataset.ticket)});
   const active=document.querySelector('.ticket-choice [data-ticket].active');setMode(active?active.dataset.ticket:'Salle');

   // met le bloc upsell juste avant les totaux/actions quand il existe
   const order=document.getElementById('order');
   if(order){new MutationObserver(function(){const u=document.querySelector('.pos-v2-upsell');if(u&&u.previousElementSibling!==order)order.insertAdjacentElement('afterend',u)}).observe(order,{childList:true,subtree:true})}
 })
})();
</script>
'''

    def pos_reference_view(*args, **kwargs):
        response = app.make_response(original(*args, **kwargs))
        try:
            if response.status_code == 200 and response.mimetype == "text/html":
                html = response.get_data(as_text=True)
                if "pos-reference-dark-style" not in html:
                    html = html.replace("</body>", addon + "</body>")
                    response.set_data(html)
                    response.content_length = len(response.get_data())
                response.headers["X-Bechefaa-POS-Reference"] = "dark-mockup"
        except Exception:
            pass
        return response

    app.view_functions["pos"] = pos_reference_view
    app._bechefaa_pos_reference_dark = True
