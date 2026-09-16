"""Finition visuelle du POS sombre.

- logo réel du site dans le rail gauche
- catégories sans ascenseur horizontal
- rail gauche toujours visible + bouton retour en haut
- upsell séquentiel Boissons puis Desserts
Aucune logique métier ni base de données modifiée.
"""


def register_pos_reference_finish(app):
    if getattr(app, "_bechefaa_pos_reference_finish", False):
        return
    original = app.view_functions.get("pos")
    if original is None:
        return

    addon = r'''
<style id="pos-reference-finish-style">
.layout{overflow:hidden!important}
.pos-v3-rail{position:sticky!important;top:0!important;height:calc(100vh - 52px)!important;align-self:start!important}
.pos-v3-brand{height:162px!important;padding:8px 0!important;overflow:visible!important}
.pos-v3-brand .pos-ref-logo{display:block!important;width:96px!important;height:96px!important;max-width:96px!important;object-fit:contain!important;margin:0 auto!important;border-radius:0!important}
.pos-v3-brand .pos-ref-brandname{font-size:20px!important;letter-spacing:3px!important;text-align:center!important;width:100%!important;overflow:visible!important}
.cats{display:flex!important;flex-wrap:wrap!important;overflow-x:hidden!important;overflow-y:visible!important;white-space:normal!important;gap:7px!important;padding:8px 14px!important}
.cat{padding:9px 13px!important;font-size:11px!important;min-width:auto!important;white-space:nowrap!important}
.pos-ref-backtop{display:none;position:fixed;right:448px;bottom:22px;z-index:9000;width:42px;height:42px;border-radius:50%;border:1px solid #745b28;background:#17130d;color:#f2c35b;font-size:22px;font-weight:900;cursor:pointer;box-shadow:0 5px 18px #0008}.pos-ref-backtop.show{display:block}
.pos-ref-upsell-overlay .pos-ref-modal{width:min(720px,96vw)!important}.pos-ref-upsell-list{grid-template-columns:repeat(2,minmax(0,1fr))!important;max-height:58vh!important;overflow:auto!important}.pos-ref-upsell-title{margin:0 0 12px!important}.pos-ref-upsell-item{min-height:72px!important}
@media(max-width:1250px){.pos-ref-backtop{right:388px}}
@media(max-width:900px){.pos-ref-backtop{right:20px}.pos-ref-upsell-list{grid-template-columns:1fr!important}}
</style>
<script id="pos-reference-finish-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   const norm=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
   const euro=v=>Number(v||0).toFixed(2).replace('.',',')+' €';
   const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

   const brand=document.querySelector('.pos-v3-brand');
   if(brand)brand.innerHTML='<img class="pos-ref-logo" src="https://raw.githubusercontent.com/jeanluchallioua-tech/Bechefaa-Site/main/logo-bechefaa.jpg" alt="BÉCHÉFAA"><div class="pos-ref-brandname">BÉCHÉFAA</div>';

   const main=document.querySelector('.main');
   if(main&&!document.querySelector('.pos-ref-backtop')){
     const up=document.createElement('button');up.type='button';up.className='pos-ref-backtop';up.setAttribute('aria-label','Retour en haut');up.textContent='↑';document.body.appendChild(up);
     function paint(){up.classList.toggle('show',main.scrollTop>260)}main.addEventListener('scroll',paint,{passive:true});paint();up.onclick=()=>main.scrollTo({top:0,behavior:'smooth'});
   }

   const overlay=document.querySelector('.pos-ref-upsell-overlay');
   if(!overlay)return;
   const list=overlay.querySelector('.pos-ref-upsell-list');
   const no=overlay.querySelector('.pos-ref-no');
   const modal=overlay.querySelector('.pos-ref-modal');
   if(!list||!no||!modal)return;
   let title=modal.querySelector('h2');if(title)title.classList.add('pos-ref-upsell-title');
   let phase='drink';
   let pendingDessert=false;

   function itemsFor(category){
     try{
       if(typeof DATA==='undefined'||!DATA||!Array.isArray(DATA.items)||typeof ORDER==='undefined')return[];
       const inCart=new Set((ORDER||[]).map(x=>String(x.product_id||'')));
       return DATA.items.filter(p=>p&&p.active!==false&&!inCart.has(String(p.id||''))&&norm(p.category)===category);
     }catch(e){return[]}
   }
   function renderPhase(){
     if(!overlay.classList.contains('open'))return;
     const cat=phase==='drink'?'boissons':'desserts';
     if(title)title.textContent=phase==='drink'?'Une boisson avec votre commande ?':'Un dessert pour terminer ?';
     no.textContent='Non merci';
     const products=itemsFor(cat);
     list.innerHTML=products.length?products.map(p=>'<button type="button" class="pos-ref-upsell-item" data-finish-upsell-id="'+esc(p.id)+'" data-finish-upsell-name="'+esc(p.name)+'">'+(p.photo?'<img src="'+esc(p.photo)+'" alt="">':'')+'<b>'+esc(p.name)+'</b><span class="pos-ref-upsell-price">'+euro(p.price)+'</span></button>').join(''):'<div style="color:#a7adb4;padding:12px">Aucun produit disponible.</div>';
   }
   function openDessert(){phase='dessert';overlay.classList.add('open');renderPhase()}
   new MutationObserver(function(){if(overlay.classList.contains('open')){phase='drink';setTimeout(renderPhase,0)}}).observe(overlay,{attributes:true,attributeFilter:['class']});

   overlay.addEventListener('click',function(e){
     const product=e.target.closest('[data-finish-upsell-id]');
     if(product){
       e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
       const chosenPhase=phase;overlay.classList.remove('open');
       if(chosenPhase==='drink')pendingDessert=true;
       if(typeof showOptions==='function')showOptions(product.dataset.finishUpsellId,product.dataset.finishUpsellName);
       return;
     }
     if(e.target.closest('.pos-ref-no')){
       e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
       if(phase==='drink'){openDessert()}else overlay.classList.remove('open');
     }
   },true);

   document.addEventListener('click',function(e){
     if(pendingDessert&&e.target.closest('[data-action="add-current"]')){
       pendingDessert=false;setTimeout(openDessert,80);
     }
   },true);
 })
})();
</script>
'''

    def pos_finish_view(*args, **kwargs):
        response = app.make_response(original(*args, **kwargs))
        try:
            if response.status_code == 200 and response.mimetype == "text/html":
                html = response.get_data(as_text=True)
                if "pos-reference-finish-style" not in html:
                    html = html.replace("</body>", addon + "</body>")
                    response.set_data(html)
                    response.content_length = len(response.get_data())
                response.headers["X-Bechefaa-POS-Finish"] = "upsell-sequential"
        except Exception:
            pass
        return response

    app.view_functions["pos"] = pos_finish_view
    app._bechefaa_pos_reference_finish = True
