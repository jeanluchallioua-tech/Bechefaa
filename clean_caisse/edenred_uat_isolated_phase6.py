"""Phase 6 — socle Edenred EDPS UAT, désactivé par défaut.

Aucun secret n'est exposé. Cette première étape vérifie uniquement la présence
de la configuration Clever et prépare le parcours OAuth MyEdenred UAT.
"""
import os
import secrets
from urllib.parse import urlencode

from flask import jsonify, request

AUTH_BASE_DEFAULT = "https://sso.sbx.edenred.io"
PAYMENT_BASE_DEFAULT = "https://directpayment.stg.eu.edenred.io/v2"


def _env(name, default=""):
    return str(os.getenv(name) or default).strip()


def _enabled():
    return _env("BECHEFAA_EDENRED_ENABLED").lower() in {"1", "true", "yes", "on"}


def _config():
    return {
        "auth_base": _env("EDENRED_AUTH_BASE_URL", AUTH_BASE_DEFAULT).rstrip("/"),
        "payment_base": _env("EDENRED_PAYMENT_BASE_URL", PAYMENT_BASE_DEFAULT).rstrip("/"),
        "mid": _env("EDENRED_MID_UAT"),
        "auth_client_id": _env("EDENRED_AUTH_CLIENT_ID"),
        "auth_client_secret": _env("EDENRED_AUTH_CLIENT_SECRET"),
        "payment_client_id": _env("EDENRED_PAYMENT_CLIENT_ID"),
        "payment_client_secret": _env("EDENRED_PAYMENT_CLIENT_SECRET"),
        "redirect_uri": _env("EDENRED_REDIRECT_URI"),
        "logout_redirect_uri": _env("EDENRED_LOGOUT_REDIRECT_URI"),
    }


def register_edenred_uat_isolated_phase6(app):
    @app.get("/api/edenred/status-phase6")
    def edenred_status_phase6():
        c = _config()
        presence = {
            "mid": bool(c["mid"]),
            "auth_client_id": bool(c["auth_client_id"]),
            "auth_client_secret": bool(c["auth_client_secret"]),
            "payment_client_id": bool(c["payment_client_id"]),
            "payment_client_secret": bool(c["payment_client_secret"]),
            "redirect_uri": bool(c["redirect_uri"]),
            "logout_redirect_uri": bool(c["logout_redirect_uri"]),
        }
        configured = all(presence.values())
        return jsonify({
            "ok": True,
            "provider": "EDENRED_EDPS",
            "environment": "UAT",
            "scope": "SITE_ONLY",
            "enabled": _enabled(),
            "configured": configured,
            "ready_for_uat": configured and _enabled(),
            "authentication_url": c["auth_base"],
            "payment_url": c["payment_base"],
            "credentials_present": presence,
            "secrets_exposed": False,
        })

    @app.get("/api/edenred/authorize-url-phase6")
    def edenred_authorize_url_phase6():
        c = _config()
        if not _enabled():
            return jsonify({
                "ok": False,
                "error": "Edenred SITE désactivé",
                "code": "EDENRED_DISABLED",
            }), 403
        required = (
            c["auth_client_id"],
            c["auth_client_secret"],
            c["payment_client_id"],
            c["payment_client_secret"],
            c["mid"],
            c["redirect_uri"],
        )
        if not all(required):
            return jsonify({
                "ok": False,
                "error": "Configuration Edenred UAT incomplète",
                "code": "EDENRED_CONFIG_INCOMPLETE",
            }), 503

        state = secrets.token_urlsafe(24)
        nonce = secrets.token_urlsafe(24)
        params = {
            "response_type": "code",
            "client_id": c["auth_client_id"],
            "scope": "openid edg-xp-mealdelivery-api offline_access",
            "redirect_uri": c["redirect_uri"],
            "state": state,
            "nonce": nonce,
            "acr_values": "tenant:fr-ctrtku",
            "ui_locales": "fr",
        }
        return jsonify({
            "ok": True,
            "provider": "EDENRED_EDPS",
            "environment": "UAT",
            "authorize_url": c["auth_base"] + "/connect/authorize?" + urlencode(params),
            "state": state,
            "nonce": nonce,
            "writes": False,
        })

    @app.get("/edenred/callback")
    def edenred_callback_placeholder_phase6():
        code_present = bool(str(request.args.get("code") or "").strip())
        error = str(request.args.get("error") or "").strip()
        return jsonify({
            "ok": bool(code_present and not error),
            "provider": "EDENRED_EDPS",
            "environment": "UAT",
            "code_present": code_present,
            "error": error or None,
            "token_exchange_implemented": False,
            "message": "Callback Edenred reçu. Échange du code volontairement non activé à cette étape.",
        })

    @app.get("/edenred/logout-callback")
    def edenred_logout_callback_phase6():
        return jsonify({
            "ok": True,
            "provider": "EDENRED_EDPS",
            "environment": "UAT",
            "logged_out_callback": True,
        })
