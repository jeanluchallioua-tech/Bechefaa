"""Design V2 isolé pour la caisse BÉCHÉFAA.

Couche d'affichage uniquement :
- thème professionnel anthracite / or ;
- hiérarchie visuelle catalogue / panier améliorée ;
- bloc upsell de 3 suggestions maximum, basé sur le catalogue déjà chargé ;
- les suggestions réutilisent showOptions(), ORDER et DATA existants.

Aucune écriture PostgreSQL, aucun changement de paiement, cuisine ou tickets.
"""
from flask import request


def register_pos_design_v2(app):
    @app.after_request
    def inject_pos_design_v2(response):
        if request.path != "/pos" or response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        if "pos-design-v2-style" in html:
            return response

        addon = r'''
<style id="pos-design-v2-style">
:root{--v2-ink:#0f1115;--v2-panel:#171a1f;--v2-panel2:#20242b;--v2-gold:#d9a62e;--v2-gold2:#f0bd45;--v2-line:#e3e6ea;--v2-muted:#747b86;--v2-bg:#f1f2f4}
body{background:var(--v2-bg)!important;color:#17191c!important}
.top{background:var(--v2-ink)!important;min-height:70px!important;padding:10px 20px!important;box-shadow:0 3px 18px rgba(0,0,0,.18)!important}
.top>b{font-size:23px!important;letter-spacing:.2px;color:#fff!important}.top>b:after{content:'  •  POS';color:var(--v2-gold2);font-size:12px;letter-spacing:1.2px;vertical-align:middle}
.navlink{background:#242830!important;border:1px solid #303641!important;border-radius:9px!important;padding:10px 13px!important}.navlink.active{background:var(--v2-gold)!important;color:#111!important;border-color:var(--v2-gold)!important}
.status{color:#c9ced6!important;font-weight:700!important}
.layout{grid-template-columns:210px minmax(0,1fr) 400px!important;height:calc(100vh - 70px)!important;gap:0!important}
.cats{background:var(--v2-panel)!important;border-right:0!important;padding:14px 12px!important}
.cats:before{content:'CATÉGORIES';display:block;color:#8f97a3;font-size:10px;font-weight:900;letter-spacing:1.35px;padding:4px 10px 8px}
.cat{background:transparent!important;color:#dce0e6!important;border:1px solid transparent!important;border-radius:9px!important;padding:12px 11px!important;margin:3px 0!important;font-size:13px!important;transition:.15s ease!important}
.cat:hover{background:#242830!important;border-color:#303641!important}.cat.active{background:var(--v2-gold)!important;color:#111!important;border-color:var(--v2-gold)!important;box-shadow:0 5px 18px rgba(217,166,46,.16)!important}
.pos-settings-link{background:#242830!important;border:1px solid #303641!important;color:#fff!important;box-shadow:none!important}.pos-settings-link:hover{background:#2c313a!important}
.main{padding:20px 22px!important;background:var(--v2-bg)!important}.title{margin-bottom:16px!important}.title h2{margin:0!important;font-size:24px!important;letter-spacing:-.25px}.title #count{color:var(--v2-muted)!important;font-size:12px!important;font-weight:800!important}
.grid{grid-template-columns:repeat(auto-fill,minmax(176px,1fr))!important;gap:14px!important}
.product{border:1px solid #e1e4e8!important;border-radius:14px!important;padding:11px!important;min-height:178px!important;box-shadow:0 2px 7px rgba(15,17,21,.04)!important;transition:transform .12s ease,box-shadow .12s ease,border-color .12s ease!important;overflow:hidden!important}
.product:hover{transform:translateY(-2px)!important;border-color:#d7b155!important;box-shadow:0 8px 22px rgba(15,17,21,.10)!important}.product-photo{height:126px!important;border-radius:10px!important;margin-bottom:10px!important}.name{font-size:15px!important;line-height:1.25!important}.meta{font-size:10px!important;text-transform:uppercase!important;letter-spacing:.55px!important;color:#8b919b!important;margin-top:5px!important}.badge{background:#fff7df!important;color:#795810!important;font-weight:800!important}.price{font-size:19px!important;color:#111!important;padding-top:8px!important}
.cart{background:#fff!important;border-left:1px solid var(--v2-line)!important;padding:16px!important;box-shadow:-4px 0 18px rgba(15,17,21,.04)!important}.cart:before{content:'COMMANDE EN COURS';display:block;font-size:10px;font-weight:900;letter-spacing:1.25px;color:#8a9099;margin:2px 0 8px}.cart h2{letter-spacing:-.2px!important}.ticket-choice{background:#fff!important;padding:2px 0 10px!important}.ticket-choice button{border:1px solid #d9dde3!important;border-radius:10px!important;background:#f7f8fa!important;color:#343943!important;font-weight:900!important}.ticket-choice button.active{background:var(--v2-ink)!important;color:#fff!important;border-color:var(--v2-ink)!important;box-shadow:0 4px 12px rgba(15,17,21,.14)!important}
.pos-recent-orders-btn{border-color:#d9dde3!important;background:#fff!important}.pos-recent-orders-btn:hover{border-color:#c6a13d!important;background:#fffbef!important}.touch-client-summary{border-color:#e0e3e7!important;background:#f8f9fa!important}.touch-client-summary .tc-edit{background:var(--v2-panel)!important}
#options{border:1px solid #e5e7eb;border-radius:12px;padding:11px;background:#fafbfc}.selection-summary{background:#fff!important}.opt-value.selected{background:var(--v2-panel)!important;border-color:var(--v2-panel)!important}.action.add{background:var(--v2-panel)!important}.action.save{background:#17784c!important;min-height:48px!important;font-size:14px!important}.action.kitchen{background:#c97f12!important;min-height:48px!important;font-size:14px!important}
.order-box{border-top:1px solid #dfe3e8!important;margin-top:14px!important;padding-top:14px!important}.order-box>h2{font-size:20px!important}.order-line{padding:10px 0!important}.order-line-head{font-size:14px!important}.order-total{font-size:22px!important;border-top:1px solid #e5e7eb!important;padding-top:12px!important;margin-top:8px!important}.remove{font-weight:800!important}
.pos-v2-upsell{margin:14px 0 4px;border:1px solid #e5d39b;border-radius:13px;background:linear-gradient(180deg,#fffdf6,#fffaf0);padding:12px}.pos-v2-upsell.hidden{display:none}.pos-v2-upsell-head{display:flex;align-items:center;gap:8px;margin-bottom:9px}.pos-v2-upsell-head span:first-child{font-size:18px}.pos-v2-upsell-head b{font-size:13px;flex:1}.pos-v2-upsell-head small{font-size:10px;color:#8a7240;font-weight:800;text-transform:uppercase;letter-spacing:.4px}.pos-v2-upsell-list{display:grid;gap:7px}.pos-v2-upsell-item{display:flex;align-items:center;gap:9px;width:100%;border:1px solid #eadfbf;background:#fff;border-radius:10px;padding:8px;text-align:left;cursor:pointer}.pos-v2-upsell-item:hover{border-color:#cfa63c;background:#fffdf7}.pos-v2-upsell-photo{width:43px;height:43px;border-radius:8px;object-fit:cover;background:#f2f2f2;flex:0 0 auto}.pos-v2-upsell-copy{min-width:0;flex:1}.pos-v2-upsell-name{font-size:12px;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pos-v2-upsell-price{font-size:11px;color:#79601f;font-weight:800;margin-top:2px}.pos-v2-upsell-add{width:28px;height:28px;border-radius:50%;background:var(--v2-gold);color:#111;display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:900;flex:0 0 auto}
.note{display:none!important}
@media(max-width:1180px){.layout{grid-template-columns:175px minmax(0,1fr) 360px!important}.grid{grid-template-columns:repeat(auto-fill,minmax(158px,1fr))!important}}
@media(max-width:900px){.layout{grid-template-columns:150px 1fr!important}.cart{display:none!important}}
</style>
<script id="pos-design-v2-script">
(function(){
  function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
  ready(function(){
    const orderEl=document.getElementById('order');
    const orderBox=document.querySelector('.order-box');
    if(!orderEl||!orderBox)return;

    const upsell=document.createElement('section');
    upsell.className='pos-v2-upsell hidden';
    upsell.innerHTML='<div class="pos-v2-upsell-head"><span>✨</span><b>Suggestions pour cette commande</b><small>Upsell</small></div><div class="pos-v2-upsell-list"></div>';
    orderEl.insertAdjacentElement('afterend',upsell);
    const list=upsell.querySelector('.pos-v2-upsell-list');

    const norm=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
    const euro=v=>Number(v||0).toFixed(2).replace('.',',')+' €';
    const esc2=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

    function targetCategories(){
      let cats=[];
      try{
        const byId=new Map((DATA&&DATA.items||[]).map(p=>[String(p.id),norm(p.category)]));
        cats=(ORDER||[]).map(l=>byId.get(String(l.product_id))||'');
      }catch(e){}
      const main=cats.some(c=>['burger','sandwich','assiette','nos formules midi','carte du soir'].includes(c));
      if(main)return ['boissons','accompagnement','desserts'];
      if(cats.includes('accompagnement'))return ['boissons','desserts'];
      if(cats.includes('boissons'))return ['desserts','accompagnement'];
      return ['boissons','accompagnement','desserts'];
    }

    function chooseSuggestions(){
      if(typeof DATA==='undefined'||!DATA||!Array.isArray(DATA.items)||typeof ORDER==='undefined'||!ORDER.length)return [];
      const inCart=new Set(ORDER.map(l=>String(l.product_id||'')));
      const targets=targetCategories();
      const out=[];
      for(const target of targets){
        const found=DATA.items.find(p=>!inCart.has(String(p.id||''))&&norm(p.category)===target&&!out.some(x=>String(x.id)===String(p.id)));
        if(found)out.push(found);
        if(out.length>=3)break;
      }
      return out;
    }

    function renderUpsell(){
      const suggestions=chooseSuggestions();
      upsell.classList.toggle('hidden',!suggestions.length);
      if(!suggestions.length){list.innerHTML='';return}
      list.innerHTML=suggestions.map(p=>'<button type="button" class="pos-v2-upsell-item" data-upsell-id="'+esc2(p.id)+'" data-upsell-name="'+esc2(p.name)+'">'+(p.photo?'<img class="pos-v2-upsell-photo" src="'+esc2(p.photo)+'" alt="">':'<div class="pos-v2-upsell-photo"></div>')+'<span class="pos-v2-upsell-copy"><span class="pos-v2-upsell-name">'+esc2(p.name)+'</span><span class="pos-v2-upsell-price">'+euro(p.price)+'</span></span><span class="pos-v2-upsell-add">+</span></button>').join('');
    }

    list.addEventListener('click',function(e){
      const b=e.target.closest('[data-upsell-id]');if(!b)return;
      if(typeof showOptions==='function'){
        showOptions(b.dataset.upsellId,b.dataset.upsellName);
        const cart=document.querySelector('.cart');if(cart)cart.scrollTo({top:0,behavior:'smooth'});
      }
    });

    new MutationObserver(()=>setTimeout(renderUpsell,0)).observe(orderEl,{childList:true,subtree:true});
    setTimeout(renderUpsell,150);
  });
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
