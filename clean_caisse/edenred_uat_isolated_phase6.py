"""Phase 6 — intégration Edenred EDPS UAT isolée.

Cette étape permet de tester le parcours MyEdenred sans créer de transaction :
diagnostic, redirection OAuth, échange serveur du code, UserInfo et lecture du
solde. Aucun token ni secret n'est renvoyé au navigateur.
"""
import json
import os
import secrets
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from flask import jsonify, redirect, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from clean_caisse.fiscal_ticket_phase44 import allocate_fiscal_ticket_number
from clean_caisse.payment_core_phase41 import _ensure_payment_schema
from clean_caisse.payment_transactions_phase44 import (
    ensure_payment_transaction_schema,
    record_payment_transaction,
)
from clean_caisse.mollie_payments_isolated_phase6 import create_mollie_payment_for_order

AUTH_BASE_DEFAULT = "https://sso.sbx.edenred.io"
PAYMENT_BASE_DEFAULT = "https://directpayment.stg.eu.edenred.io/v2"
STATE_SALT = "bechefaa-edenred-state-phase6-v1"
CENT = Decimal("0.01")


def _money(value):
    try:
        return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Montant invalide")


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


def _authorize_url(c, action="balance", state_extra=None):
    nonce = secrets.token_urlsafe(24)
    state_payload = {
        "nonce": nonce,
        "rnd": secrets.token_urlsafe(12),
        "action": action,
    }
    if isinstance(state_extra, dict):
        state_payload.update({str(k): v for k, v in state_extra.items()})
    state = _serializer(c).dumps(state_payload)
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


def _post_json(url, payload, headers, timeout=20):
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            **headers,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "BECHEFAA-EDENRED-UAT",
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
            provider_code = None
            provider_message = None
    return jsonify({
        "ok": False,
        "provider": "EDENRED_EDPS",
        "environment": "UAT",
        "stage": stage,
        "http_status": status,
        "provider_code": provider_code,
        "provider_message": provider_message,
        "error": "Edenred UAT a refusé ou interrompu cette étape.",
        "secrets_exposed": False,
    }), 502


def _safe_shape(value, depth=0):
    """Retourne uniquement la structure d'une réponse JSON, jamais les valeurs sensibles."""
    if depth > 3:
        return type(value).__name__
    if isinstance(value, dict):
        return {str(k): _safe_shape(v, depth + 1) for k, v in list(value.items())[:30]}
    if isinstance(value, list):
        sample = [_safe_shape(v, depth + 1) for v in value[:3]]
        return {"type": "list", "length": len(value), "sample": sample}
    if value is None:
        return "null"
    return type(value).__name__


def _extract_balance(balance):
    """Tolère plusieurs formes de réponse Edenred EDPS UAT."""
    if not isinstance(balance, dict):
        return None, None

    candidates = []
    candidates.append(balance)
    data = balance.get("data")
    if isinstance(data, dict):
        candidates.append(data)
    elif isinstance(data, list):
        candidates.extend(x for x in data if isinstance(x, dict))

    for key in ("balances", "wallets", "accounts", "products"):
        value = balance.get(key)
        if isinstance(value, dict):
            candidates.append(value)
        elif isinstance(value, list):
            candidates.extend(x for x in value if isinstance(x, dict))
        if isinstance(data, dict):
            value = data.get(key)
            if isinstance(value, dict):
                candidates.append(value)
            elif isinstance(value, list):
                candidates.extend(x for x in value if isinstance(x, dict))

    amount_keys = (
        "available_amount", "availableAmount", "available_balance", "availableBalance",
        "balance", "amount", "value", "available",
    )
    currency_keys = ("currency", "currency_code", "currencyCode")

    for obj in candidates:
        if not isinstance(obj, dict):
            continue
        amount = None
        currency = None
        for k in amount_keys:
            v = obj.get(k)
            if isinstance(v, (int, float)):
                amount = v
                break
            if isinstance(v, dict):
                for nk in ("amount", "value", "minor_units", "minorUnits"):
                    nv = v.get(nk)
                    if isinstance(nv, (int, float)):
                        amount = nv
                        break
                if amount is not None:
                    for ck in currency_keys:
                        cv = v.get(ck)
                        if isinstance(cv, str) and cv.strip():
                            currency = cv.strip()
                            break
                    break
        if amount is None:
            continue
        if not currency:
            for ck in currency_keys:
                cv = obj.get(ck)
                if isinstance(cv, str) and cv.strip():
                    currency = cv.strip()
                    break
        return amount, currency

    return None, None


