"""Phase 6 — commande SITE avant paiement Edenred EDPS PROD.

La route reste désactivée tant que BECHEFAA_EDENRED_PROD_ENABLED=false.
La commande est créée sans envoi cuisine ; l'envoi intervient après capture
Edenred confirmée côté serveur.
"""
from flask import jsonify, request

from clean_caisse.edenred_prod_isolated_phase6 import _enabled
from clean_caisse.site_orders_bridge_isolated_phase6 import (
    map_site_order_payload,
    _apply_server_catalog_prices,
    _dispatch_internal,
    _persist_site_service_mode,
    _persist_site_options_text,
)


def register_site_edenred_prod_checkout_isolated_phase6(app):
    @app.after_request
    def site_edenred_prod_checkout_cors_phase6(response):
        if request.path == "/api/public/orders/edenred-prod-phase6":
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/api/public/orders/edenred-prod-phase6", methods=["POST", "OPTIONS"])
    def site_edenred_order_prod_phase6():
        if request.method == "OPTIONS":
            return ("", 204)
        if not _enabled():
            return jsonify({
                "ok": False,
                "error": "Edenred PROD désactivé",
                "code": "EDENRED_PROD_DISABLED",
            }), 403

        external = request.get_json(silent=True) or {}
        internal, error = map_site_order_payload(external)
        if error:
            return jsonify({"ok": False, "error": error}), 400

        try:
            _apply_server_catalog_prices(internal)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        except Exception as exc:
            return jsonify({
                "ok": False,
                "error": "Calcul du prix catalogue impossible",
                "detail": str(exc),
            }), 503

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
            data["options_warning"] = "Affichage des options à vérifier : " + str(exc)

        data["ok"] = True
        data["status"] = data.get("status") or "Enregistrée"
        data["payment_provider"] = "EDENRED_EDPS"
        data["payment_environment"] = "PROD"
        data["payment_required"] = True
        data["kitchen_sent"] = False
        return jsonify(data), 201
