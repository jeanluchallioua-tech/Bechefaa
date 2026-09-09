"""Phase 4.2 — libellé d'exploitation des commandes.

Couche d'affichage uniquement :
- Salle -> Table N
- Emporter -> À emporter
- Livraison -> nom réel du client
Ne modifie aucune donnée PostgreSQL ni les modules gelés de Phase 3.
"""
from flask import request


def register_service_label_phase42(app):
    @app.after_request
    def service_label_phase42(response):
        if request.method != "GET" or response.status_code != 200:
            return response

        # Enrichit les JSON déjà produits par les modules gelés.
        if request.path in ("/api/kitchen/board", "/api/kitchen/orders", "/api/orders/history"):
            try:
                data = response.get_json(silent=True)
                if not isinstance(data, dict) or not isinstance(data.get("orders"), list):
                    return response
                for order in data["orders"]:
                    if not isinstance(order, dict):
                        continue
                    source = str(order.get("source") or "").upper()
                    table_label = str(order.get("table_label") or "").strip()
                    customer = str(order.get("customer_name") or "").strip()
                    if table_label:
                        label = table_label
                    elif source in ("LIVRAISON", "DELIVERY"):
                        label = customer or "Livraison"
                    else:
                        label = "À emporter"
                    order["service_label"] = label
                response.set_data(app.json.dumps(data, ensure_ascii=False))
                response.content_type = "application/json; charset=utf-8"
            except Exception:
                pass
            return response

        # Cuisine : utilise le libellé enrichi sans modifier la logique du tableau.
        if request.path == "/cuisine-preparation" and response.mimetype == "text/html":
            html = response.get_data(as_text=True)
            html = html.replace(
                "#${esc(o.num)} · ${esc(o.customer_name)}",
                "#${esc(o.num)} · ${esc(o.service_label||o.customer_name)}",
                1,
            )
            response.set_data(html)
            response.content_length = len(response.get_data())
            return response

        # Historique : même règle d'affichage, si la page reste accessible directement.
        if request.path == "/historique-modification" and response.mimetype == "text/html":
            html = response.get_data(as_text=True)
            html = html.replace(
                "#${esc(o.num)} · ${esc(o.table_label||o.customer_name)}",
                "#${esc(o.num)} · ${esc(o.service_label||o.table_label||o.customer_name)}",
                1,
            )
            response.set_data(html)
            response.content_length = len(response.get_data())
        return response
