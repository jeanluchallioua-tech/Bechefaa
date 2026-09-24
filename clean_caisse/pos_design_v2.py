"""Design POS professionnel directement applique a /pos.

La couche ne modifie aucune logique metier : elle reorganise uniquement le DOM/CSS
existant pour retrouver la maquette validee (navigation gauche, barre service/recherche,
categories horizontales, produits au centre, ticket/actions a droite, upsell compact).
"""


def register_pos_design_v2(app):
    if getattr(app, "_bechefaa_pos_v2_wrapped", False):
        return

    original = app.view_functions.get("pos")
    if original is None:
        return

    addon = r'''
<style id="pos-design-v2-style">
:root{
  --pos-bg:#f3f4f6;--pos-dark:#111418;--pos-dark2:#1b2026;--pos-dark3:#272d35;
  --pos-gold:#e0ad2f;--pos-gold2:#f2c34b;--pos-line:#e2e5e9;--pos-muted:#7c8490;
  --pos-green:#1c8b5a;--pos-orange:#d88918;--pos-red:#b42318;
}
*{box-sizing:border-box}
body{background:var(--pos-bg)!important;color:#15181c!important;overflow:hidden!important}
.top{height:66px!important;min-height:66px!important;background:#fff!important;color:#111!important;border-bottom:1px solid var(--pos-line)!important;padding:0 18px 0 96px!important;gap:10px!important;box-shadow:none!important;position:relative!important;z-index:60!important}
.top>b{font-size:20px!important;color:#111!important;letter-spacing:-.3px!important}.top>b:after{content:'  POS';font-size:10px!important;color:#9a7415!important;letter-spacing:1px!important}
.top .navlink{display:none!important}.top .status{margin-left:auto!important;color:#68707b!important;font-size:12px!important;font-weight:800!important}.navspacer{display:none!important}
.layout{display:grid!important;grid-template-columns:88px minmax(0,1fr) 390px!important;height:calc(100vh - 66px)!important;min-height:0!important}

/* Navigation gauche */
.pos-v3-rail{grid-column:1;grid-row:1;min-width:88px;background:var(--pos-dark)!important;border-right:1px solid #252a31;display:flex;flex-direction:column;align-items:center;padding:12px 8px;gap:8px;overflow:auto;z-index:40}
.pos-v3-brand{width:54px;height:54px;border-radius:16px;background:var(--pos-gold);color:#111;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:1000;margin-bottom:6px;box-shadow:0 7px 18px #0003}
.pos-v3-nav{width:100%;min-height:60px;border:1px solid transparent;border-radius:13px;color:#d5dae0;text-decoration:none;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:5px;font-size:10px;font-weight:900;line-height:1.1;text-align:center;padding:6px 3px}
.pos-v3-nav span{font-size:20px;line-height:1}.pos-v3-nav:hover{background:var(--pos-dark2);border-color:#30363f}.pos-v3-nav.active{background:var(--pos-gold);color:#111}.pos-v3-rail-spacer{flex:1}

/* Zone centre */
.main{grid-column:2!important;grid-row:1!important;padding:0!important;background:var(--pos-bg)!important;overflow:auto!important;min-width:0!important}
.pos-v3-toolbar{position:sticky;top:0;z-index:35;background:#fff;border-bottom:1px solid var(--pos-line);padding:12px 16px;display:grid;grid-template-columns:minmax(340px,auto) minmax(220px,1fr) auto;gap:12px;align-items:center}
.pos-v3-service{display:flex;gap:7px;min-width:0}.pos-v3-service .ticket-choice{display:flex!important;gap:7px!important;margin:0!important;padding:0!important;position:static!important;background:transparent!important;width:auto!important}.pos-v3-service .ticket-choice button{min-height:44px!important;padding:0 16px!important;border:1px solid #d9dde2!important;border-radius:11px!important;background:#f7f8fa!important;color:#262b31!important;font-size:12px!important;font-weight:900!important;box-shadow:none!important}.pos-v3-service .ticket-choice button.active{background:var(--pos-dark)!important;color:#fff!important;border-color:var(--pos-dark)!important}
.pos-v3-search{height:44px;border:1px solid #d8dce2;border-radius:11px;background:#f8f9fa;padding:0 14px;font-size:14px;font-weight:700;outline:none;width:100%}.pos-v3-search:focus{border-color:#c99b27;box-shadow:0 0 0 3px rgba(224,173,47,.13);background:#fff}
.pos-v3-clock{display:flex;align-items:center;gap:9px;white-space:nowrap;color:#5d6570;font-size:12px;font-weight:800}.pos-v3-time{font-size:18px;color:#111;font-weight:1000;letter-spacing:-.3px}.pos-v3-user{width:36px;height:36px;border-radius:50%;background:var(--pos-dark);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:12px}
.title{padding:15px 18px 8px!important;margin:0!important}.title h2{margin:0!important;font-size:22px!important;letter-spacing:-.4px!important}.title #count{font-size:11px!important;color:#848b95!important;font-weight:900!important}

/* Categories horizontales */
.cats{grid-column:auto!important;grid-row:auto!important;background:transparent!important;border:0!important;padding:4px 18px 10px!important;overflow-x:auto!important;overflow-y:hidden!important;display:flex!important;gap:7px!important;white-space:nowrap!important;box-shadow:none!important;scrollbar-width:thin}
.cats:before{display:none!important}.cats .pos-settings-link{display:none!important}.cat{width:auto!important;min-width:max-content!important;padding:10px 14px!important;margin:0!important;border:1px solid #dce0e5!important;border-radius:999px!important;background:#fff!important;color:#31363d!important;text-align:center!important;font-size:12px!important;font-weight:900!important;box-shadow:none!important}.cat:hover{border-color:#c8a34b!important;background:#fffaf0!important}.cat.active{background:var(--pos-dark)!important;color:#fff!important;border-color:var(--pos-dark)!important;box-shadow:none!important}
.grid{padding:0 18px 22px!important;display:grid!important;grid-template-columns:repeat(auto-fill,minmax(180px,1fr))!important;gap:12px!important}
.product{background:#fff!important;border:1px solid #e0e3e7!important;border-radius:14px!important;padding:9px!important;min-height:210px!important;box-shadow:0 2px 7px rgba(16,20,24,.04)!important;transition:.12s ease!important;overflow:hidden!important}.product:hover{transform:translateY(-2px)!important;border-color:#d2b05b!important;box-shadow:0 8px 22px rgba(16,20,24,.10)!important}.product-photo{height:132px!important;border-radius:10px!important;margin-bottom:9px!important;object-fit:cover!important}.name{font-size:15px!important;line-height:1.18!important;font-weight:900!important}.meta{font-size:9px!important;letter-spacing:.5px!important;color:#8a919a!important;text-transform:uppercase!important;margin-top:4px!important}.badge{font-size:9px!important;background:#fff4d4!important;color:#76570d!important;font-weight:900!important;margin-top:6px!important}.price{font-size:20px!important;color:#111!important;font-weight:1000!important;padding-top:8px!important}

/* Ticket droite */
.cart{grid-column:3!important;grid-row:1!important;background:#fff!important;border-left:1px solid var(--pos-line)!important;padding:0!important;overflow:auto!important;box-shadow:-4px 0 18px rgba(15,18,22,.04)!important;position:relative!important}
.cart:before{content:'COMMANDE';display:block;padding:15px 16px 8px;font-size:10px;font-weight:1000;letter-spacing:1.25px;color:#8a919b}
.cart>h2#side-title{display:none!important}.cart>.ticket-choice{display:none!important}
.pos-recent-orders-btn{margin:0 14px 8px!important;width:calc(100% - 28px)!important;min-height:40px!important;border:1px solid #dce0e5!important;border-radius:10px!important;background:#fff!important;font-size:12px!important;font-weight:900!important}.pos-recent-orders-btn:hover{background:#f8f9fa!important}
.touch-client-summary{margin:0 14px 8px!important;border-radius:10px!important;background:#f7f8fa!important;border-color:#e1e4e8!important;min-height:48px!important}.touch-client-summary .tc-edit{background:var(--pos-dark)!important}
.order-box{border:0!important;margin:0!important;padding:6px 16px 12px!important}.order-box>h2{font-size:18px!important;margin:0 0 8px!important}.order-line{padding:9px 0!important}.order-line-head{font-size:13px!important}.order-opts{font-size:10px!important}.order-total{font-size:25px!important;border-top:2px solid #161a1f!important;padding-top:12px!important;margin-top:8px!important}.remove{font-size:11px!important;font-weight:900!important;color:var(--pos-red)!important}
#options{margin:0 14px 12px!important;border:1px solid #e3e6ea!important;border-radius:12px!important;padding:10px!important;background:#f8f9fa!important}.selection-summary{background:#fff!important}.opt-value.selected{background:var(--pos-dark)!important;color:#fff!important;border-color:var(--pos-dark)!important}.action.add{background:var(--pos-dark)!important;color:#fff!important}.action.save{background:var(--pos-orange)!important;color:#fff!important;min-height:52px!important;font-size:14px!important;border-radius:11px!important;text-transform:uppercase!important;letter-spacing:.25px!important}.action.kitchen{background:var(--pos-orange)!important;color:#fff!important;min-height:52px!important;font-size:14px!important;border-radius:11px!important;text-transform:uppercase!important}.note{display:none!important}

/* Upsell unique */
.pos-v2-upsell{margin:0 14px 12px!important;border:1px solid #ead9a8!important;border-radius:12px!important;background:#fffaf0!important;padding:10px!important}.pos-v2-upsell.hidden{display:none!important}.pos-v2-upsell-head{display:flex;align-items:center;gap:7px;margin-bottom:7px}.pos-v2-upsell-head b{font-size:12px;flex:1}.pos-v2-upsell-head small{font-size:9px;color:#8a6b1a;font-weight:900;text-transform:uppercase}.pos-v2-upsell-list{display:grid;gap:6px}.pos-v2-upsell-item{display:flex;align-items:center;gap:8px;width:100%;border:1px solid #ebdfbd;background:#fff;border-radius:9px;padding:7px;text-align:left;cursor:pointer}.pos-v2-upsell-photo{width:38px;height:38px;border-radius:7px;object-fit:cover;background:#eee;flex:0 0 auto}.pos-v2-upsell-copy{min-width:0;flex:1}.pos-v2-upsell-name{display:block;font-size:11px;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pos-v2-upsell-price{display:block;font-size:10px;color:#80641c;font-weight:900;margin-top:2px}.pos-v2-upsell-add{width:26px;height:26px;border-radius:50%;background:var(--pos-gold);display:flex;align-items:center;justify-content:center;font-size:17px;font-weight:1000;color:#111;flex:0 0 auto}

/* Masque le vieux selecteur service injecte dans la colonne droite : la barre haute devient la reference */
#phase36-table-selector{display:none!important}

/* Mobile : comportement historique conservé */
@media(max-width:980px){
  body{overflow:auto!important}
  .layout{grid-template-columns:72px 1fr!important;height:auto!important}
  .cart{grid-column:2!important;grid-row:2!important;display:block!important;border-left:0!important;border-top:1px solid var(--pos-line)!important}
  .pos-v3-toolbar{grid-template-columns:1fr!important}
  .pos-v3-clock{display:none!important}
  .grid{grid-template-columns:repeat(auto-fill,minmax(150px,1fr))!important}
}

/* Profil unique Samsung tablette 11" — activé par JavaScript uniquement sur écran tactile large */
html.bechefaa-tablet body{overflow:hidden!important}
html.bechefaa-tablet .top{
  height:58px!important;min-height:58px!important;
  padding:0 14px 0 110px!important
}
html.bechefaa-tablet .top>b{font-size:18px!important}
html.bechefaa-tablet .top .status{font-size:11px!important}
html.bechefaa-tablet .layout{
  display:grid!important;
  grid-template-columns:104px minmax(0,1fr) 285px!important;
  height:calc(100vh - 58px)!important;
  min-height:0!important
}
html.bechefaa-tablet .pos-v3-rail{
  grid-column:1!important;grid-row:1!important;
  min-width:104px!important;
  padding:10px 8px!important;gap:8px!important
}
html.bechefaa-tablet .pos-v3-brand{
  width:56px!important;height:56px!important;
  border-radius:15px!important;font-size:21px!important;margin-bottom:4px!important
}
html.bechefaa-tablet .pos-v3-nav{
  min-height:70px!important;
  font-size:16px!important;
  border-radius:13px!important;
  padding:8px 5px!important;
  line-height:1.15!important
}
html.bechefaa-tablet .pos-v3-nav span{font-size:27px!important}
html.bechefaa-tablet .main{
  grid-column:2!important;grid-row:1!important;
  min-width:0!important;
  overflow-y:auto!important;overflow-x:hidden!important
}
html.bechefaa-tablet .cart{
  grid-column:3!important;grid-row:1!important;
  display:block!important;
  height:calc(100vh - 58px)!important;
  border-left:1px solid var(--pos-line)!important;
  border-top:0!important;
  overflow:auto!important
}
html.bechefaa-tablet .pos-v3-toolbar{
  padding:9px 11px!important;
  grid-template-columns:520px minmax(220px,1fr)!important;
  gap:12px!important
}
html.bechefaa-tablet .pos-v3-service{
  width:520px!important;
  justify-content:center!important
}
html.bechefaa-tablet .pos-v3-service .ticket-choice{
  width:100%!important;
  display:flex!important;
  justify-content:center!important;
  gap:12px!important
}
html.bechefaa-tablet .pos-v3-service .ticket-choice button{
  flex:1 1 0!important;
  min-width:0!important;
  min-height:68px!important;
  padding:8px 12px!important;
  font-size:17px!important;
  display:flex!important;
  flex-direction:column!important;
  align-items:center!important;
  justify-content:center!important;
  gap:4px!important;
  text-align:center!important
}
html.bechefaa-tablet .pos-v3-service .ticket-choice button::before{
  display:block!important;
  font-size:28px!important;
  line-height:1!important
}
html.bechefaa-tablet .pos-v3-service .ticket-choice button[data-ticket="Salle"]::before{content:"🍽"!important}
html.bechefaa-tablet .pos-v3-service .ticket-choice button[data-ticket="Emporter"]::before{content:"🥡"!important}
html.bechefaa-tablet .pos-v3-service .ticket-choice button[data-ticket="Livraison"]::before{content:"🛵"!important}
html.bechefaa-tablet .pos-v3-search{
  height:42px!important;font-size:14px!important;padding:0 12px!important
}
html.bechefaa-tablet .pos-v3-clock{display:none!important}
html.bechefaa-tablet .title{padding:10px 12px 6px!important}
html.bechefaa-tablet .title h2{font-size:19px!important}
html.bechefaa-tablet .cats{
  padding:4px 12px 9px!important;
  gap:7px!important
}
html.bechefaa-tablet .cat{
  padding:12px 16px!important;
  font-size:18px!important;
  line-height:1.1!important
}
html.bechefaa-tablet .grid{
  padding:0 10px 18px!important;
  grid-template-columns:repeat(4,190px)!important;
  gap:30px!important;
  justify-content:center!important;
  min-width:0!important;width:100%!important
}
html.bechefaa-tablet .product{
  min-height:160px!important;
  width:190px!important;
  max-width:190px!important;
  justify-self:start!important;
  padding:7px!important;
  border-radius:11px!important;
  min-width:0!important;
  overflow:hidden!important
}
html.bechefaa-tablet .product-photo{
  height:110px!important;
  width:160px!important;
  max-width:160px!important;
  object-fit:cover!important;
  margin:0 auto 6px!important;
  border-radius:8px!important;
  display:block!important
}
html.bechefaa-tablet .name{
  font-size:16px!important;
  line-height:1.16!important;
  text-align:center!important;
  white-space:normal!important;
  overflow-wrap:anywhere!important;
  display:-webkit-box!important;
  -webkit-box-orient:vertical!important;
  -webkit-line-clamp:2!important;
  overflow:hidden!important
}
html.bechefaa-tablet .meta{display:none!important}
html.bechefaa-tablet .badge{display:none!important}
html.bechefaa-tablet .price{font-size:18px!important;padding-top:5px!important;text-align:center!important;width:100%!important}
html.bechefaa-tablet .cart:before{padding:10px 11px 5px!important}
html.bechefaa-tablet .pos-recent-orders-btn{
  margin:0 10px 7px!important;
  width:calc(100% - 20px)!important;
  min-height:42px!important;
  font-size:13px!important
}
html.bechefaa-tablet .touch-client-summary{
  margin:0 10px 7px!important;
  min-height:46px!important;
  padding:8px 9px!important
}
html.bechefaa-tablet #options{margin:0 10px 8px!important;padding:8px!important}
html.bechefaa-tablet .order-box{padding:4px 11px 9px!important}
html.bechefaa-tablet .order-box>h2{font-size:17px!important;margin-bottom:6px!important}
html.bechefaa-tablet .order-line{padding:7px 0!important}
html.bechefaa-tablet .order-line-head{font-size:13px!important}
html.bechefaa-tablet .order-total{font-size:22px!important;padding-top:8px!important}
html.bechefaa-tablet .action.save,
html.bechefaa-tablet .action.kitchen{
  min-height:46px!important;
  font-size:13px!important
}
html.bechefaa-tablet .pos-v2-upsell{margin:0 10px 8px!important;padding:8px!important}

</style>
<script id="pos-design-v2-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   const layout=document.querySelector('.layout'),main=document.querySelector('.main'),cats=document.getElementById('cats'),cart=document.querySelector('.cart'),ticket=document.querySelector('.ticket-choice');
   if(!layout||!main||!cats||!cart||!ticket)return;

   function applyTabletProfile(){
     const w=window.innerWidth,h=window.innerHeight;
     const touch=(navigator.maxTouchPoints||0)>0;
     const tablet=touch&&w>=1000&&w<=1700&&h<=1100;
     document.documentElement.classList.toggle('bechefaa-tablet',tablet);
     if(tablet){
       main.scrollLeft=0;
       const grid=document.getElementById('grid');
       if(grid)grid.scrollLeft=0;
     }
   }
   applyTabletProfile();
   window.addEventListener('resize',applyTabletProfile);
   window.addEventListener('pageshow',applyTabletProfile);
   document.addEventListener('visibilitychange',function(){if(!document.hidden)applyTabletProfile();});

   // Rail gauche
   if(!document.querySelector('.pos-v3-rail')){
     const rail=document.createElement('aside');rail.className='pos-v3-rail';
     rail.innerHTML='<div class="pos-v3-brand">B</div><a class="pos-v3-nav active" href="/pos"><span>▦</span>Caisse</a><a class="pos-v3-nav" href="/cuisine"><span>♨</span>Cuisine</a><a class="pos-v3-nav" href="/historique"><span>≡</span>Historique</a><div class="pos-v3-rail-spacer"></div><a class="pos-v3-nav" href="/administration"><span>⚙</span>Réglages</a>';
     layout.insertBefore(rail,layout.firstChild);
   }

   // Barre service + recherche + heure
   let toolbar=document.querySelector('.pos-v3-toolbar');
   if(!toolbar){
     toolbar=document.createElement('div');toolbar.className='pos-v3-toolbar';
     toolbar.innerHTML='<div class="pos-v3-service"></div><input class="pos-v3-search" type="search" placeholder="Rechercher un produit…"><div class="pos-v3-clock"><div><div class="pos-v3-time">--:--</div><div>Administrateur</div></div><div class="pos-v3-user">AD</div></div>';
     main.insertBefore(toolbar,main.firstChild);
     toolbar.querySelector('.pos-v3-service').appendChild(ticket);
   }

   // Categories sous le titre, au centre
   const title=main.querySelector('.title');
   if(title && cats.parentNode!==main){title.insertAdjacentElement('afterend',cats)}
   else if(title && cats.previousElementSibling!==title){title.insertAdjacentElement('afterend',cats)}

   // Ticket avant les options
   const orderBox=cart.querySelector('.order-box'),options=document.getElementById('options');
   if(orderBox&&options&&orderBox.nextElementSibling!==options){cart.insertBefore(orderBox,options)}

   // Horloge
   const timeEl=toolbar.querySelector('.pos-v3-time');
   function tick(){const d=new Date();timeEl.textContent=d.toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})}tick();setInterval(tick,30000);

   // Recherche visuelle, sans toucher au moteur catalogue
   const search=toolbar.querySelector('.pos-v3-search'),grid=document.getElementById('grid');
   function applySearch(){const q=String(search.value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();grid.querySelectorAll('.product').forEach(p=>{const n=String(p.dataset.name||p.textContent||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();p.style.display=!q||n.includes(q)?'flex':'none'})}
   search.addEventListener('input',applySearch);new MutationObserver(()=>setTimeout(applySearch,0)).observe(grid,{childList:true});

   // Upsell compact
   const orderEl=document.getElementById('order');
   if(orderEl&&!document.querySelector('.pos-v2-upsell')){
     const upsell=document.createElement('section');upsell.className='pos-v2-upsell hidden';upsell.innerHTML='<div class="pos-v2-upsell-head"><span>＋</span><b>Ajouter à la commande</b><small>Suggestion</small></div><div class="pos-v2-upsell-list"></div>';orderEl.insertAdjacentElement('afterend',upsell);
     const list=upsell.querySelector('.pos-v2-upsell-list');
     const norm=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();const euro=v=>Number(v||0).toFixed(2).replace('.',',')+' €';const esc2=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
     function suggestions(){try{if(!DATA||!Array.isArray(DATA.items)||!ORDER||!ORDER.length)return[];const inCart=new Set(ORDER.map(l=>String(l.product_id||'')));const byId=new Map(DATA.items.map(p=>[String(p.id),norm(p.category)]));const cats=ORDER.map(l=>byId.get(String(l.product_id))||'');let targets=cats.some(c=>['burger','sandwich','assiette','nos formules midi','carte du soir'].includes(c))?['boissons','accompagnement','desserts']:['boissons','desserts','accompagnement'];const out=[];for(const target of targets){const p=DATA.items.find(x=>!inCart.has(String(x.id||''))&&norm(x.category)===target&&!out.some(y=>String(y.id)===String(x.id)));if(p)out.push(p);if(out.length===3)break}return out}catch(e){return[]}}
     function draw(){const s=suggestions();upsell.classList.toggle('hidden',!s.length);list.innerHTML=s.map(p=>'<button type="button" class="pos-v2-upsell-item" data-upsell-id="'+esc2(p.id)+'" data-upsell-name="'+esc2(p.name)+'">'+(p.photo?'<img class="pos-v2-upsell-photo" src="'+esc2(p.photo)+'" alt="">':'<span class="pos-v2-upsell-photo"></span>')+'<span class="pos-v2-upsell-copy"><span class="pos-v2-upsell-name">'+esc2(p.name)+'</span><span class="pos-v2-upsell-price">'+euro(p.price)+'</span></span><span class="pos-v2-upsell-add">+</span></button>').join('')}
     list.addEventListener('click',e=>{const b=e.target.closest('[data-upsell-id]');if(!b)return;if(typeof showOptions==='function')showOptions(b.dataset.upsellId,b.dataset.upsellName)});new MutationObserver(()=>setTimeout(draw,0)).observe(orderEl,{childList:true,subtree:true});setTimeout(draw,200);
   }
 })
})();
</script>
'''

    def pos_v2_view(*args, **kwargs):
        response = app.make_response(original(*args, **kwargs))
        try:
            if response.status_code == 200 and response.mimetype == "text/html":
                html = response.get_data(as_text=True)
                if "pos-design-v2-style" not in html:
                    html = html.replace("</body>", addon + "</body>")
                    response.set_data(html)
                    response.content_length = len(response.get_data())
                response.headers["X-Bechefaa-POS-Design"] = "v6-tablet-single-profile"
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                response.headers["Pragma"] = "no-cache"
        except Exception:
            pass
        return response

    app.view_functions["pos"] = pos_v2_view
    app._bechefaa_pos_v2_wrapped = True
