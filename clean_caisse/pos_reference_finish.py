"""Finition visuelle du POS sombre.

- logo BÉCHÉFAA embarqué dans la caisse
- catégories aérées sans ascenseur horizontal
- bouton Ajouter à la commande remonté dans les options
- upsell séquentiel Boissons puis Desserts
- bouton Envoyer en cuisine du bas supprimé ; action haute mise en valeur
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
.pos-v3-brand{height:162px!important;padding:4px 0 28px!important;overflow:visible!important}
.pos-v3-brand .pos-ref-logo{display:block!important;width:78px!important;height:78px!important;max-width:78px!important;object-fit:contain!important;margin:0 auto!important;border-radius:0!important}
.pos-v3-brand .pos-ref-brandname{font-size:18px!important;letter-spacing:3px!important;text-align:center!important;width:100%!important;overflow:visible!important}

/* Barre catégories : plus détendue, mais sans ascenseur horizontal. */
.cats{display:flex!important;flex-wrap:wrap!important;overflow-x:hidden!important;overflow-y:visible!important;white-space:normal!important;gap:9px!important;padding:11px 16px 12px!important}
.cat{padding:11px 16px!important;font-size:12px!important;line-height:1.15!important;min-width:auto!important;white-space:nowrap!important}

/* Ajouter à la commande doit rester immédiatement identifiable. */
#options .action.add{width:100%!important;min-height:54px!important;margin:0 0 12px!important;background:linear-gradient(180deg,#f0c568,#e4ad43)!important;color:#111!important;border:0!important;border-radius:9px!important;font-size:15px!important;font-weight:950!important;box-shadow:0 5px 18px #0005!important}

/* Le gros doublon Envoyer cuisine du bas disparaît ; Encaisser reste. */
.pos-ref-kitchen{display:none!important}
.pos-ref-actions{padding-top:8px!important}

/* Action Envoyer cuisine dans l'encart haut. */
.pos-ref-top-kitchen{display:inline-flex!important;align-items:center!important;justify-content:center!important;gap:7px!important;background:linear-gradient(180deg,#f0c568,#e4ad43)!important;color:#111!important;border:1px solid #f2c35b!important;border-radius:8px!important;padding:9px 12px!important;font-weight:950!important;text-decoration:none!important;box-shadow:none!important}
.pos-ref-top-kitchen:hover{filter:brightness(1.04)}

.pos-ref-backtop{display:none;position:fixed;right:448px;bottom:22px;z-index:9000;width:42px;height:42px;border-radius:50%;border:1px solid #745b28;background:#17130d;color:#f2c35b;font-size:22px;font-weight:900;cursor:pointer;box-shadow:0 5px 18px #0008}.pos-ref-backtop.show{display:block}
.pos-ref-upsell-overlay .pos-ref-modal{width:min(720px,96vw)!important}.pos-ref-upsell-list{grid-template-columns:repeat(2,minmax(0,1fr))!important;max-height:58vh!important;overflow:auto!important}.pos-ref-upsell-title{margin:0 0 12px!important}.pos-ref-upsell-item{min-height:72px!important}
@media(max-width:1250px){.pos-ref-backtop{right:388px}.cats{gap:7px!important;padding:10px 13px!important}.cat{padding:10px 13px!important;font-size:11px!important}}
@media(max-width:900px){.pos-ref-backtop{right:20px}.pos-ref-upsell-list{grid-template-columns:1fr!important}}
</style>
<script id="pos-reference-finish-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   const norm=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
   const euro=v=>Number(v||0).toFixed(2).replace('.',',')+' €';
   const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

   /* Logo embarqué : aucune dépendance réseau externe. */
   const brand=document.querySelector('.pos-v3-brand');
   if(brand)brand.innerHTML='<img class="pos-ref-logo" src="data:image/png;base64,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" alt="BÉCHÉFAA"><div class="pos-ref-brandname">BÉCHÉFAA</div>';

   /* Remonte physiquement le bouton Ajouter dans le bloc options. */
   const options=document.getElementById('options');
   function liftAdd(){
     if(!options)return;
     const add=options.querySelector('.action.add');if(!add)return;
     const summary=options.querySelector('.selection-summary');
     if(summary){if(summary.nextElementSibling!==add)summary.insertAdjacentElement('afterend',add)}
     else if(options.firstElementChild!==add)options.insertBefore(add,options.firstChild);
   }
   if(options){liftAdd();new MutationObserver(()=>setTimeout(liftAdd,0)).observe(options,{childList:true,subtree:true})}

   /* Met en valeur l'action Envoyer cuisine déjà présente dans l'encart de commande. */
   const orderMessage=document.getElementById('order-message')||document.querySelector('.cart .success')?.parentElement;
   function styleTopKitchen(){
     document.querySelectorAll('.cart a,.cart button').forEach(el=>{
       const t=norm(el.textContent);
       if(t.includes('envoyer')&&t.includes('cuisine')){
         el.classList.add('pos-ref-top-kitchen');
         if(!el.dataset.posRefKitchenStyled){el.dataset.posRefKitchenStyled='1';el.innerHTML='👨‍🍳 <span>ENVOYER EN CUISINE</span>'}
       }
     })
   }
   styleTopKitchen();
   const cart=document.querySelector('.cart');if(cart)new MutationObserver(()=>setTimeout(styleTopKitchen,0)).observe(cart,{childList:true,subtree:true});

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
   let sequenceActive=false;
   let lastOpen=false;

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
   function openDessert(){phase='dessert';sequenceActive=true;overlay.classList.add('open');setTimeout(renderPhase,0)}
   new MutationObserver(function(){
     const now=overlay.classList.contains('open');
     if(now&&!lastOpen){
       if(!sequenceActive){sequenceActive=true;phase='drink'}
       setTimeout(renderPhase,0);
     }
     lastOpen=now;
   }).observe(overlay,{attributes:true,attributeFilter:['class']});

   overlay.addEventListener('click',function(e){
     const product=e.target.closest('[data-finish-upsell-id]');
     if(product){
       e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
       const chosen=phase;
       overlay.classList.remove('open');
       if(typeof showOptions==='function')showOptions(product.dataset.finishUpsellId,product.dataset.finishUpsellName);
       if(chosen==='drink')setTimeout(openDessert,140);
       else sequenceActive=false;
       return;
     }
     if(e.target.closest('.pos-ref-no')){
       e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
       if(phase==='drink')openDessert();
       else{sequenceActive=false;overlay.classList.remove('open')}
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
                response.headers["X-Bechefaa-POS-Finish"] = "upsell-sequential-v2"
        except Exception:
            pass
        return response

    app.view_functions["pos"] = pos_finish_view
    app._bechefaa_pos_reference_finish = True
