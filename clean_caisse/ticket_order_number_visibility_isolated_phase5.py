"""Phase 5 — masque le numéro interne de commande sur les tickets imprimés.

INACTIF : ce module n'est ni importé ni enregistré dans wsgi_caisse.py.

Le numéro interne reste intact en base et disponible pour la traçabilité.
Cette couche agit uniquement sur le HTML des tickets client et cuisine.
"""
from flask import request


def register_ticket_order_number_visibility_isolated_phase5(app):
    @app.after_request
    def ticket_order_number_visibility_after_phase5(response):
        if response.status_code != 200 or response.mimetype != "text/html":
            return response
        if not (request.path.startswith("/impression/client/") or request.path.startswith("/impression/cuisine/")):
            return response

        html = response.get_data(as_text=True)

        # Le rendu historique de printing_phase1 contient une ligne dédiée au
        # numéro interne. On la masque sans modifier la donnée ni le backend.
        html = html.replace(
            '<style>',
            '<style>.cnum,.knum{display:none!important}</style><style>',
            1,
        )

        response.set_data(html)
        return response