def _send_order_to_kitchen(app, order_id):
    with app.test_request_context(
        f"/api/orders/{order_id}/send-kitchen",
        method="POST",
        json={},
    ):
        response = app.full_dispatch_request()
    data = response.get_json(silent=True) or {}
    return {
        "ok": 200 <= response.status_code < 300,
        "status_code": response.status_code,
        "status": data.get("status"),
        "error": data.get("error"),
    }


def _record_edenred_order_payment(conn, ensure_order_schema, order_id, amount_eur, external_reference):
    """Enregistre Edenred sans forcer le paiement total.

    Permet le paiement mixte : Edenred couvre tout ou partie, puis le solde
    éventuel peut être payé par Mollie. Le ticket fiscal n'est alloué qu'une
    fois le total intégralement encaissé.
    """
    _ensure_payment_schema(conn, ensure_order_schema)
    ensure_payment_transaction_schema(conn)

    row = conn.execute(
        "SELECT id,num,total,payment_status FROM caisse_orders WHERE id=%s FOR UPDATE",
        (order_id,),
    ).fetchone()
    if not row:
        raise ValueError("Commande BÉCHÉFAA introuvable")

    total = _money(row["total"])
    paid_row = conn.execute("""
        SELECT COALESCE(SUM(CASE
            WHEN transaction_type='PAYMENT' AND status='SUCCEEDED' THEN amount
            WHEN transaction_type='REFUND' AND status='SUCCEEDED' THEN -amount
            ELSE 0 END),0) AS net
        FROM caisse_payment_transactions
        WHERE order_id=%s
    """, (order_id,)).fetchone()
    before = _money(paid_row["net"] if paid_row else 0)
    remaining_before = max(Decimal("0.00"), total - before)

    existing = conn.execute("""
        SELECT id,amount FROM caisse_payment_transactions
        WHERE order_id=%s AND provider='EDENRED_EDPS'
          AND transaction_type='PAYMENT' AND status='SUCCEEDED'
          AND external_reference=%s
        LIMIT 1
    """, (order_id, external_reference)).fetchone()
    if existing:
        after = min(total, before)
        remaining = max(Decimal("0.00"), total - after)
        return {
            "duplicate": True,
            "order_id": order_id,
            "num": row["num"],
            "payment_status": "PAYÉE" if remaining <= 0 else "PARTIELLEMENT PAYÉE",
            "transaction_id": existing["id"],
            "paid_total": float(after),
            "remaining_amount": float(remaining),
            "fiscal_ticket_number": None,
        }

    amount = _money(amount_eur)
    if amount <= 0:
        raise ValueError("Montant Edenred invalide")
    if amount > remaining_before:
        raise ValueError("Le paiement Edenred dépasse le solde de la commande")

    tx_id = record_payment_transaction(
        conn,
        order_id,
        "TITRE RESTAURANT",
        amount,
        provider="EDENRED_EDPS",
        external_reference=external_reference,
        created_by="EDENRED_UAT",
    )

    now = int(time.time() * 1000)
    paid_total = (before + amount).quantize(CENT)
    remaining = max(Decimal("0.00"), total - paid_total)
    is_full = remaining <= 0
    payment_status = "PAYÉE" if is_full else "PARTIELLEMENT PAYÉE"
    payment_method = "TITRE RESTAURANT" if is_full and before <= 0 else "MIXTE"

    conn.execute("""
        UPDATE caisse_orders
        SET payment=%s,
            payment_status=%s,
            payment_method=%s,
            paid_amount=%s,
            paid_at=%s,
            updated_at=%s
        WHERE id=%s
    """, (
        payment_method,
        payment_status,
        payment_method,
        paid_total,
        now if is_full else None,
        now,
        order_id,
    ))

    fiscal_ticket_number = None
    if is_full:
        fiscal_ticket_number = allocate_fiscal_ticket_number(
            conn, ensure_order_schema, order_id, now
        )

    return {
        "duplicate": False,
        "order_id": order_id,
        "num": row["num"],
        "payment_status": payment_status,
        "transaction_id": tx_id,
        "paid_total": float(paid_total),
        "remaining_amount": float(remaining),
        "fiscal_ticket_number": fiscal_ticket_number,
    }


