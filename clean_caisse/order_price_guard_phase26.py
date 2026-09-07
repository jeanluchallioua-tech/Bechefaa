"""Phase 2.6 — verrouillage serveur des prix lors de la création d'une commande.

Le navigateur peut proposer un unit_price, mais le serveur recalcule le prix canonique
à partir de catalog_admin_v2 (prix produit + options sélectionnées). Une ligne dont le prix
reçu diffère du prix catalogue est refusée avant tout INSERT.
"""
import json
from decimal import Decimal, InvalidOperation

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


def register_order_price_guard_phase26(app, db):
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
