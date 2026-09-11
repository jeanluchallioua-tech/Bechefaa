"""Phase 4.4 — identité visuelle des commandes en cuisine et confirmation caisse.

Affichage uniquement : aucun identifiant technique ni numéro opérationnel n'est
modifié en base.
- Salle -> Table N
- Emporter caisse -> À EMPORTER — Nom client
- Emporter site -> Nom client uniquement
- Livraison -> LIVRAISON — Nom client
Le numéro #xx n'est plus affiché sur l'écran cuisine ni dans le bloc de confirmation POS.
"""
from flask import request


def register_kitchen_identity_phase44(app):
    @app.after_request
    def kitchen_identity_phase44(response):
        if request.method != "GET" or request.path not in ("/cuisine-preparation", "/pos"):
            return response
        if response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)

        if request.path == "/cuisine-preparation":
            marker = "function card(o){"
            helper = r'''function orderIdentity(o){
  let table=String(o.table_label||'').trim();
  if(table)return table.toUpperCase();
  let source=String(o.source||'').toUpperCase();
  let channel=String(o.sales_channel||'').toUpperCase();
  let customer=String(o.customer_name||'').trim();
  let generic=/^client\s+(comptoir|livraison)$/i.test(customer);
  if(source==='LIVRAISON'||source==='DELIVERY')return generic||!customer?'LIVRAISON':'LIVRAISON — '+customer;
  if(channel==='SITE'&&!generic&&customer)return customer;
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
            html = html.replace(
                "${channelBadge(o.source)}${modeBadge(o.ticket_type)}",
                "${channelBadge(o.sales_channel||o.source)}${modeBadge(o.ticket_type)}",
            )
            html = html.replace("SITE INTERNET</span>", "SITE</span>")

        if request.path == "/pos":
            marker = "function saveOrder(){"
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
            if marker in html and "function posOrderIdentity(d)" not in html:
                html = html.replace(marker, helper + marker, 1)
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
