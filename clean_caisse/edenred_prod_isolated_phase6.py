"""Phase 6 — configuration Edenred EDPS PROD isolée.

Ce module prépare uniquement la configuration PROD et son diagnostic sûr.
Aucun paiement n'est exposé ici tant que la bascule PROD n'a pas été validée.
Les secrets ne sont jamais renvoyés au navigateur.
"""
import os
from flask import jsonify

AUTH_BASE_DEFAULT = "https://sso.eu.edenred.io"
PAYMENT_BASE_DEFAULT = "https://directpayment.eu.edenred.io/v2"


def _env(name, default=""):
    return str(os.getenv(name) or default).strip()


def _enabled():
    return _env("BECHEFAA_EDENRED_PROD_ENABLED").lower() in {"1", "true", "yes", "on"}


def _config():
    return {
        "auth_base": _env("EDENRED_PROD_AUTH_BASE_URL", AUTH_BASE_DEFAULT).rstrip("/"),
        "payment_base": _env("EDENRED_PROD_PAYMENT_BASE_URL", PAYMENT_BASE_DEFAULT).rstrip("/"),
        "mid": _env("EDENRED_MID_PROD"),
        "auth_client_id": _env("EDENRED_PROD_AUTH_CLIENT_ID"),
        "auth_client_secret": _env("EDENRED_PROD_AUTH_CLIENT_SECRET"),
        "payment_client_id": _env("EDENRED_PROD_PAYMENT_CLIENT_ID"),
        "payment_client_secret": _env("EDENRED_PROD_PAYMENT_CLIENT_SECRET"),
        "redirect_uri": _env("EDENRED_PROD_REDIRECT_URI", "https://www.bechefaa.fr/edenred/callback"),
        "logout_redirect_uri": _env("EDENRED_PROD_LOGOUT_REDIRECT_URI", "https://www.bechefaa.fr/"),
    }


def _presence(c):
    return {
        "mid": bool(c["mid"]),
        "auth_client_id": bool(c["auth_client_id"]),
        "auth_client_secret": bool(c["auth_client_secret"]),
        "payment_client_id": bool(c["payment_client_id"]),
        "payment_client_secret": bool(c["payment_client_secret"]),
        "redirect_uri": bool(c["redirect_uri"]),
        "logout_redirect_uri": bool(c["logout_redirect_uri"]),
    }


def _configured(c):
    return all(_presence(c).values())


def register_edenred_prod_isolated_phase6(app):
    @app.get("/api/edenred-prod/status-phase6")
    def edenred_prod_status_phase6():
        c = _config()
        presence = _presence(c)
        configured = all(presence.values())
        return jsonify({
            "ok": True,
            "provider": "EDENRED_EDPS",
            "environment": "PROD",
            "scope": "SITE_ONLY",
            "enabled": _enabled(),
            "configured": configured,
            "ready_for_prod": configured and _enabled(),
            "authentication_url": c["auth_base"],
            "payment_url": c["payment_base"],
            "redirect_uri": c["redirect_uri"],
            "logout_redirect_uri": c["logout_redirect_uri"],
            "credentials_present": presence,
            "payment_routes_exposed": False,
            "secrets_exposed": False,
        })
