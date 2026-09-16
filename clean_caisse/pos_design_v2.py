"""Design V2 direct pour la caisse BÉCHÉFAA.

Le rendu V2 est appliqué directement à la vue Flask /pos, avant les couches
after_request. Aucun changement de logique métier, PostgreSQL, paiement ou cuisine.
"""


def register_pos_design_v2(app):
    if getattr(app, "_bechefaa_pos_v2_wrapped", False):
        return

    original = app.view_functions.get("pos")
    if original is None:
        return

    addon = r'''
<style id="pos-design-v2-style">
:root{--v2-ink:#0d1014;--v2-panel:#171b20;--v2-panel2:#22272e;--v2-gold:#d6a52e;--v2-gold2:#f1c44f;--v2-line:#e1e4e8;--v2-muted:#79818c;--v2-bg:#f1f2f4}
body{background:var(--v2-bg)!important;color:#17191c!important}
.top{background:var(--v2-ink)!important;min-height:72px!important;padding:10px 20px!important;box-shadow:0 3px 18px rgba(0,0,0,.2)!important}
.top>b{font-size:23px!important;letter-spacing:.2px!important;color:#fff!important}.top>b:after{content:'  •  POS V2';color:var(--v2-gold2);font-size:11px;letter-spacing:1.3px;vertical-align:middle}
.navlink{background:#242a31!important;border:1px solid #333a44!important;border-radius:10px!important;padding:10px 14px!important}.navlink.active{background:var(--v2-gold)!important;color:#111!important;border-color:var(--v2-gold)!important}
.status{color:#c9ced5!important;font-weight:800!important}
.layout{grid-template-columns:220px minmax(0,1fr) 410px!important;height:calc(100vh - 72px)!important}
.cats{background:var(--v2-panel)!important;border-right:0!important;padding:15px 12px!important;box-shadow:4px 0 18px rgba(0,0,0,.07)!important}
.cats:before{content:'CATÉGORIES';display:block;color:#89919c;font-size:10px;font-weight:900;letter-spacing:1.4px;padding:4px 10px 10px}
.cat{width:100%!important;padding:13px 11px!important;margin:3px 0!important;border:1px solid transparent!important;border-radius:10px!important;background:transparent!important;color:#e1e5ea!important;text-align:left!important;font-weight:800!important;cursor:pointer!important;transition:.15s ease!important}
.cat:hover{background:#242a31!important;border-color:#333a44!important}.cat.active{background:var(--v2-gold)!important;color:#111!important;border-color:var(--v2-gold)!important;box-shadow:0 5px 18px rgba(214,165,46,.2)!important}
.pos-settings-link{background:#242a31!important;border:1px solid #333a44!important;color:#fff!important;box-shadow:none!important}.pos-settings-link:hover{background:#2c333c!important}
.main{padding:22px 24px!important;background:var(--v2-bg)!important}.title{margin-bottom:16px!important}.title h2{margin:0!important;font-size:25px!important;letter-spacing:-.3px!important}.title #count{font-size:12px!important;color:var(--v2-muted)!important;font-weight:900!important}
.grid{grid-template-columns:repeat(auto-fill,minmax(178px,1fr))!important;gap:14px!important}
.product{background:#fff!important;border:1px solid #e0e3e7!important;border-radius:15px!important;padding:11px!important;min-height:188px!important;box-shadow:0 2px 8px rgba(15,17,21,.05)!important;transition:transform .12s ease,box-shadow .12s ease,border-color .12s ease!important;overflow:hidden!important}
.product:hover{transform:translateY(-2px)!important;border-color:#d3ad4d!important;box-shadow:0 8px 24px rgba(15,17,21,.11)!important}.product-photo{height:128px!important;border-radius:10px!important;margin-bottom:10px!important}.name{font-size:15px!important;line-height:1.25!important}.meta{font-size:10px!important;text-transform:uppercase!important;letter-spacing:.55px!important;color:#8b919b!important;margin-top:5px!important}.badge{background:#fff7df!important;color:#755713!important;font-weight:900!important}.price{font-size:20px!important;color:#111!important;padding-top:9px!important}
.cart{background:#fff!important;border-left:1px solid var(--v2-line)!important;padding:17px!important;box-shadow:-5px 0 20px rgba(15,17,21,.05)!important}.cart:before{content:'COMMANDE EN COURS';display:block;font-size:10px;font-weight:900;letter-spacing:1.3px;color:#8b919a;margin:2px 0 9px}.cart h2{letter-spacing:-.2px!important}.ticket-choice{background:#fff!important;padding:2px 0 10px!important}.ticket-choice button{border:1px solid #d8dce2!important;border-radius:10px!important;background:#f7f8fa!important;color:#343943!important;font-weight:900!important}.ticket-choice button.active{background:var(--v2-ink)!important;color:#fff!important;border-color:var(--v2-ink)!important;box-shadow:0 4px 12px rgba(15,17,21,.15)!important}
.pos-recent-orders-btn{border-color:#d9dde3!important;background:#fff!important}.pos-recent-orders-btn:hover{border-color:#c8a23f!important;background:#fffbef!important}.touch-client-summary{border-color:#e0e3e7!important;background:#f8f9fa!important}.touch-client-summary .tc-edit{background:var(--v2-panel)!important}
#options{border:1px solid #e4e7eb!important;border-radius:13px!important;padding:11px!important;background:#fafbfc!important}.selection-summary{background:#fff!important}.opt-value.selected{background:var(--v2-panel)!important;border-color:var(--v2-panel)!important}.action.add{background:var(--v2-panel)!important}.action.save{background:#17784c!important;min-height:50px!important;font-size:14px!important}.action.kitchen{background:#c67d10!important;min-height:50px!important;font-size:14px!important}
.order-box{border-top:1px solid #dfe3e8!important;margin-top:15px!important;padding-top:15px!important}.order-box>h2{font-size:20px!important}.order-line{padding:10px 0!important}.order-line-head{font-size:14px!important}.order-total{font-size:23px!important;border-top:1px solid #e5e7eb!important;padding-top:12px!important;margin-top:8px!important}.remove{font-weight:900!important}
.pos-v2-upsell{margin:14px 0 4px;border:1px solid #e6d49d;border-radius:13px;background:linear-gradient(180deg,#fffdf7,#fff9ea);padding:12px}.pos-v2-upsell.hidden{display:none!important}.pos-v2-upsell-head{display:flex;align-items:center;gap:8px;margin-bottom:9px}.pos-v2-upsell-head b{font-size:13px;flex:1}.pos-v2-upsell-head small{font-size:9px;color:#8a7240;font-weight:900;text-transform:uppercase;letter-spacing:.5px}.pos-v2-upsell-list{display:grid;gap:7px}.pos-v2-upsell-item{display:flex;align-items:center;gap:9px;width:100%;border:1px solid #eadfbf;background:#fff;border-radius:10px;padding:8px;text-align:left;cursor:pointer}.pos-v2-upsell-item:hover{border-color:#cfa63c;background:#fffdf7}.pos-v2-upsell-photo{width:43px;height:43px;border-radius:8px;object-fit:cover;background:#f2f2f2;flex:0 0 auto}.pos-v2-upsell-copy{min-width:0;flex:1}.pos-v2-upsell-name{display:block;font-size:12px;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pos-v2-upsell-price{display:block;font-size:11px;color:#79601f;font-weight:900;margin-top:2px}.pos-v2-upsell-add{width:28px;height:28px;border-radius:50%;background:var(--v2-gold);color:#111;display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:900;flex:0 0 auto}.note{display:none!important}
@media(max-width:1180px){.layout{grid-template-columns:180px minmax(0,1fr) 365px!important}.grid{grid-template-columns:repeat(auto-fill,minmax(158px,1fr))!important}}
@media(max-width:900px){.layout{grid-template-columns:150px 1fr!important}.cart{display:none!important}}
</style>
<script id="pos-design-v2-script">
(function(){
 function boot(){
  const orderEl=document.getElementById('order');if(!orderEl||document.querySelector('.pos-v2-upsell'))return;
  const upsell=document.createElement('section');upsell.className='pos-v2-upsell hidden';upsell.innerHTML='<div class="pos-v2-upsell-head"><span>✨</span><b>Suggestions pour cette commande</b><small>Upsell</small></div><div class="pos-v2-upsell-list"></div>';orderEl.insertAdjacentElement('afterend',upsell);
  const list=upsell.querySelector('.pos-v2-upsell-list');
  const norm=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
  const euro=v=>Number(v||0).toFixed(2).replace('.',',')+' €';
  const esc2=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function suggestions(){
   try{if(!DATA||!Array.isArray(DATA.items)||!ORDER||!ORDER.length)return[];const inCart=new Set(ORDER.map(l=>String(l.product_id||'')));const byId=new Map(DATA.items.map(p=>[String(p.id),norm(p.category)]));const cats=ORDER.map(l=>byId.get(String(l.product_id))||'');let targets=cats.some(c=>['burger','sandwich','assiette','nos formules midi','carte du soir'].includes(c))?['boissons','accompagnement','desserts']:['boissons','desserts','accompagnement'];const out=[];for(const target of targets){const p=DATA.items.find(x=>!inCart.has(String(x.id||''))&&norm(x.category)===target&&!out.some(y=>String(y.id)===String(x.id)));if(p)out.push(p);if(out.length===3)break}return out}catch(e){return[]}
  }
  function renderUpsell(){const s=suggestions();upsell.classList.toggle('hidden',!s.length);list.innerHTML=s.map(p=>'<button type="button" class="pos-v2-upsell-item" data-upsell-id="'+esc2(p.id)+'" data-upsell-name="'+esc2(p.name)+'">'+(p.photo?'<img class="pos-v2-upsell-photo" src="'+esc2(p.photo)+'" alt="">':'<span class="pos-v2-upsell-photo"></span>')+'<span class="pos-v2-upsell-copy"><span class="pos-v2-upsell-name">'+esc2(p.name)+'</span><span class="pos-v2-upsell-price">'+euro(p.price)+'</span></span><span class="pos-v2-upsell-add">+</span></button>').join('')}
  list.addEventListener('click',e=>{const b=e.target.closest('[data-upsell-id]');if(!b)return;if(typeof showOptions==='function')showOptions(b.dataset.upsellId,b.dataset.upsellName)});
  new MutationObserver(()=>setTimeout(renderUpsell,0)).observe(orderEl,{childList:true,subtree:true});setTimeout(renderUpsell,200);
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
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
                response.headers["X-Bechefaa-POS-Design"] = "v2-direct"
        except Exception:
            pass
        return response

    app.view_functions["pos"] = pos_v2_view
    app._bechefaa_pos_v2_wrapped = True
