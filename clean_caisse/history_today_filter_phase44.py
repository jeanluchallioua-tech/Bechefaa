"""Phase 4.4 — filtre isolé de l'historique opérationnel du jour.

Ne modifie pas clean_caisse/app.py ni les données PostgreSQL.
Le filtre agit uniquement sur la réponse JSON de /api/orders/history :
- conserve les commandes créées aujourd'hui en Europe/Paris ;
- exclut les commandes annulées ;
- laisse toutes les autres routes inchangées.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import request


PARIS_TZ = ZoneInfo("Europe/Paris")


def register_history_today_filter_phase44(app):
    @app.after_request
    def filter_history_today_phase44(response):
        if request.path != "/api/orders/history" or response.status_code != 200:
            return response

        try:
            payload = response.get_json(silent=True)
            if not isinstance(payload, dict) or not payload.get("ok"):
                return response

            orders = payload.get("orders")
            if not isinstance(orders, list):
                return response

            today = datetime.now(PARIS_TZ).date()
            filtered = []

            for order in orders:
                if not isinstance(order, dict):
                    continue
                if str(order.get("status") or "").strip().upper() == "ANNULÉE":
                    continue

                created_at = order.get("created_at")
                try:
                    created_ms = int(created_at)
                    created_date = datetime.fromtimestamp(created_ms / 1000.0, PARIS_TZ).date()
                except (TypeError, ValueError, OSError, OverflowError):
                    continue

                if created_date == today:
                    filtered.append(order)

            payload["orders"] = filtered
            payload["count"] = len(filtered)
            response.set_data(app.json.dumps(payload))
            response.content_type = "application/json"
        except Exception:
            # Sécurité anti-régression : si le filtre rencontre un problème,
            # on renvoie la réponse stable d'origine sans la casser.
            return response

        return response
