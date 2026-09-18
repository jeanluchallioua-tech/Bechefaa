"""Phase 6 — intégration Edenred EDPS UAT isolée.

Cette étape permet de tester le parcours MyEdenred sans créer de transaction :
diagnostic, redirection OAuth, échange serveur du code, UserInfo et lecture du
solde. Aucun token ni secret n'est renvoyé au navigateur.
"""
import json
import os
import secrets
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from flask import jsonify, redirect, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

AUTH_BASE_DEFAULT = "https://sso.sbx.edenred.io"
PAYMENT_BASE_DEFAULT = "https://directpayment.stg.eu.edenred.io/v2"
STATE_SALT = "bechefaa-edenred-state-phase6-v1"


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


def _configured(c):
    return all((
        c["mid"],
        c["auth_client_id"],
        c["auth_client_secret"],
        c["payment_client_id"],
        c["payment_client_secret"],
        c["redirect_uri"],
        c["logout_redirect_uri"],
    ))


def _serializer(c):
    # Le secret d'authentification reste exclusivement côté serveur.
    return URLSafeTimedSerializer(c["auth_client_secret"], salt=STATE_SALT)


def _authorize_url(c):
    nonce = secrets.token_urlsafe(24)
    state = _serializer(c).dumps({
        "nonce": nonce,
        "rnd": secrets.token_urlsafe(12),
    })
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
    return c["auth_base"] + "/connect/authorize?" + urlencode(params)


def _form_json(url, form, timeout=20):
    req = Request(
        url,
        data=urlencode(form).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "BECHEFAA-EDENRED-UAT",
        },
        method="POST",
    )
    with urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def _get_json(url, headers, timeout=20):
    req = Request(
        url,
        headers={**headers, "Accept": "application/json", "User-Agent": "BECHEFAA-EDENRED-UAT"},
        method="GET",
    )
    with urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def _provider_error(stage, exc):
    status = getattr(exc, "code", None)
    return jsonify({
        "ok": False,
        "provider": "EDENRED_EDPS",
        "environment": "UAT",
        "stage": stage,
        "http_status": status,
        "error": "Edenred UAT a refusé ou interrompu cette étape.",
        "secrets_exposed": False,
    }), 502


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
            return jsonify({"ok": False, "error": "Edenred SITE désactivé", "code": "EDENRED_DISABLED"}), 403
        if not _configured(c):
            return jsonify({"ok": False, "error": "Configuration Edenred UAT incomplète", "code": "EDENRED_CONFIG_INCOMPLETE"}), 503
        return jsonify({
            "ok": True,
            "provider": "EDENRED_EDPS",
            "environment": "UAT",
            "authorize_url": _authorize_url(c),
            "writes": False,
            "tokens_exposed": False,
        })

    @app.get("/api/edenred/start-phase6")
    def edenred_start_phase6():
        c = _config()
        if not _enabled():
            return jsonify({"ok": False, "error": "Edenred SITE désactivé", "code": "EDENRED_DISABLED"}), 403
        if not _configured(c):
            return jsonify({"ok": False, "error": "Configuration Edenred UAT incomplète", "code": "EDENRED_CONFIG_INCOMPLETE"}), 503
        return redirect(_authorize_url(c), code=302)

    @app.post("/api/edenred/callback-phase6")
    def edenred_callback_phase6():
        c = _config()
        if not _enabled() or not _configured(c):
            return jsonify({"ok": False, "error": "Edenred UAT indisponible", "code": "EDENRED_NOT_READY"}), 503

        provider_error = str(request.form.get("error") or "").strip()
        if provider_error:
            return jsonify({
                "ok": False,
                "provider": "EDENRED_EDPS",
                "environment": "UAT",
                "stage": "authorization",
                "error": provider_error,
                "secrets_exposed": False,
            }), 400

        code = str(request.form.get("code") or "").strip()
        state = str(request.form.get("state") or "").strip()
        if not code or not state:
            return jsonify({"ok": False, "error": "Callback Edenred incomplet", "code": "EDENRED_CALLBACK_INCOMPLETE"}), 400

        try:
            state_data = _serializer(c).loads(state, max_age=600)
        except SignatureExpired:
            return jsonify({"ok": False, "error": "Connexion Edenred expirée. Recommencez le test.", "code": "EDENRED_STATE_EXPIRED"}), 400
        except BadSignature:
            return jsonify({"ok": False, "error": "État Edenred invalide.", "code": "EDENRED_STATE_INVALID"}), 400

        try:
            _, token = _form_json(c["auth_base"] + "/connect/token", {
                "client_id": c["auth_client_id"],
                "client_secret": c["auth_client_secret"],
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": c["redirect_uri"],
            })
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            return _provider_error("token", exc)

        access_token = str(token.get("access_token") or "").strip()
        if not access_token:
            return jsonify({
                "ok": False,
                "provider": "EDENRED_EDPS",
                "environment": "UAT",
                "stage": "token",
                "error": "Aucun access_token reçu.",
                "secrets_exposed": False,
            }), 502

        try:
            _, userinfo = _get_json(
                c["auth_base"] + "/connect/userinfo",
                {"Authorization": "Bearer " + access_token},
            )
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            return _provider_error("userinfo", exc)

        username = str(userinfo.get("username") or "").strip()
        if not username:
            sub = str(userinfo.get("sub") or "").strip()
            username = sub.split("\\", 1)[-1] if "\\" in sub else sub
        if not username:
            return jsonify({
                "ok": False,
                "provider": "EDENRED_EDPS",
                "environment": "UAT",
                "stage": "userinfo",
                "error": "Username Edenred introuvable.",
                "secrets_exposed": False,
            }), 502

        try:
            _, balance = _get_json(
                c["payment_base"] + "/users/" + quote(username, safe="") + "/balances",
                {
                    "Authorization": "Bearer " + access_token,
                    "X-Client-Id": c["payment_client_id"],
                    "X-Client-Secret": c["payment_client_secret"],
                },
            )
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            return _provider_error("balance", exc)

        data = balance.get("data") if isinstance(balance, dict) else {}
        data = data if isinstance(data, dict) else {}
        amount = data.get("available_amount")
        currency = data.get("currency")
        return jsonify({
            "ok": True,
            "provider": "EDENRED_EDPS",
            "environment": "UAT",
            "stage": "balance",
            "authentication": "succeeded",
            "token_exchange": "succeeded",
            "userinfo": "succeeded",
            "balance_read": "succeeded",
            "username_present": True,
            "available_amount_cents": amount,
            "available_amount_eur": (amount / 100.0) if isinstance(amount, (int, float)) else None,
            "currency": currency,
            "transaction_created": False,
            "tokens_exposed": False,
            "secrets_exposed": False,
            "state_validated": bool(state_data),
        })
