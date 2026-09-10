"""Phase 5 — fondation isolée des canaux de vente.

INACTIF : ce module n'est ni importé ni enregistré dans wsgi_caisse.py.
Il prépare un champ métier distinct du mode de service existant afin de ne pas
confondre Salle/Emporter/Livraison avec le canal commercial.

Canaux prévus : RESTO, SITE, UBER_EATS, DELIVEROO.
Aucune statistique ni interface n'est modifiée tant que ce module reste inactif.
"""

import json

from flask import g, request


SALES_CHANNELS = ("RESTO", "SITE", "UBER_EATS", "DELIVEROO")


def _normalize_sales_channel(value):
    raw = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "": "RESTO",
        "CAISSE": "RESTO",
        "RESTAURANT": "RESTO",
        "RESTO": "RESTO",
        "WEB": "SITE",
        "WIX": "SITE",
        "SITE": "SITE",
        "SITE_INTERNET": "SITE",
        "UBER": "UBER_EATS",
        "UBEREAT": "UBER_EATS",
        "UBEREATS": "UBER_EATS",
        "UBER_EATS": "UBER_EATS",
        "DELIVEROO": "DELIVEROO",
    }
    return aliases.get(raw, "RESTO")


def register_sales_channels_isolated_phase5(app, db):
    """Prépare la persistance du canal sur les nouvelles commandes.

    Le champ ``source`` existant reste totalement inchangé : il continue de
    porter le mode de service historique. Le nouveau champ ``sales_channel``
    sert uniquement à la ventilation commerciale future.
    """

    @app.before_request
    def capture_sales_channel_phase5():
        if request.path != "/api/orders" or request.method != "POST":
            return None
        payload = request.get_json(silent=True) or {}
        g.phase5_sales_channel = _normalize_sales_channel(
            payload.get("sales_channel") or payload.get("channel")
        )
        return None

    @app.after_request
    def persist_sales_channel_phase5(response):
        if request.path != "/api/orders" or request.method != "POST":
            return response
        if response.status_code < 200 or response.status_code >= 300:
            return response

        try:
            body = response.get_json(silent=True)
            if not isinstance(body, dict):
                body = json.loads(response.get_data(as_text=True) or "{}")
            order_id = str(body.get("id") or "").strip()
            if not order_id:
                return response

            channel = _normalize_sales_channel(getattr(g, "phase5_sales_channel", "RESTO"))
            with db() as conn:
                with conn.transaction():
                    conn.execute(
                        "ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS sales_channel TEXT NOT NULL DEFAULT 'RESTO'"
                    )
                    conn.execute(
                        "UPDATE caisse_orders SET sales_channel=%s WHERE id=%s",
                        (channel, order_id),
                    )
        except Exception:
            # Une commande déjà créée ne doit jamais être transformée en erreur
            # à cause de la future ventilation commerciale.
            return response

        return response
