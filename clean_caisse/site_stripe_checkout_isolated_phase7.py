"""Phase 7.1 — Stripe Checkout Site BÉCHÉFAA, mode test uniquement.

Étape isolée : crée une session Stripe Checkout à partir du prix canonique serveur.
Aucune commande n'est créée ici et rien n'est envoyé en cuisine. Le passage en
commande sera ajouté uniquement après validation du webhook Stripe.
"""
import json
import os
import uuid
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from flask import jsonify, request

from clean_caisse.order_price_guard_phase26 import _canonical_price


def register_site_stripe_checkout_isolated_phase7(app, db):
    def stripe_key():
        return str(os.getenv("STRIPE_SECRET_KEY") or "").strip()

    def site_url():
        return str(os.getenv("SITE_PUBLIC_URL") or "").strip().rstrip("/")

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

    def canonical_lines(payload):
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("Panier vide")
        by_id, duplicates = load_products()
        lines = []
        total = Decimal("0.00")
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"Ligne panier invalide : {index + 1}")
            product_id = str(item.get("id") or item.get("product_id") or "").strip()
            if not product_id:
                raise ValueError(f"Produit sans identifiant catalogue : ligne {index + 1}")
            if product_id in duplicates or product_id not in by_id:
                raise ValueError(f"Produit catalogue introuvable ou ambigu : ligne {index + 1}")
            try:
                qty = int(item.get("qty") or item.get("quantity") or 1)
            except (TypeError, ValueError):
                qty = 0
            if qty < 1 or qty > 99:
                raise ValueError(f"Quantité invalide : ligne {index + 1}")
            selected = item.get("options") if isinstance(item.get("options"), list) else []
            unit = _canonical_price(by_id[product_id], selected)
            line_total = (unit * qty).quantize(Decimal("0.01"))
            total += line_total
            lines.append({
                "product_id": product_id,
                "name": str(by_id[product_id].get("name") or item.get("name") or "Produit")[:120],
                "qty": qty,
                "unit": unit,
                "line_total": line_total,
            })
        return lines, total.quantize(Decimal("0.01"))

    @app.get("/api/public/site-payment/stripe/status")
    def site_stripe_status_phase7():
        key = stripe_key()
        base = site_url()
        return jsonify({
            "ok": True,
            "phase": "7.1",
            "provider": "stripe",
            "configured": bool(key and base),
            "test_mode": key.startswith("sk_test_"),
            "site_url_configured": bool(base),
            "creates_order": False,
            "sends_kitchen": False,
            "webhook_validated": False,
        })

    @app.post("/api/public/site-payment/stripe/checkout-session")
    def site_stripe_checkout_session_phase7():
        key = stripe_key()
        base = site_url()
        if not key:
            return jsonify({"ok": False, "error": "STRIPE_SECRET_KEY manquant"}), 503
        if not key.startswith("sk_test_"):
            return jsonify({"ok": False, "error": "Phase 7.1 limitée à une clé Stripe de test"}), 409
        if not base:
            return jsonify({"ok": False, "error": "SITE_PUBLIC_URL manquant"}), 503

        payload = request.get_json(silent=True) or {}
        try:
            lines, total = canonical_lines(payload)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        except Exception as exc:
            return jsonify({"ok": False, "error": "Calcul du panier impossible", "detail": str(exc)}), 503

        form = [
            ("mode", "payment"),
            ("payment_method_types[0]", "card"),
            ("success_url", base + "/?payment=success&session_id={CHECKOUT_SESSION_ID}"),
            ("cancel_url", base + "/?payment=cancelled"),
            ("client_reference_id", "site-" + uuid.uuid4().hex),
            ("metadata[source]", "BECHEFAA-SITE"),
            ("metadata[expected_total_cents]", str(int(total * 100))),
        ]
        email = str((payload.get("customer") or {}).get("email") or "").strip()
        if email:
            form.append(("customer_email", email[:200]))

        for i, line in enumerate(lines):
            form.extend([
                (f"line_items[{i}][price_data][currency]", "eur"),
                (f"line_items[{i}][price_data][product_data][name]", line["name"]),
                (f"line_items[{i}][price_data][unit_amount]", str(int(line["unit"] * 100))),
                (f"line_items[{i}][quantity]", str(line["qty"])),
            ])

        req = Request(
            "https://api.stripe.com/v1/checkout/sessions",
            data=urlencode(form).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + key,
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "BECHEFAA-Caisse/Phase7.1",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8"))
                message = ((detail.get("error") or {}).get("message") or "Erreur Stripe")
            except Exception:
                message = "Erreur Stripe"
            return jsonify({"ok": False, "error": message}), 502
        except Exception as exc:
            return jsonify({"ok": False, "error": "Stripe indisponible", "detail": str(exc)}), 502

        session_id = str(data.get("id") or "")
        checkout_url = str(data.get("url") or "")
        if not session_id or not checkout_url:
            return jsonify({"ok": False, "error": "Réponse Stripe incomplète"}), 502

        return jsonify({
            "ok": True,
            "phase": "7.1",
            "provider": "stripe",
            "test_mode": True,
            "session_id": session_id,
            "checkout_url": checkout_url,
            "amount": float(total),
            "currency": "EUR",
            "creates_order": False,
            "sends_kitchen": False,
        })
