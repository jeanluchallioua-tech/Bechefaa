"""Canaux de vente isolés — RESTO / SITE / UBER_EATS / DELIVEROO.

Le mode de service historique reste dans ``source`` (Salle/Emporter/Livraison).
Le canal commercial est conservé séparément dans ``sales_channel``.

Ce module ne gère plus d'interface de notification sur /pos.
Les notifications SITE sont centralisées dans ``order_notifications_phase33.py``
afin d'éviter deux systèmes concurrents avec des marqueurs localStorage différents.
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


def _add_sales_channels_to_orders(db, body):
    if not isinstance(body, dict) or not isinstance(body.get("orders"), list):
        return body

    ids = [
        str(order.get("id") or "").strip()
        for order in body["orders"]
        if isinstance(order, dict)
    ]
    ids = [order_id for order_id in ids if order_id]
    if not ids:
        return body

    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT id, COALESCE(sales_channel, 'RESTO') AS sales_channel "
                "FROM caisse_orders WHERE id = ANY(%s)",
                (ids,),
            ).fetchall()
        channels = {
            str(row["id"]): _normalize_sales_channel(row["sales_channel"])
            for row in rows
        }
        for order in body["orders"]:
            if isinstance(order, dict):
                order["sales_channel"] = channels.get(
                    str(order.get("id") or ""), "RESTO"
                )
    except Exception:
        # Compatibilité avec une base plus ancienne : aucune erreur métier.
        for order in body["orders"]:
            if isinstance(order, dict):
                order.setdefault("sales_channel", "RESTO")
    return body


def register_sales_channels_isolated_phase5(app, db):
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

            channel = _normalize_sales_channel(
                getattr(g, "phase5_sales_channel", "RESTO")
            )
            with db() as conn:
                with conn.transaction():
                    conn.execute(
                        "ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS "
                        "sales_channel TEXT NOT NULL DEFAULT 'RESTO'"
                    )
                    conn.execute(
                        "UPDATE caisse_orders SET sales_channel=%s WHERE id=%s",
                        (channel, order_id),
                    )
        except Exception:
            # Une commande créée ne devient jamais une erreur à cause du canal.
            return response

        return response

    @app.after_request
    def expose_sales_channel_phase5(response):
        if response.status_code != 200:
            return response

        if request.method == "GET" and request.path in (
            "/api/kitchen/orders",
            "/api/kitchen/board",
        ):
            try:
                body = response.get_json(silent=True)
                body = _add_sales_channels_to_orders(db, body)
                response.set_data(json.dumps(body, ensure_ascii=False))
                response.content_type = "application/json; charset=utf-8"
                response.content_length = len(response.get_data())
            except Exception:
                pass

        return response
