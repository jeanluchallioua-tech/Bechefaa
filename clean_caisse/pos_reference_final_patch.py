"""Derniers ajustements visuels POS d'après validation écran.

- Salle devient Sur place dans la barre haute.
- Un seul bouton Envoyer en cuisine : celui de l'encart haut.
- La barre des catégories affiche uniquement les catégories métier en grille 5 x 2.
- Le bouton Tous les produits est masqué visuellement sans supprimer sa logique interne.
- La grille 5 x 2 est forcée en style inline important pour résister aux couches CSS antérieures.
- Le bouton Envoyer en cuisine reprend l'accent couleur du site BÉCHÉFAA.
Aucune logique métier ni base de données modifiée.
"""


def register_pos_reference_final_patch(app):
    if getattr(app, "_bechefaa_pos_reference_final_patch", False):
        return
    original = app.view_functions.get("pos")
    if original is None:
        return

    addon = r'''
<style id="pos-reference-final-patch-style">
/* Catégories : 10 catégories métier en grille 5 x 2, sans changer le filtrage interne. */
.cats{display:grid!important;grid-template-columns:repeat(5,minmax(0,1fr))!important;grid-auto-rows:minmax(44px,auto)!important;align-items:stretch!important;gap:9px!important;padding:11px 16px 12px!important;overflow:visible!important;white-space:normal!important}
.cat{width:100%!important;min-width:0!important;max-width:none!important;overflow:hidden!important;text-overflow:ellipsis!important;white-space:nowrap!important;padding:11px 10px!important;font-size:12px!important;line-height:1.15!important;border-radius:9px!important;text-align:center!important;display:flex!important;align-items:center!important;justify-content:center!important}
.cat.pos-ref-all-hidden{display:none!important}

/* Un seul bouton Envoyer en cuisine : celui de l'encart haut. */
.pos-ref-actions .pos-ref-kitchen,
.pos-ref-actions [data-action="send-kitchen"],
.pos-ref-actions button[data-action*="kitchen"],
.pos-ref-actions a[data-action*="kitchen"]{display:none!important}

/* Couleur exactement alignée sur le site BÉCHÉFAA. */
.pos-ref-top-kitchen{display:flex!important;width:100%!important;min-height:50px!important;background:#d99a18!important;color:#111!important;border:1px solid #d99a18!important;border-radius:9px!important;font-size:14px!important;font-weight:950!important;align-items:center!important;justify-content:center!important;gap:8px!important;text-transform:uppercase!important}
.pos-ref-top-kitchen:hover,.pos-ref-top-kitchen:active{background:#f0bd45!important;border-color:#f0bd45!important;color:#111!important}

@media(max-width:1250px){.cats{gap:8px!important;padding:10px 14px 11px!important}.cat{padding:10px 8px!important;font-size:11.5px!important}}
@media(max-width:900px){.cats{grid-template-columns:repeat(5,minmax(0,1fr))!important;gap:7px!important}.cat{font-size:11px!important;padding:9px 6px!important}}
</style>
<script id="pos-reference-final-patch-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   const norm=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
   const isAllProducts=el=>{const t=norm(el&&el.textContent);return t==='tous les produits'||t==='tous nos produits'||t==='tous produits'};

   function fixServiceLabel(){
     document.querySelectorAll('.ticket-choice [data-ticket="Salle"]').forEach(function(b){
       b.innerHTML='🍴&nbsp;&nbsp;SUR PLACE';
     });
   }

   function forceCategoryGrid(){
     const cats=document.querySelector('.cats');
     if(!cats)return;
     cats.style.setProperty('display','grid','important');
     cats.style.setProperty('grid-template-columns','repeat(5,minmax(0,1fr))','important');
     cats.style.setProperty('grid-auto-rows','minmax(44px,auto)','important');
     cats.style.setProperty('align-items','stretch','important');
     cats.style.setProperty('gap','9px','important');
     cats.style.setProperty('padding','11px 16px 12px','important');
     cats.style.setProperty('overflow','visible','important');
     cats.style.setProperty('white-space','normal','important');
     cats.querySelectorAll('.cat').forEach(function(el){
       if(isAllProducts(el)){
         el.classList.add('pos-ref-all-hidden');
         el.style.setProperty('display','none','important');
         return;
       }
       el.style.setProperty('width','100%','important');
       el.style.setProperty('min-width','0','important');
       el.style.setProperty('max-width','none','important');
       el.style.setProperty('white-space','nowrap','important');
       el.style.setProperty('overflow','hidden','important');
       el.style.setProperty('text-overflow','ellipsis','important');
       el.style.setProperty('display','flex','important');
       el.style.setProperty('align-items','center','important');
       el.style.setProperty('justify-content','center','important');
       el.style.setProperty('text-align','center','important');
       el.style.setProperty('padding','11px 10px','important');
     });
   }

   function hideAllProductsCategory(){
     const cats=document.querySelector('.cats');
     if(!cats)return;
     cats.querySelectorAll('.cat').forEach(function(el){
       if(isAllProducts(el)){
         el.classList.add('pos-ref-all-hidden');
         el.style.setProperty('display','none','important');
       }
     });
   }

   function hideDuplicateKitchen(){
     document.querySelectorAll('.pos-ref-actions button,.pos-ref-actions a').forEach(function(el){
       const t=norm(el.textContent);
       if(t.includes('envoyer')&&t.includes('cuisine'))el.style.setProperty('display','none','important');
     });
   }

   function styleTopKitchen(){
     document.querySelectorAll('.cart a,.cart button').forEach(function(el){
       if(el.closest('.pos-ref-actions'))return;
       const t=norm(el.textContent);
       if(t.includes('envoyer')&&t.includes('cuisine')){
         el.classList.add('pos-ref-top-kitchen');
         if(!el.dataset.posRefFinalKitchen){
           el.dataset.posRefFinalKitchen='1';
           el.innerHTML='👨‍🍳 <span>ENVOYER EN CUISINE</span>';
         }
       }
     });
   }

   function apply(){fixServiceLabel();forceCategoryGrid();hideAllProductsCategory();hideDuplicateKitchen();styleTopKitchen()}
   apply();
   const cats=document.querySelector('.cats');if(cats)new MutationObserver(()=>setTimeout(()=>{forceCategoryGrid();hideAllProductsCategory()},0)).observe(cats,{childList:true,subtree:true});
   const cart=document.querySelector('.cart');if(cart)new MutationObserver(()=>setTimeout(apply,0)).observe(cart,{childList:true,subtree:true});
   const toolbar=document.querySelector('.pos-v3-toolbar');if(toolbar)new MutationObserver(()=>setTimeout(fixServiceLabel,0)).observe(toolbar,{childList:true,subtree:true});
   setTimeout(()=>{forceCategoryGrid();hideAllProductsCategory()},150);
   setTimeout(()=>{forceCategoryGrid();hideAllProductsCategory()},500);
 })
})();
</script>
'''

    def pos_final_patch_view(*args, **kwargs):
        response = app.make_response(original(*args, **kwargs))
        try:
            if response.status_code == 200 and response.mimetype == "text/html":
                html = response.get_data(as_text=True)
                if "pos-reference-final-patch-style" not in html:
                    html = html.replace("</body>", addon + "</body>")
                    response.set_data(html)
                    response.content_length = len(response.get_data())
                response.headers["X-Bechefaa-POS-Final-Patch"] = "service-kitchen-categories-grid-force-6"
        except Exception:
            pass
        return response

    app.view_functions["pos"] = pos_final_patch_view
    app._bechefaa_pos_reference_final_patch = True
