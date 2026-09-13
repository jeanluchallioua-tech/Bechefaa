"""Phase 2.6 — verrouillage serveur des prix lors de la création d'une commande.

Le navigateur peut proposer un unit_price, mais le serveur recalcule le prix canonique
à partir de catalog_admin_v2 (prix produit + options sélectionnées). Une ligne dont le prix
reçu diffère du prix catalogue est refusée avant tout INSERT.

Phase 7 : ajoute un devis public en lecture seule pour préparer le paiement Site.
Phase 7.1 : prépare Stripe Checkout en mode test uniquement, sans créer de commande
et sans envoyer quoi que ce soit en cuisine.
"""
import json
import os
import uuid
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import jsonify, request


def _money(value):
    try:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Prix invalide")


def _group_name(group, index):
    if not isinstance(group, dict):
        return "Groupe " + str(index + 1)
    return str(
        group.get("name")
        or group.get("label")
        or group.get("title")
        or ("Groupe " + str(index + 1))
    ).strip()


def _values(group):
    if not isinstance(group, dict):
        return []
    for key in ("options", "values", "items", "choices"):
        if isinstance(group.get(key), list):
            return group[key]
    return []


def _choice(value):
    if isinstance(value, (list, tuple)):
        name = str(value[0] if value else "").strip()
        price = _money(value[1] if len(value) > 1 else 0)
        return name, price
    if isinstance(value, dict):
        name = str(
            value.get("name")
            or value.get("label")
            or value.get("title")
            or value.get("value")
            or value.get("id")
            or ""
        ).strip()
        price = _money(
            value.get("price")
            or value.get("extraPrice")
            or value.get("supplement")
            or 0
        )
        return name, price
    return str(value or "").strip(), Decimal("0.00")


def _canonical_price(product, selected_options):
    if product.get("active", True) is False:
        raise ValueError("Produit inactif")

    base = _money(product.get("price", 0))
    groups = product.get("options") if isinstance(product.get("options"), list) else []
    used = {}
    extra = Decimal("0.00")

    for selected in selected_options:
        if not isinstance(selected, dict):
            raise ValueError("Option sélectionnée invalide")
        group_name = str(selected.get("group") or "").strip()
        option_name = str(selected.get("name") or selected.get("label") or "").strip()
        if not group_name or not option_name:
            raise ValueError("Option sélectionnée incomplète")

        matching_groups = [
            (index, group)
            for index, group in enumerate(groups)
            if _group_name(group, index) == group_name
        ]
        if len(matching_groups) != 1:
            raise ValueError("Groupe option introuvable ou ambigu : " + group_name)

        group_index, group = matching_groups[0]
        matching_choices = []
        for raw_choice in _values(group):
            name, price = _choice(raw_choice)
            if name == option_name:
                matching_choices.append((name, price))
        if len(matching_choices) != 1:
            raise ValueError(
                "Choix introuvable ou ambigu : " + group_name + " / " + option_name
            )

        used[group_index] = used.get(group_index, 0) + 1
        extra += matching_choices[0][1]

    for group_index, group in enumerate(groups):
        if not isinstance(group, dict):
            continue
        count = used.get(group_index, 0)
        required = bool(group.get("required", False))
        try:
            maximum = int(
                group.get("max")
                or group.get("maxChoices")
                or group.get("maximum")
                or 0
            )
        except (ValueError, TypeError):
            raise ValueError("Règle d'option invalide : " + _group_name(group, group_index))
        if required and count < 1:
            raise ValueError("Option obligatoire manquante : " + _group_name(group, group_index))
        if maximum > 0 and count > maximum:
            raise ValueError("Trop de choix pour : " + _group_name(group, group_index))

    return (base + extra).quantize(Decimal("0.01"))


def _catalog_products(db):
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


def _quote_lines(db, payload):
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Panier vide")

    by_id, duplicates = _catalog_products(db)
    total = Decimal("0.00")
    lines = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError("Ligne panier invalide : " + str(index + 1))

        product_id = str(item.get("id") or item.get("product_id") or "").strip()
        if not product_id:
            raise ValueError("Produit sans identifiant catalogue : ligne " + str(index + 1))
        if product_id in duplicates or product_id not in by_id:
            raise ValueError("Produit catalogue introuvable ou ambigu : ligne " + str(index + 1))

        try:
            qty = int(item.get("qty") or item.get("quantity") or 1)
        except (TypeError, ValueError):
            qty = 0
        if qty < 1 or qty > 99:
            raise ValueError("Quantité invalide : ligne " + str(index + 1))

        selected = item.get("options") if isinstance(item.get("options"), list) else []
        unit = _canonical_price(by_id[product_id], selected)
        line_total = (unit * qty).quantize(Decimal("0.01"))
        total += line_total
        lines.append({
            "productId": product_id,
            "name": by_id[product_id].get("name") or item.get("name") or "Produit",
            "qty": qty,
            "unitPrice": float(unit),
            "unitDecimal": unit,
            "lineTotal": float(line_total),
        })

    return lines, total.quantize(Decimal("0.01"))


