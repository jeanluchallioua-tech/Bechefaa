"""Phase 4.4 — identité visuelle des commandes dans l'historique.

Affichage uniquement : les identifiants techniques et numéros internes restent
inchangés en base.
- Salle -> Table N
- Emporter -> À EMPORTER — Nom client
- Livraison -> LIVRAISON — Nom client
Aucun #xx n'est affiché dans l'historique normal.
"""
from flask import request


def register_history_identity_phase44(app):
    @app.after_request
    def history_identity_phase44(response):
        if request.method != "GET" or request.path != "/historique-modification":
            return response
        if response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        marker = "function render(){"
        helper = r'''function historyIdentity(o){
  let table=String(o.table_label||'').trim();
  if(table)return table.toUpperCase();
  let source=String(o.source||'').toUpperCase();
  let customer=String(o.customer_name||'').trim();
  let generic=/^client\s+(comptoir|livraison)$/i.test(customer);
  if(source==='LIVRAISON'||source==='DELIVERY')return generic||!customer?'LIVRAISON':'LIVRAISON — '+customer;
  return generic||!customer?'À EMPORTER':'À EMPORTER — '+customer;
}
'''
        if marker in html and "function historyIdentity(o)" not in html:
            html = html.replace(marker, helper + marker, 1)

        html = html.replace(
            "#${esc(o.num)} · ${esc(o.customer_name)} ",
            "${esc(historyIdentity(o))} ",
            1,
        )
        html = html.replace(
            "#${esc(o.num)} · ${esc(o.service_label||o.table_label||o.customer_name)}",
            "${esc(historyIdentity(o))}",
            1,
        )
        html = html.replace(
            "alert('#'+o.num+'\\n'+o.status",
            "alert(historyIdentity(o)+'\\n'+o.status",
            1,
        )
        html = html.replace(
            "document.getElementById('mtitle').textContent='Modifier commande #'+o.num;",
            "document.getElementById('mtitle').textContent='Modifier — '+historyIdentity(o);",
            1,
        )
        html = html.replace(
            "document.getElementById('mmsg').innerHTML='<div class=\"success\">Commande #'+esc(d.num)+' modifiée. Statut : '+esc(d.status)",
            "document.getElementById('mmsg').innerHTML='<div class=\"success\">Commande modifiée. Statut : '+esc(d.status)",
            1,
        )

        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
