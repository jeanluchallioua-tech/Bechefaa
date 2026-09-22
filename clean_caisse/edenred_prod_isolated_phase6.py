"""Phase 6 — intégration Edenred EDPS PROD isolée.

Le module reste inactif tant que BECHEFAA_EDENRED_PROD_ENABLED n'est pas activé.
Il utilise exclusivement les identifiants PROD et les endpoints PROD.
Les secrets et tokens ne sont jamais renvoyés au navigateur.
"""
import json
import os
import secrets
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from flask import jsonify, redirect, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from clean_caisse.edenred_uat_isolated_phase6 import (
    _extract_balance,
    _money,
    _record_edenred_order_payment,
    _send_order_to_kitchen,
)
from clean_caisse.mollie_payments_isolated_phase6 import create_mollie_payment_for_order
from clean_caisse.payment_core_phase41 import _ensure_payment_schema

AUTH_BASE_DEFAULT = "https://sso.eu.edenred.io"
PAYMENT_BASE_DEFAULT = "https://directpayment.eu.edenred.io/v2"
STATE_SALT = "bechefaa-edenred-state-phase6-prod-v1"
STATE_PREFIX = "prod."


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


def _serializer(c):
    return URLSafeTimedSerializer(c["auth_client_secret"], salt=STATE_SALT)


def _authorize_url(c, order_id):
    nonce = secrets.token_urlsafe(24)
    payload = {
        "nonce": nonce,
        "rnd": secrets.token_urlsafe(12),
        "action": "site_order_prod",
        "order_id": str(order_id),
    }
    state = STATE_PREFIX + _serializer(c).dumps(payload)
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
            "User-Agent": "BECHEFAA-EDENRED-PROD",
        },
        method="POST",
    )
    with urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def _get_json(url, headers, timeout=20):
    req = Request(
        url,
        headers={**headers, "Accept": "application/json", "User-Agent": "BECHEFAA-EDENRED-PROD"},
        method="GET",
    )
    with urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def _post_json(url, payload, headers, timeout=20):
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            **headers,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "BECHEFAA-EDENRED-PROD",
        },
        method="POST",
    )
    with urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def _provider_error(stage, exc):
    status = getattr(exc, "code", None)
    provider_code = None
    provider_message = None
    if isinstance(exc, HTTPError):
        try:
            raw = exc.read().decode("utf-8", errors="replace")
            body = json.loads(raw) if raw else {}
            if isinstance(body, dict):
                provider_code = body.get("code") or body.get("error") or body.get("status")
                provider_message = body.get("message") or body.get("error_description")
                meta = body.get("meta")
                if isinstance(meta, dict):
                    provider_code = provider_code or meta.get("code") or meta.get("status")
                    messages = meta.get("messages")
                    if not provider_message and isinstance(messages, list) and messages:
                        first = messages[0]
                        if isinstance(first, dict):
                            provider_message = first.get("message") or first.get("description") or first.get("code")
                        elif isinstance(first, str):
                            provider_message = first
        except Exception:
            pass
    return jsonify({
        "ok": False,
        "provider": "EDENRED_EDPS",
        "environment": "PROD",
        "stage": stage,
        "http_status": status,
        "provider_code": provider_code,
        "provider_message": provider_message,
        "error": "Edenred a refusé ou interrompu cette étape.",
        "secrets_exposed": False,
    }), 502