def register_order_price_guard_phase26(app, db):
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
        try:
            lines, total = _quote_lines(db, payload)
            return jsonify({
                "ok": True,
                "readOnly": True,
                "currency": "EUR",
                "items": [
                    {
                        "productId": x["productId"],
                        "name": x["name"],
                        "qty": x["qty"],
                        "unitPrice": x["unitPrice"],
                        "lineTotal": x["lineTotal"],
                    }
                    for x in lines
                ],
                "total": float(total),
                "createsOrder": False,
                "sendsKitchen": False,
                "chargesCard": False,
            })
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        except Exception as exc:
            return jsonify({"ok": False, "error": "Calcul du panier impossible", "detail": str(exc)}), 503

    @app.get("/api/public/site-payment/stripe/status")
    def site_stripe_status_phase71():
        key = str(os.getenv("STRIPE_SECRET_KEY") or "").strip()
        base = str(os.getenv("SITE_PUBLIC_URL") or "").strip().rstrip("/")
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
    def site_stripe_checkout_session_phase71():
        key = str(os.getenv("STRIPE_SECRET_KEY") or "").strip()
        base = str(os.getenv("SITE_PUBLIC_URL") or "").strip().rstrip("/")
        if not key:
            return jsonify({"ok": False, "error": "STRIPE_SECRET_KEY manquant"}), 503
        if not key.startswith("sk_test_"):
            return jsonify({"ok": False, "error": "Phase 7.1 limitée à une clé Stripe de test"}), 409
        if not base:
            return jsonify({"ok": False, "error": "SITE_PUBLIC_URL manquant"}), 503

        payload = request.get_json(silent=True) or {}
        try:
            lines, total = _quote_lines(db, payload)
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

        customer = payload.get("customer") if isinstance(payload.get("customer"), dict) else {}
        email = str(customer.get("email") or "").strip()
        if email:
            form.append(("customer_email", email[:200]))

        for i, line in enumerate(lines):
            form.extend([
                (f"line_items[{i}][price_data][currency]", "eur"),
                (f"line_items[{i}][price_data][product_data][name]", str(line["name"])[:120]),
                (f"line_items[{i}][price_data][unit_amount]", str(int(line["unitDecimal"] * 100))),
                (f"line_items[{i}][quantity]", str(line["qty"])),
            ])

        stripe_request = Request(
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
            with urlopen(stripe_request, timeout=20) as response:
                stripe_data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8"))
                message = ((detail.get("error") or {}).get("message") or "Erreur Stripe")
            except Exception:
                message = "Erreur Stripe"
            return jsonify({"ok": False, "error": message}), 502
        except Exception as exc:
            return jsonify({"ok": False, "error": "Stripe indisponible", "detail": str(exc)}), 502

        session_id = str(stripe_data.get("id") or "")
        checkout_url = str(stripe_data.get("url") or "")
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

    @app.before_request
    def order_price_guard_phase26():
        # Portée volontairement limitée à la création initiale d'une commande.
        if request.method != "POST" or request.path != "/api/orders":
            return None

        payload = request.get_json(silent=True) or {}
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            return None  # create_order garde ses validations historiques.

        try:
            by_id, duplicates = _catalog_products(db)

            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    continue  # create_order produira son erreur habituelle.
                product_id = str(item.get("product_id") or "").strip()
                if not product_id:
                    return jsonify({
                        "ok": False,
                        "error": "Produit sans identifiant catalogue",
                        "line": index + 1,
                    }), 409
                if product_id in duplicates or product_id not in by_id:
                    return jsonify({
                        "ok": False,
                        "error": "Produit catalogue introuvable ou ambigu",
                        "productId": product_id,
                        "line": index + 1,
                    }), 409

                selected = item.get("options") if isinstance(item.get("options"), list) else []
                canonical = _canonical_price(by_id[product_id], selected)
                received = _money(item.get("unit_price", 0))
                if canonical != received:
                    return jsonify({
                        "ok": False,
                        "error": "Prix de commande différent du catalogue",
                        "productId": product_id,
                        "product": by_id[product_id].get("name") or item.get("name") or "",
                        "receivedPrice": float(received),
                        "serverPrice": float(canonical),
                        "line": index + 1,
                    }), 409

        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        except Exception as exc:
            return jsonify({
                "ok": False,
                "error": "Validation serveur du prix impossible",
                "detail": str(exc),
            }), 503

        return None
