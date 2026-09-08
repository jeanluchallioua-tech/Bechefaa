"""Phase 3.0 — sécurisation des modifications de commande.

Le PUT /api/orders/<id> est validé côté serveur avec le même catalogue canonique
que la création. Le navigateur ne peut donc pas imposer un prix, un nom produit
ou une option différente du catalogue.

Aucune modification de schéma et aucune écriture hors du flux PUT existant.
"""
import json
from decimal import Decimal, InvalidOperation

from flask import jsonify, request

from clean_caisse.order_price_guard_phase26 import _canonical_price


def _money(value):
    try:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Prix invalide")


def register_order_update_guard_phase30(app, db):
    @app.before_request
    def order_update_guard_phase30():
        if request.method != "PUT" or not request.path.startswith("/api/orders/"):
            return None

        # Cette garde concerne uniquement la modification d'une commande.
        # Les sous-routes cuisine ont d'autres méthodes et ne passent pas ici.
        order_id = request.path[len("/api/orders/"):].strip("/")
        if not order_id or "/" in order_id:
            return None

        payload = request.get_json(silent=True) or {}
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            return None  # Le endpoint historique conserve sa validation habituelle.

        try:
            with db() as conn:
                row = conn.execute(
                    "SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1"
                ).fetchone()
            if not row:
                return jsonify({"ok": False, "error": "Catalogue introuvable"}), 503

            data = json.loads(row["data_json"] or "{}")
            products = data.get("products") if isinstance(data, dict) else []
            if not isinstance(products, list):
                return jsonify({"ok": False, "error": "Catalogue produits invalide"}), 503

            by_id = {}
            duplicates = set()
            for product in products:
                if not isinstance(product, dict):
                    continue
                product_id = str(product.get("id") or "").strip()
                if not product_id:
                    continue
                if product_id in by_id:
                    duplicates.add(product_id)
                else:
                    by_id[product_id] = product

            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    return jsonify({"ok": False, "error": "Ligne invalide", "line": index + 1}), 409

                product_id = str(item.get("product_id") or "").strip()
                if not product_id or product_id in duplicates or product_id not in by_id:
                    return jsonify({
                        "ok": False,
                        "error": "Produit catalogue introuvable ou ambigu",
                        "productId": product_id,
                        "line": index + 1,
                    }), 409

                product = by_id[product_id]
                canonical_name = str(product.get("name") or "").strip()
                received_name = str(item.get("name") or "").strip()
                if canonical_name != received_name:
                    return jsonify({
                        "ok": False,
                        "error": "Nom produit différent du catalogue",
                        "productId": product_id,
                        "line": index + 1,
                    }), 409

                selected = item.get("options") if isinstance(item.get("options"), list) else []
                canonical = _canonical_price(product, selected)
                received = _money(item.get("unit_price", 0))
                if canonical != received:
                    return jsonify({
                        "ok": False,
                        "error": "Prix de commande différent du catalogue",
                        "productId": product_id,
                        "product": canonical_name,
                        "receivedPrice": float(received),
                        "serverPrice": float(canonical),
                        "line": index + 1,
                    }), 409

        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        except Exception as exc:
            return jsonify({
                "ok": False,
                "error": "Validation serveur de la modification impossible",
                "detail": str(exc),
            }), 503

        return None