def register_edenred_prod_isolated_phase6(app, db=None, ensure_order_schema=None):
    @app.after_request
    def edenred_prod_cors_phase6(response):
        if request.path == "/api/edenred-prod/status-phase6":
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            response.headers["Cache-Control"] = "no-store"
        return response

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
            "payment_routes_registered": True,
            "payment_routes_enabled": _enabled(),
            "secrets_exposed": False,
        })

    @app.get("/api/edenred-prod/orders/<order_id>/start-phase6")
    def edenred_prod_order_start_phase6(order_id):
        c = _config()
        if not _enabled():
            return jsonify({"ok": False, "error": "Edenred PROD désactivé", "code": "EDENRED_PROD_DISABLED"}), 403
        if not _configured(c) or db is None or ensure_order_schema is None:
            return jsonify({"ok": False, "error": "Edenred PROD indisponible", "code": "EDENRED_PROD_NOT_READY"}), 503

        try:
            with db() as conn:
                _ensure_payment_schema(conn, ensure_order_schema)
                conn.commit()
                row = conn.execute(
                    "SELECT id,num,total,payment_status,source FROM caisse_orders WHERE id=%s",
                    (order_id,),
                ).fetchone()
            if not row:
                return jsonify({"ok": False, "error": "Commande introuvable"}), 404
            if str(row.get("payment_status") or "") == "PAYÉE":
                return jsonify({"ok": False, "error": "Commande déjà payée"}), 409
            if str(row.get("source") or "").upper() not in {"EMPORTER", "LIVRAISON", "SITE"}:
                return jsonify({"ok": False, "error": "Commande non éligible au paiement SITE Edenred"}), 409
        except Exception:
            return jsonify({"ok": False, "error": "Vérification de la commande impossible"}), 503

        return redirect(_authorize_url(c, order_id), code=302)

    @app.post("/api/edenred-prod/callback-phase6")
    def edenred_prod_callback_phase6():
        c = _config()
        if not _enabled() or not _configured(c):
            return jsonify({"ok": False, "error": "Edenred PROD indisponible", "code": "EDENRED_PROD_NOT_READY"}), 503

        provider_error = str(request.form.get("error") or "").strip()
        if provider_error:
            return jsonify({
                "ok": False,
                "provider": "EDENRED_EDPS",
                "environment": "PROD",
                "stage": "authorization",
                "error": provider_error,
                "secrets_exposed": False,
            }), 400

        code = str(request.form.get("code") or "").strip()
        state = str(request.form.get("state") or "").strip()
        if not code or not state or not state.startswith(STATE_PREFIX):
            return jsonify({"ok": False, "error": "Callback Edenred PROD incomplet", "code": "EDENRED_PROD_CALLBACK_INCOMPLETE"}), 400

        try:
            state_data = _serializer(c).loads(state[len(STATE_PREFIX):], max_age=600)
        except SignatureExpired:
            return jsonify({"ok": False, "error": "Connexion Edenred expirée. Recommencez le paiement.", "code": "EDENRED_PROD_STATE_EXPIRED"}), 400
        except BadSignature:
            return jsonify({"ok": False, "error": "État Edenred PROD invalide.", "code": "EDENRED_PROD_STATE_INVALID"}), 400

        if str(state_data.get("action") or "") != "site_order_prod":
            return jsonify({"ok": False, "error": "Action Edenred PROD invalide"}), 400

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
                "environment": "PROD",
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
                "environment": "PROD",
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

        amount, currency = _extract_balance(balance)
        order_id = str(state_data.get("order_id") or "").strip()
        if not order_id:
            return jsonify({"ok": False, "error": "Commande Edenred absente du state"}), 400
        if db is None or ensure_order_schema is None:
            return jsonify({"ok": False, "error": "Paiement commande Edenred indisponible"}), 503

        try:
            with db() as conn:
                _ensure_payment_schema(conn, ensure_order_schema)
                conn.commit()
                order = conn.execute(
                    "SELECT id,num,total,payment_status FROM caisse_orders WHERE id=%s",
                    (order_id,),
                ).fetchone()
            if not order:
                return jsonify({"ok": False, "error": "Commande introuvable"}), 404
            if str(order.get("payment_status") or "") == "PAYÉE":
                return jsonify({
                    "ok": True,
                    "provider": "EDENRED_EDPS",
                    "environment": "PROD",
                    "stage": "already_paid",
                    "order_id": order_id,
                    "order_num": order["num"],
                    "payment_status": "PAYÉE",
                    "transaction_created": False,
                    "secrets_exposed": False,
                })

            total_eur = _money(order["total"])
            order_amount_cents = int((total_eur * 100).to_integral_value())
            if not isinstance(amount, (int, float)) or int(amount) <= 0:
                return jsonify({
                    "ok": False,
                    "provider": "EDENRED_EDPS",
                    "environment": "PROD",
                    "stage": "pre_transaction",
                    "error": "Aucun solde Edenred disponible pour cette commande.",
                    "available_amount_cents": amount,
                    "order_amount_cents": order_amount_cents,
                    "transaction_created": False,
                    "secrets_exposed": False,
                }), 400

            edenred_amount_cents = min(int(amount), order_amount_cents)
            edenred_amount_eur = _money(edenred_amount_cents / 100)
            order_ref = "BCH-" + str(order["num"]) + "-" + str(order_id)[-8:].upper()
            tstamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            payment_payload = {
                "order_ref": order_ref,
                "mid": c["mid"],
                "amount": edenred_amount_cents,
                "capture_mode": "auto",
                "extra_field": order_ref,
                "tstamp": tstamp,
            }
            _, transaction = _post_json(
                c["payment_base"] + "/transactions",
                payment_payload,
                {
                    "Authorization": "Bearer " + access_token,
                    "X-Client-Id": c["payment_client_id"],
                    "X-Client-Secret": c["payment_client_secret"],
                },
            )
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            if isinstance(exc, ValueError):
                return jsonify({"ok": False, "error": str(exc), "stage": "transaction"}), 400
            return _provider_error("transaction", exc)
        except Exception:
            return jsonify({"ok": False, "error": "Paiement Edenred PROD impossible", "stage": "transaction"}), 502

        tx_data = transaction.get("data") if isinstance(transaction, dict) else {}
        tx_data = tx_data if isinstance(tx_data, dict) else {}
        tx_meta = transaction.get("meta") if isinstance(transaction, dict) else {}
        tx_meta = tx_meta if isinstance(tx_meta, dict) else {}
        captured_amount = tx_data.get("captured_amount")
        if captured_amount is None:
            captured_amount = tx_data.get("capture_amount")
        captured = (
            str(tx_meta.get("status") or "").lower() == "succeeded"
            and str(tx_data.get("status") or "").lower() == "captured"
            and int(captured_amount or 0) == edenred_amount_cents
        )
        if not captured:
            return jsonify({
                "ok": False,
                "provider": "EDENRED_EDPS",
                "environment": "PROD",
                "stage": "transaction",
                "transaction_status": tx_data.get("status"),
                "provider_status": tx_meta.get("status"),
                "captured_amount_cents": captured_amount,
                "order_amount_cents": order_amount_cents,
                "transaction_created": True,
                "payment_recorded": False,
                "secrets_exposed": False,
            }), 502

        external_reference = str(
            tx_data.get("capture_id")
            or tx_data.get("authorization_id")
            or tx_data.get("order_ref")
            or order_ref
        )
        try:
            with db() as conn:
                with conn.transaction():
                    recorded = _record_edenred_order_payment(
                        conn,
                        ensure_order_schema,
                        order_id,
                        edenred_amount_eur,
                        external_reference,
                        created_by="EDENRED_PROD",
                    )

            remaining_eur = _money(recorded.get("remaining_amount") or 0)
            kitchen = None
            next_payment = None
            if remaining_eur > 0:
                mollie_data = create_mollie_payment_for_order(
                    db, ensure_order_schema, order_id, test_mode=False
                )
                next_payment = {
                    "provider": "MOLLIE",
                    "mode": "LIVE",
                    "payment_id": mollie_data.get("payment_id"),
                    "checkout_url": mollie_data.get("checkout_url"),
                    "amount": mollie_data.get("amount"),
                }
            else:
                kitchen = _send_order_to_kitchen(app, order_id)
        except ValueError as exc:
            return jsonify({
                "ok": False,
                "provider": "EDENRED_EDPS",
                "environment": "PROD",
                "stage": "record_payment",
                "error": str(exc),
                "transaction_created": True,
                "payment_recorded": False,
                "secrets_exposed": False,
            }), 500
        except Exception as exc:
            return jsonify({
                "ok": False,
                "provider": "EDENRED_EDPS",
                "environment": "PROD",
                "stage": "mixed_payment",
                "error": "Paiement Edenred capturé mais finalisation locale à vérifier.",
                "detail": str(exc),
                "transaction_created": True,
                "payment_recorded": True,
                "secrets_exposed": False,
            }), 502

        return jsonify({
            "ok": True,
            "provider": "EDENRED_EDPS",
            "environment": "PROD",
            "stage": "completed",
            "order_id": order_id,
            "order_num": recorded.get("num"),
            "order_amount_cents": order_amount_cents,
            "available_amount_before_cents": amount,
            "edenred_amount_cents": edenred_amount_cents,
            "remaining_amount_eur": recorded.get("remaining_amount"),
            "currency": currency or "EUR",
            "transaction_created": True,
            "transaction_status": tx_data.get("status"),
            "provider_status": tx_meta.get("status"),
            "authorization_id_present": bool(tx_data.get("authorization_id")),
            "capture_id_present": bool(tx_data.get("capture_id")),
            "captured_amount_cents": captured_amount,
            "payment_recorded": True,
            "payment_status": recorded.get("payment_status"),
            "local_transaction_id": recorded.get("transaction_id"),
            "fiscal_ticket_number": recorded.get("fiscal_ticket_number"),
            "mixed_payment": next_payment is not None,
            "next_payment": next_payment,
            "kitchen": kitchen,
            "tokens_exposed": False,
            "secrets_exposed": False,
            "state_validated": True,
        })
