"""Correctif visuel isolé des boutons d'action POS.

- Enregistrer la commande : doré site
- Envoyer en cuisine : doré site
- Ticket cuisine 80 mm : doré site + texte noir
- Ticket client inchangé (bleu)
Aucune logique métier modifiée.
"""


def register_pos_site_button_colors(app):
    if getattr(app, "_bechefaa_pos_site_button_colors", False):
        return
    original = app.view_functions.get("pos")
    if original is None:
        return

    addon = r'''
<style id="pos-site-button-colors-style">
/* Couleur de référence visuelle du site BÉCHÉFAA. */
.cart .action.save,
.cart [data-action="save-order"],
.cart .pos-ref-top-kitchen{
  background:#f0bd45!important;
  background-image:none!important;
  color:#111!important;
  border-color:#f0bd45!important;
}
.cart .action.save:hover,
.cart [data-action="save-order"]:hover,
.cart .pos-ref-top-kitchen:hover{
  background:#d99a18!important;
  background-image:none!important;
  color:#111!important;
}
</style>
<script id="pos-site-button-colors-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   const norm=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
   function gold(el,blackText){
     if(!el)return;
     el.style.setProperty('background','#f0bd45','important');
     el.style.setProperty('background-image','none','important');
     el.style.setProperty('border-color','#f0bd45','important');
     if(blackText)el.style.setProperty('color','#111','important');
   }
   function apply(){
     document.querySelectorAll('.cart [data-action="save-order"],.cart .action.save,.cart .pos-ref-top-kitchen').forEach(el=>gold(el,true));
     document.querySelectorAll('.cart a,.cart button').forEach(el=>{
       const t=norm(el.textContent);
       if(t.includes('ticket cuisine')&&t.includes('80'))gold(el,true);
     });
   }
   apply();
   const cart=document.querySelector('.cart');
   if(cart)new MutationObserver(()=>setTimeout(apply,0)).observe(cart,{childList:true,subtree:true});
 })
})();
</script>
'''

    def pos_site_button_colors_view(*args, **kwargs):
        response = app.make_response(original(*args, **kwargs))
        try:
            if response.status_code == 200 and response.mimetype == "text/html":
                html = response.get_data(as_text=True)
                if "pos-site-button-colors-style" not in html:
                    html = html.replace("</body>", addon + "</body>")
                    response.set_data(html)
                    response.content_length = len(response.get_data())
                response.headers["X-Bechefaa-POS-Button-Colors"] = "site-gold"
        except Exception:
            pass
        return response

    app.view_functions["pos"] = pos_site_button_colors_view
    app._bechefaa_pos_site_button_colors = True