def register_edenred_uat_isolated_phase6(app, db=None, ensure_order_schema=None):
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
        return redirect(_authorize_url(c, "balance"), code=302)

    @app.get("/api/edenred/test-payment-phase6")
    def edenred_test_payment_phase6():
        """Démarre explicitement un paiement UAT isolé de 1,00 EUR."""
        c = _config()
        if not _enabled():
            return jsonify({"ok": False, "error": "Edenred SITE désactivé", "code": "EDENRED_DISABLED"}), 403
        if not _configured(c):
            return jsonify({"ok": False, "error": "Configuration Edenred UAT incomplète", "code": "EDENRED_CONFIG_INCOMPLETE"}), 503
        return redirect(_authorize_url(c, "payment_uat_100"), code=302)

    @app.get("/api/edenred/orders/<order_id>/start-uat-phase6")
    def edenred_order_start_uat_phase6(order_id):
        c = _config()
        if not _enabled():
            return jsonify({"ok": False, "error": "Edenred UAT désactivé", "code": "EDENRED_DISABLED"}), 403
        if not _configured(c) or db is None or ensure_order_schema is None:
            return jsonify({"ok": False, "error": "Edenred UAT indisponible", "code": "EDENRED_NOT_READY"}), 503

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

        return redirect(
            _authorize_url(c, "site_order_uat", {"order_id": str(order_id)}),
            code=302,
        )

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

        amount, currency = _extract_balance(balance)
        balance_shape = _safe_shape(balance)
        action = str(state_data.get("action") or "balance")

        if action not in {"payment_uat_100", "site_order_uat"}:
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
                "balance_shape": balance_shape,
                "transaction_created": False,
                "tokens_exposed": False,
                "secrets_exposed": False,
                "state_validated": bool(state_data),
            })

        if action == "site_order_uat":
            if db is None or ensure_order_schema is None:
                return jsonify({"ok": False, "error": "Paiement commande Edenred indisponible"}), 503

            order_id = str(state_data.get("order_id") or "").strip()
            if not order_id:
                return jsonify({"ok": False, "error": "Commande Edenred absente du state"}), 400

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
                        "environment": "UAT",
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
                        "environment": "UAT",
                        "stage": "pre_transaction",
                        "error": "Aucun solde Edenred disponible pour cette commande.",
                        "available_amount_cents": amount,
                        "order_amount_cents": order_amount_cents,
                        "transaction_created": False,
                        "secrets_exposed": False,
                    }), 400

                edenred_amount_cents = min(int(amount), order_amount_cents)
                edenred_amount_eur = _money(Decimal(edenred_amount_cents) / Decimal("100"))
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
                return jsonify({"ok": False, "error": "Paiement Edenred UAT impossible", "stage": "transaction"}), 502

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
                    "environment": "UAT",
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
                        )
                remaining_eur = _money(recorded.get("remaining_amount") or 0)
                kitchen = None
                next_payment = None

                if remaining_eur > 0:
                    try:
                        mollie_data = create_mollie_payment_for_order(
                            db, ensure_order_schema, order_id
                        )
                    except Exception as exc:
                        return jsonify({
                            "ok": False,
                            "provider": "EDENRED_EDPS",
                            "environment": "UAT",
                            "stage": "mixed_payment",
                            "error": "Création du complément CB impossible.",
                            "detail": str(exc),
                            "edenred_payment_recorded": True,
                            "edenred_amount_cents": edenred_amount_cents,
                            "remaining_amount_eur": float(remaining_eur),
                            "payment_status": recorded.get("payment_status"),
                            "secrets_exposed": False,
                        }), 502
                    next_payment = {
                        "provider": "MOLLIE",
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
                    "environment": "UAT",
                    "stage": "record_payment",
                    "error": str(exc),
                    "transaction_created": True,
                    "payment_recorded": False,
                    "secrets_exposed": False,
                }), 500
            except Exception:
                return jsonify({
                    "ok": False,
                    "provider": "EDENRED_EDPS",
                    "environment": "UAT",
                    "stage": "record_payment",
                    "error": "Transaction Edenred capturée mais enregistrement local à vérifier.",
                    "transaction_created": True,
                    "payment_recorded": False,
                    "secrets_exposed": False,
                }), 500

            return jsonify({
                "ok": True,
                "provider": "EDENRED_EDPS",
                "environment": "UAT",
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

        test_amount = 100
        if not isinstance(amount, (int, float)) or amount < test_amount:
            return jsonify({
                "ok": False,
                "provider": "EDENRED_EDPS",
                "environment": "UAT",
                "stage": "pre_transaction",
                "error": "Solde Edenred UAT insuffisant pour le test de 1,00 EUR.",
                "available_amount_cents": amount,
                "test_amount_cents": test_amount,
                "transaction_created": False,
                "tokens_exposed": False,
                "secrets_exposed": False,
            }), 400

        order_ref = "BCH-UAT-" + secrets.token_hex(6).upper()
        tstamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        payment_payload = {
            "order_ref": order_ref,
            "mid": c["mid"],
            "amount": test_amount,
            "capture_mode": "auto",
            "extra_field": order_ref,
            "tstamp": tstamp,
        }
        try:
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
            return _provider_error("transaction", exc)

        tx_data = transaction.get("data") if isinstance(transaction, dict) else {}
        tx_data = tx_data if isinstance(tx_data, dict) else {}
        tx_meta = transaction.get("meta") if isinstance(transaction, dict) else {}
        tx_meta = tx_meta if isinstance(tx_meta, dict) else {}
        captured_amount = tx_data.get("captured_amount")
        if captured_amount is None:
            captured_amount = tx_data.get("capture_amount")

        return jsonify({
            "ok": str(tx_meta.get("status") or "").lower() == "succeeded" and str(tx_data.get("status") or "").lower() == "captured",
            "provider": "EDENRED_EDPS",
            "environment": "UAT",
            "stage": "transaction",
            "authentication": "succeeded",
            "token_exchange": "succeeded",
            "userinfo": "succeeded",
            "balance_read": "succeeded",
            "available_amount_before_cents": amount,
            "test_amount_cents": test_amount,
            "test_amount_eur": 1.0,
            "currency": currency or "EUR",
            "transaction_created": True,
            "transaction_status": tx_data.get("status"),
            "order_ref": tx_data.get("order_ref") or order_ref,
            "authorization_id_present": bool(tx_data.get("authorization_id")),
            "capture_id_present": bool(tx_data.get("capture_id")),
            "authorized_amount_cents": tx_data.get("authorized_amount"),
            "captured_amount_cents": captured_amount,
            "provider_status": tx_meta.get("status"),
            "tokens_exposed": False,
            "secrets_exposed": False,
            "state_validated": bool(state_data),
        })
