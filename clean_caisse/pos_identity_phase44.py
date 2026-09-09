"""Phase 4.4 — identité visuelle des commandes sur la caisse.

Affichage uniquement : aucun identifiant technique ni numéro opérationnel n'est
modifié en base.
- Salle -> Table N
- Emporter -> À EMPORTER — Nom client
- Livraison -> LIVRAISON — Nom client
Le numéro #xx n'est plus affiché dans le bloc de confirmation de commande.
"""
from flask import request


def register_pos_identity_phase44(app):
    @app.after_request
    def pos_identity_phase44(response):
        if request.method != "GET" or request.path != "/pos":
            return response
        if response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)

        helper_marker = "function saveOrder(){"
        helper = r'''function posOrderIdentity(d){
  let table=String((d&&d.table_label)||'').trim();
  if(table)return table.toUpperCase();
  let type=String((d&&d.ticket_type)||'').toLowerCase();
  let source=String((d&&d.source)||'').toUpperCase();
  let customer=String((d&&d.customer_name)||'').trim();
  let generic=/^client\s+(comptoir|livraison)$/i.test(customer);
  if(type.includes('livraison')||source==='LIVRAISON'||source==='DELIVERY')return generic||!customer?'LIVRAISON':'LIVRAISON — '+customer;
  return generic||!customer?'À EMPORTER':'À EMPORTER — '+customer;
}
'''
        if helper_marker in html and "function posOrderIdentity(d)" not in html:
            html = html.replace(helper_marker, helper + helper_marker, 1)

        html = html.replace(
            "Commande #${esc(d.num)} enregistrée • ${esc(d.ticket_type)}",
            "${esc(posOrderIdentity(d))} • Commande enregistrée",
            1,
        )
        html = html.replace(
            "Commande #${esc(d.num||orderNum)} envoyée en cuisine",
            "${esc(posOrderIdentity(d))} • Envoyée en cuisine",
            1,
        )

        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
