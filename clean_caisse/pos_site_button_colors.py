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
/* Couleur dorée de référence BÉCHÉFAA — sélecteurs réels du POS. */
button[data-action="save-order"],
.action.save,
button[data-action="send-kitchen"],
a[data-action="send-kitchen"],
.pos-ref-top-kitchen,
.print-kitchen{
  background:#f0bd45!important;
  background-image:none!important;
  color:#111!important;
  border-color:#f0bd45!important;
}
button[data-action="save-order"]:hover,
.action.save:hover,
button[data-action="send-kitchen"]:hover,
a[data-action="send-kitchen"]:hover,
.pos-ref-top-kitchen:hover,
.print-kitchen:hover{
  background:#f0bd45!important;
  background-image:none!important;
  color:#111!important;
  filter:brightness(.96)!important;
}
/* Le ticket client reste volontairement bleu. */
.print-client{background:#2563eb!important;color:#fff!important}
</style>
<script id="pos-site-button-colors-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   function gold(el){
     if(!el)return;
     el.style.setProperty('background','#f0bd45','important');
     el.style.setProperty('background-image','none','important');
     el.style.setProperty('border-color','#f0bd45','important');
     el.style.setProperty('color','#111','important');
   }
   function apply(){
     document.querySelectorAll(
       'button[data-action="save-order"],.action.save,'+
       'button[data-action="send-kitchen"],a[data-action="send-kitchen"],'+
       '.pos-ref-top-kitchen,.print-kitchen'
     ).forEach(gold);
     /* Ne jamais recolorer le ticket client. */
     document.querySelectorAll('.print-client').forEach(function(el){
       el.style.setProperty('background','#2563eb','important');
       el.style.setProperty('color','#fff','important');
     });
   }
   apply();
   new MutationObserver(function(){setTimeout(apply,0)}).observe(document.body,{childList:true,subtree:true});
   /* Sécurité contre les modules qui recréent/restylent les actions après coup. */
   setInterval(apply,500);
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
                response.headers["X-Bechefaa-POS-Button-Colors"] = "site-gold-real-selectors"
        except Exception:
            pass
        return response

    app.view_functions["pos"] = pos_site_button_colors_view
    app._bechefaa_pos_site_button_colors = True
