"""Phase 4.4 — masquage commercial des commandes annulées.

Les commandes annulées restent en base pour audit mais sont retirées de
l'historique commercial normal.

Important : aucune commande ne présente désormais de bouton « Annuler » dans
l'interface normale. L'annulation est réservée à la zone interne /securite,
protégée par PIN côté serveur.
"""
from flask import request


def register_order_cancellation_ui_phase44(app):
    @app.after_request
    def cancellation_ui_phase44(response):
        if request.path == "/api/orders/history" and response.status_code == 200 and response.is_json:
            try:
                data = response.get_json(silent=True) or {}
                if data.get("ok") and isinstance(data.get("orders"), list):
                    orders = [o for o in data["orders"] if str(o.get("status") or "").upper() != "ANNULÉE"]
                    data["orders"] = orders
                    data["count"] = len(orders)
                    response.set_data(app.json.dumps(data))
                    response.content_type = "application/json"
                    response.content_length = len(response.get_data())
            except Exception:
                pass
        return response
