"""Phase 7 — préparation paiement Site BÉCHÉFAA.

Étape isolée et sans encaissement : expose un calcul de panier canonique pour le Site.
Aucune commande n'est créée, rien n'est envoyé en cuisine et aucun paiement n'est lancé.
Le calcul réutilise exactement le verrou serveur de prix de la caisse.
"""
import json
from decimal import Decimal

from flask import jsonify, request

from clean_caisse.order_price_guard_phase26 import _canonical_price


def register_site_payment_quote_isolated_phase7(app, db):
    def load_products():
        with db() as conn:
            row = conn.execute(
                "SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1"
            ).fetchone()
        if not row:
            raise RuntimeError("Catalogue introuvable")
        data = json.loads(row["data_json"] or "{}")
        products = data.get("products") if isinstance(data, dict) else []
        if not isinstance(products, list):
            raise RuntimeError("Catalogue produits invalide")
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
        return by_id, duplicates

    @app.get("/api/public/site-payment/status")
    def site_payment_status_phase7():
        return jsonify({
            "ok": True,
            "phase": "7",
            "mode": "preparation",
            "quote_ready": True,
            "creates_order": False,
            "sends_kitchen": False,
            "charges_card": False,
        })

    @app.post("/api/public/site-payment/quote")
    def site_payment_quote_phase7():
        payload = request.get_json(silent=True) or {}
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            return jsonify({"ok": False, "error": "Panier vide"}), 400

        try:
            by_id, duplicates = load_products()
            total = Decimal("0.00")
            lines = []

            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    return jsonify({"ok": False, "error": "Ligne panier invalide", "line": index + 1}), 400

                product_id = str(item.get("id") or item.get("product_id") or "").strip()
                if not product_id:
                    return jsonify({"ok": False, "error": "Produit sans identifiant catalogue", "line": index + 1}), 409
                if product_id in duplicates or product_id not in by_id:
                    return jsonify({"ok": False, "error": "Produit catalogue introuvable ou ambigu", "productId": product_id, "line": index + 1}), 409

                try:
                    qty = int(item.get("qty") or item.get("quantity") or 1)
                except (TypeError, ValueError):
                    qty = 0
                if qty < 1 or qty > 99:
                    return jsonify({"ok": False, "error": "Quantité invalide", "line": index + 1}), 400

                selected = item.get("options") if isinstance(item.get("options"), list) else []
                unit = _canonical_price(by_id[product_id], selected)
                line_total = (unit * qty).quantize(Decimal("0.01"))
                total += line_total
                lines.append({
                    "productId": product_id,
                    "name": by_id[product_id].get("name") or item.get("name") or "",
                    "qty": qty,
                    "unitPrice": float(unit),
                    "lineTotal": float(line_total),
                })

            total = total.quantize(Decimal("0.01"))
            return jsonify({
                "ok": True,
                "readOnly": True,
                "currency": "EUR",
                "items": lines,
                "total": float(total),
                "createsOrder": False,
                "sendsKitchen": False,
                "chargesCard": False,
            })
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        except Exception as exc:
            return jsonify({"ok": False, "error": "Calcul du panier impossible", "detail": str(exc)}), 503
