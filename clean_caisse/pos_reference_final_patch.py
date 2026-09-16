"""Derniers ajustements visuels POS d'après validation écran.

- Salle devient Sur place dans la barre haute.
- Un seul bouton Envoyer en cuisine : celui de l'encart haut.
- La barre des catégories est légèrement plus aérée sans scroll horizontal.
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
/* Catégories : un peu plus d'air, toujours sans ascenseur horizontal. */
.cats{gap:10px!important;padding:12px 16px 13px!important;overflow-x:hidden!important;overflow-y:visible!important;flex-wrap:wrap!important}
.cat{padding:12px 17px!important;font-size:12px!important;line-height:1.15!important}

/* Un seul bouton Envoyer en cuisine : celui de l'encart haut. */
.pos-ref-actions .pos-ref-kitchen,
.pos-ref-actions [data-action="send-kitchen"],
.pos-ref-actions button[data-action*="kitchen"],
.pos-ref-actions a[data-action*="kitchen"]{display:none!important}

.pos-ref-top-kitchen{display:flex!important;width:100%!important;min-height:50px!important;background:linear-gradient(180deg,#f0c568,#df9d18)!important;color:#111!important;border:0!important;border-radius:9px!important;font-size:14px!important;font-weight:950!important;align-items:center!important;justify-content:center!important;gap:8px!important;text-transform:uppercase!important}

@media(max-width:1250px){.cats{gap:8px!important;padding:11px 14px 12px!important}.cat{padding:11px 14px!important}}
</style>
<script id="pos-reference-final-patch-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   const norm=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();

   function fixServiceLabel(){
     document.querySelectorAll('.ticket-choice [data-ticket="Salle"]').forEach(function(b){
       b.innerHTML='🍴&nbsp;&nbsp;SUR PLACE';
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

   function apply(){fixServiceLabel();hideDuplicateKitchen();styleTopKitchen()}
   apply();
   const cart=document.querySelector('.cart');if(cart)new MutationObserver(()=>setTimeout(apply,0)).observe(cart,{childList:true,subtree:true});
   const toolbar=document.querySelector('.pos-v3-toolbar');if(toolbar)new MutationObserver(()=>setTimeout(fixServiceLabel,0)).observe(toolbar,{childList:true,subtree:true});
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
                response.headers["X-Bechefaa-POS-Final-Patch"] = "service-kitchen-1"
        except Exception:
            pass
        return response

    app.view_functions["pos"] = pos_final_patch_view
    app._bechefaa_pos_reference_final_patch = True
