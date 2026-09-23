"""Phase 6 — passerelle isolée des commandes BÉCHÉFAA-Site.

Objectif : traduire le contrat HTTP du site vers le contrat propre de
``POST /api/orders`` sans écrire directement dans PostgreSQL pour la création.
Les garde-fous de la caisse (prix, livraison, client, canal de vente, fiscalité,
etc.) restent dans la chaîne normale.
"""

import re

from flask import jsonify, request
from clean_caisse.app import db
from clean_caisse.order_price_guard_phase26 import _canonical_price, _catalog_products


def _digits(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _normalize_mode(value):
    raw = str(value or "").strip().upper()
    if raw in {"LIVRAISON", "DELIVERY"}:
        return "LIVRAISON"
    return "À EMPORTER"


def _site_customer(raw):
    raw = raw if isinstance(raw, dict) else {}
    return {
        "first_name": str(raw.get("firstName") or raw.get("first_name") or "").strip(),
        "last_name": str(raw.get("lastName") or raw.get("last_name") or "").strip(),
        "phone": str(raw.get("phone") or "").strip(),
        "email": str(raw.get("email") or "").strip(),
        "address": str(raw.get("address") or "").strip(),
        "postal_code": str(raw.get("postalCode") or raw.get("postal_code") or "").strip(),
        "city": str(raw.get("city") or "").strip(),
    }


def _structured_options(item):
    """Conserve les options structurées du site sans les transformer en texte."""
    raw = item.get("options")
    if not isinstance(raw, list):
        return []

    options = []
    for selected in raw:
        if not isinstance(selected, dict):
            continue
        group = str(selected.get("group") or "").strip()
        name = str(selected.get("name") or selected.get("label") or "").strip()
        if not group or not name:
            continue
        option = {"group": group, "name": name}
        if selected.get("price") is not None:
            option["price"] = selected.get("price")
        options.append(option)
    return options


def map_site_order_payload(payload):
    """Valide et traduit une commande du site vers ``POST /api/orders``."""
    payload = payload if isinstance(payload, dict) else {}
    mode = _normalize_mode(payload.get("mode"))
    customer = _site_customer(payload.get("customer"))

    if not customer["first_name"] or not customer["last_name"]:
        return None, "Nom et prénom client obligatoires"
    if len(_digits(customer["phone"])) < 10:
        return None, "Téléphone client invalide"
    if customer["email"] and not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", customer["email"]):
        return None, "Email client invalide"

    if mode == "LIVRAISON":
        if not customer["address"] or not customer["city"]:
            return None, "Adresse de livraison incomplète"
        if not re.fullmatch(r"\d{5}", customer["postal_code"]):
            return None, "Code postal de livraison invalide"
    else:
        customer["address"] = ""
        customer["postal_code"] = ""
        customer["city"] = ""

    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        return None, "Panier vide"

    items = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            return None, "Ligne de commande invalide"
        name = str(item.get("name") or "").strip()
        if not name:
            return None, "Article sans nom"
        try:
            qty = int(item.get("qty") or 1)
            unit_price = float(item.get("price") if item.get("price") is not None else item.get("unit_price") or 0)
        except (TypeError, ValueError):
            return None, "Prix ou quantité invalide"
        if qty < 1 or unit_price < 0:
            return None, "Prix ou quantité invalide"

        line_id = str(item.get("cartId") or item.get("line_id") or f"site-line-{index}").strip()
        product_id = str(item.get("id") or item.get("product_id") or "").strip() or None
        options_text = str(item.get("optionsText") or item.get("options_text") or "").strip()
        items.append({
            "line_id": line_id,
            "product_id": product_id,
            "name": name,
            "qty": qty,
            "unit_price": unit_price,
            "options": _structured_options(item),
            # Conservé pour l'affichage Cuisine/Historiques des commandes SITE.
            # Les prix sont recalculés côté caisse avant création.
            "options_text": options_text,
        })

    internal = {
        "ticket_type": "livraison" if mode == "LIVRAISON" else "comptoir",
        "sales_channel": "SITE",
        "customer": customer,
        "items": items,
        "site_meta": {
            "slot": str(payload.get("slot") or "DÈS QUE POSSIBLE").strip(),
            "instructions": str((payload.get("customer") or {}).get("instructions") or "").strip()
                if isinstance(payload.get("customer"), dict) else "",
        },
    }
    return internal, None


def _apply_server_catalog_prices(internal):
    """Remplace les prix reçus du site par les prix canoniques du catalogue V2.

    Le site et la caisse lisent le même catalogue, mais la caisse reste autoritaire.
    On conserve donc le garde-fou Phase 2.6 sans accepter un montant fourni par le
    navigateur lorsque le serveur peut le recalculer lui-même.
    """
    by_id, duplicates = _catalog_products(db)
    for index, item in enumerate(internal.get("items") or []):
        product_id = str(item.get("product_id") or "").strip()
        if not product_id or product_id in duplicates or product_id not in by_id:
            raise ValueError("Produit catalogue introuvable ou ambigu : ligne " + str(index + 1))
        selected = item.get("options") if isinstance(item.get("options"), list) else []
        item["unit_price"] = float(_canonical_price(by_id[product_id], selected))


def _dispatch_internal(app, path, payload):
    """Passe volontairement par Flask pour conserver tous les wrappers actifs.

    Le marqueur WSGI ci-dessous est interne au processus : il permet aux ponts
    publics déjà validés de réutiliser /api/orders sans être bloqués par le PIN
    personnel de la caisse. Il n'est jamais exposé comme en-tête HTTP public.
    """
    with app.test_request_context(
        path,
        method="POST",
        json=payload,
        environ_overrides={"bechefaa.internal_dispatch": "1"},
    ):
        return app.full_dispatch_request()


def _persist_site_service_mode(order_id, internal):
    """Conserve explicitement le mode de service des commandes SITE.

    Le cœur historique de la caisse utilise une source générique pour tout ce qui
    n'est pas Livraison. Pour une commande SITE, on sait toutefois avec certitude
    qu'un mode non-livraison correspond à À emporter. On l'enregistre donc comme
    EMPORTER afin que tickets, Cuisine et Historique affichent tous le bon mode.
    """
    if str(internal.get("ticket_type") or "").lower() == "livraison":
        return
    with db() as conn:
        with conn.transaction():
            conn.execute(
                "UPDATE caisse_orders SET source=%s WHERE id=%s",
                ("EMPORTER", order_id),
            )


def _persist_site_options_text(order_id, items):
    """Écrit uniquement le libellé lisible déjà choisi sur le site.

    Cette étape ne touche ni options_json, ni les prix, ni le total, ni les règles
    du catalogue. Elle corrige seulement l'affichage Cuisine/Historique lorsque
    le mapping structuré d'une option V2 est incomplet.
    """
    rows = [
        (str(item.get("options_text") or "").strip(), str(item.get("line_id") or "").strip())
        for item in items
        if str(item.get("options_text") or "").strip() and str(item.get("line_id") or "").strip()
    ]
    if not rows:
        return
    with db() as conn:
        with conn.transaction():
            for text, line_id in rows:
                conn.execute(
                    "UPDATE caisse_order_items SET options_text=%s WHERE order_id=%s AND line_id=%s",
                    (text, order_id, line_id),
                )


def register_site_orders_bridge_isolated_phase6(app):
    @app.post("/api/public/orders")
    def site_public_order_phase6():
        external = request.get_json(silent=True) or {}
        internal, error = map_site_order_payload(external)
        if error:
            return jsonify({"ok": False, "error": error}), 400

        try:
            _apply_server_catalog_prices(internal)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        except Exception as exc:
            return jsonify({"ok": False, "error": "Calcul du prix catalogue impossible", "detail": str(exc)}), 503

        created = _dispatch_internal(app, "/api/orders", internal)
        if created.status_code < 200 or created.status_code >= 300:
            return created

        data = created.get_json(silent=True) or {}
        order_id = str(data.get("id") or "").strip()
        if not order_id:
            return jsonify({"ok": False, "error": "Commande créée sans identifiant"}), 500

        try:
            _persist_site_service_mode(order_id, internal)
        except Exception as exc:
            data["service_mode_warning"] = "Mode de service à vérifier : " + str(exc)

        try:
            _persist_site_options_text(order_id, internal.get("items") or [])
        except Exception as exc:
            # La commande reste valide : on signale uniquement l'affichage des options.
            data["options_warning"] = "Affichage des options à vérifier : " + str(exc)

        kitchen = _dispatch_internal(app, f"/api/orders/{order_id}/send-kitchen", {})
        kitchen_data = kitchen.get_json(silent=True) or {}

        if kitchen.status_code < 200 or kitchen.status_code >= 300:
            data["ok"] = True
            data["status"] = data.get("status") or "Enregistrée"
            data["kitchen_warning"] = kitchen_data.get("error") or "Envoi cuisine à vérifier"
            return jsonify(data), 201

        data["ok"] = True
        data["status"] = kitchen_data.get("status") or "À préparer"
        return jsonify(data), 201

    @app.post("/api/site-orders-phase6/map-test")
    def site_order_map_test_phase6():
        """Diagnostic pur : traduit le payload sans créer aucune commande."""
        internal, error = map_site_order_payload(request.get_json(silent=True) or {})
        if error:
            return jsonify({"ok": False, "error": error}), 400
        return jsonify({"ok": True, "internal": internal, "writes": False})
