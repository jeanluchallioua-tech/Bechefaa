"""Phase 4.4 — identité visuelle des commandes en cuisine.

Affichage uniquement : aucun identifiant technique ni numéro opérationnel n'est
modifié en base.
- Salle -> Table N
- Emporter -> À EMPORTER — Nom client
- Livraison -> LIVRAISON — Nom client
Le numéro #xx n'est plus affiché sur l'écran cuisine.
"""
from flask import request


def register_kitchen_identity_phase44(app):
    @app.after_request
    def kitchen_identity_phase44(response):
        if request.method != "GET" or request.path != "/cuisine-preparation":
            return response
        if response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        marker = "function card(o){"
        helper = r'''function orderIdentity(o){
  let table=String(o.table_label||'').trim();
  if(table)return table.toUpperCase();
  let source=String(o.source||'').toUpperCase();
  let customer=String(o.customer_name||'').trim();
  let generic=/^client\s+(comptoir|livraison)$/i.test(customer);
  if(source==='LIVRAISON'||source==='DELIVERY')return generic||!customer?'LIVRAISON':'LIVRAISON — '+customer;
  return generic||!customer?'À EMPORTER':'À EMPORTER — '+customer;
}
'''
        if marker in html and "function orderIdentity(o)" not in html:
            html = html.replace(marker, helper + marker, 1)

        html = html.replace(
            "#${esc(o.num)} · ${esc(o.customer_name)}",
            "${esc(orderIdentity(o))}",
            1,
        )
        html = html.replace(
            "#${esc(o.num)} · ${esc(o.service_label||o.customer_name)}",
            "${esc(orderIdentity(o))}",
            1,
        )

        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
