"""Phase 6 — intégration Mollie isolée pour les paiements SITE.

Cette couche ne modifie pas le fonctionnement du TPE BNP. Elle expose un socle
Mollie CB : création de paiement, lecture du statut et webhook idempotent.

Aucune clé n'est stockée dans le dépôt. La variable MOLLIE_API_KEY est fournie
par Clever Cloud. Le parcours SITE n'est activé que si
BECHEFAA_MOLLIE_SITE_ENABLED vaut 1/true/yes/on.
"""
import json
import os
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import jsonify, request

from clean_caisse.fiscal_ticket_phase44 import allocate_fiscal_ticket_number
from clean_caisse.payment_core_phase41 import _ensure_payment_schema
from clean_caisse.payment_transactions_phase44 import (
    ensure_payment_transaction_schema,
    record_payment_transaction,
)

CENT = Decimal("0.01")
MOLLIE_API_BASE = "https://api.mollie.com/v2"


def _money(value):
    try:
        return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Montant invalide")


def _mollie_key():
    return str(os.getenv("MOLLIE_API_KEY") or "").strip()


def _configured_return_url():
    return str(os.getenv("BECHEFAA_MOLLIE_RETURN_URL") or "").strip()


def _site_enabled():
    raw = str(os.getenv("BECHEFAA_MOLLIE_SITE_ENABLED") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _public_base_url():
    configured = str(os.getenv("BECHEFAA_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    return request.url_root.rstrip("/")


def _mollie_request(method, path, payload=None):
    key = _mollie_key()
    if not key:
        raise RuntimeError("MOLLIE_API_KEY non configurée")

    body = None
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "User-Agent": "BECHEFAA-Caisse/phase6",
    }
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(MOLLIE_API_BASE + path, data=body, headers=headers, method=method.upper())
    try:
        with urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw or "{}")
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8") or "{}")
        except Exception:
            detail = {"detail": str(exc)}
        message = detail.get("detail") or detail.get("title") or f"HTTP {exc.code}"
        raise RuntimeError("Mollie : " + str(message)) from exc
    except URLError as exc:
        raise RuntimeError("Mollie indisponible : " + str(exc.reason)) from exc


def _checkout_url(payment):
    links = payment.get("_links") if isinstance(payment, dict) else {}
    checkout = links.get("checkout") if isinstance(links, dict) else {}
    return str(checkout.get("href") or "") if isinstance(checkout, dict) else ""


def _payment_order_id(payment):
    metadata = payment.get("metadata") if isinstance(payment, dict) else None
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}
    if not isinstance(metadata, dict):
        return ""
    return str(metadata.get("order_id") or "").strip()


def _existing_paid_total(conn, order_id):
    ensure_payment_transaction_schema(conn)
    row = conn.execute("""
        SELECT COALESCE(SUM(CASE
            WHEN transaction_type='PAYMENT' AND status='SUCCEEDED' THEN amount
            WHEN transaction_type='REFUND' AND status='SUCCEEDED' THEN -amount
            ELSE 0 END),0) AS net
        FROM caisse_payment_transactions
        WHERE order_id=%s
    """, (order_id,)).fetchone()
    return _money(row["net"] if row else 0)


def _apply_paid_payment(conn, ensure_order_schema, payment):
    """Enregistre une confirmation Mollie une seule fois après relecture API."""
    payment_id = str(payment.get("id") or "").strip()
    order_id = _payment_order_id(payment)
    if not payment_id or not order_id:
        raise ValueError("Référence Mollie ou commande manquante")

    _ensure_payment_schema(conn, ensure_order_schema)
    row = conn.execute(
        "SELECT id,num,total FROM caisse_orders WHERE id=%s FOR UPDATE",
        (order_id,),
    ).fetchone()
    if not row:
        raise ValueError("Commande BÉCHÉFAA introuvable")

    existing = conn.execute("""
        SELECT id FROM caisse_payment_transactions
        WHERE provider='MOLLIE' AND external_reference=%s
          AND transaction_type='PAYMENT' AND status='SUCCEEDED'
        LIMIT 1
    """, (payment_id,)).fetchone()
    if existing:
        return {
            "order_id": order_id,
            "transaction_id": existing["id"],
            "duplicate": True,
            "payment_status": "PAYÉE",
        }

    amount_obj = payment.get("amount") if isinstance(payment.get("amount"), dict) else {}
    amount = _money(amount_obj.get("value"))
    if amount <= 0:
        raise ValueError("Montant Mollie invalide")

    total = _money(row["total"])
    before = _existing_paid_total(conn, order_id)
    remaining_before = max(Decimal("0.00"), total - before)
    if amount > remaining_before:
        raise ValueError("Le paiement Mollie dépasse le solde de la commande")

    tx_id = record_payment_transaction(
        conn,
        order_id,
        "CB",
        amount,
        provider="MOLLIE",
        external_reference=payment_id,
        created_by="MOLLIE_WEBHOOK",
    )

    now = int(time.time() * 1000)
    paid_total = before + amount
    is_full = paid_total >= total
    payment_status = "PAYÉE" if is_full else "PARTIELLEMENT PAYÉE"

    conn.execute("""
        UPDATE caisse_orders
        SET payment=%s,
            payment_status=%s,
            payment_method=%s,
            paid_amount=%s,
            paid_at=%s,
            updated_at=%s
        WHERE id=%s
    """, ("CB", payment_status, "CB", paid_total, now, now, order_id))

    fiscal_ticket_number = None
    if is_full:
        fiscal_ticket_number = allocate_fiscal_ticket_number(conn, ensure_order_schema, order_id, now)

    return {
        "order_id": order_id,
        "transaction_id": tx_id,
        "duplicate": False,
        "payment_status": payment_status,
        "paid_amount": float(paid_total),
        "fiscal_ticket_number": fiscal_ticket_number,
    }


def _send_paid_order_to_kitchen(app, order_id):
    """Envoie une commande payée en cuisine via la route métier existante."""
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


def _finalize_payment(app, db, ensure_order_schema, payment_id):
    """Relit Mollie, comptabilise si payé, puis envoie la commande en cuisine."""
    payment = _mollie_request("GET", "/payments/" + str(payment_id))
    status = str(payment.get("status") or "").lower()
    order_id = _payment_order_id(payment)
    if not order_id:
        raise ValueError("Paiement Mollie sans order_id BÉCHÉFAA")

    result = None
    kitchen = None
    if status == "paid":
        with db() as conn:
            with conn.transaction():
                result = _apply_paid_payment(conn, ensure_order_schema, payment)
        kitchen = _send_paid_order_to_kitchen(app, order_id)

    return {
        "payment_id": str(payment.get("id") or payment_id),
        "order_id": order_id,
        "status": status,
        "paid": status == "paid",
        "recorded": bool(result),
        "result": result,
        "kitchen": kitchen,
    }


def register_mollie_payments_isolated_phase6(app, db, ensure_order_schema):
    @app.get("/api/mollie/status-phase6")
    def mollie_status_phase6():
        configured = bool(_mollie_key()) and bool(_configured_return_url())
        return jsonify({
            "ok": True,
            "provider": "MOLLIE",
            "scope": "SITE_ONLY",
            "restaurant_provider": "BNP_TPE",
            "api_key_configured": bool(_mollie_key()),
            "return_url_configured": bool(_configured_return_url()),
            "site_enabled": _site_enabled(),
            "site_ready": configured and _site_enabled(),
            "webhook_url": _public_base_url() + "/api/mollie/webhook-phase6",
            "active_method": "CB",
            "vouchers": "PREPARED_LATER",
            "writes_on_status": False,
        })

    @app.post("/api/mollie/payments/create-phase6")
    def mollie_create_payment_phase6():
        payload = request.get_json(silent=True) or {}
        order_id = str(payload.get("order_id") or "").strip()
        if not order_id:
            return jsonify({"ok": False, "error": "order_id obligatoire"}), 400
        if not _site_enabled():
            return jsonify({"ok": False, "error": "Paiement Mollie SITE désactivé", "code": "MOLLIE_SITE_DISABLED"}), 403
        if not _mollie_key():
            return jsonify({"ok": False, "error": "Mollie non configuré", "code": "MOLLIE_API_KEY_MISSING"}), 503
        return_url = _configured_return_url()
        if not return_url:
            return jsonify({"ok": False, "error": "URL de retour Mollie non configurée", "code": "MOLLIE_RETURN_URL_MISSING"}), 503

        try:
            with db() as conn:
                _ensure_payment_schema(conn, ensure_order_schema)
                conn.commit()
                order = conn.execute(
                    "SELECT id,num,total,status FROM caisse_orders WHERE id=%s",
                    (order_id,),
                ).fetchone()
                if not order:
                    return jsonify({"ok": False, "error": "Commande introuvable"}), 404
                paid = _existing_paid_total(conn, order_id)
                total = _money(order["total"])

            remaining = max(Decimal("0.00"), total - paid)
            if remaining <= 0:
                return jsonify({"ok": False, "error": "Commande déjà payée"}), 409

            mollie_payload = {
                "amount": {"currency": "EUR", "value": f"{remaining:.2f}"},
                "description": f"BÉCHÉFAA commande #{order['num']}",
                "method": "creditcard",
                "redirectUrl": return_url,
                "webhookUrl": _public_base_url() + "/api/mollie/webhook-phase6",
                "metadata": {
                    "order_id": order_id,
                    "order_num": str(order["num"]),
                    "channel": "SITE",
                    "integration": "BECHEFAA_PHASE6",
                },
            }
            payment = _mollie_request("POST", "/payments", mollie_payload)
            checkout = _checkout_url(payment)
            if not payment.get("id") or not checkout:
                raise RuntimeError("Mollie n'a pas retourné de lien de paiement")

            return jsonify({
                "ok": True,
                "provider": "MOLLIE",
                "order_id": order_id,
                "payment_id": payment.get("id"),
                "status": payment.get("status"),
                "amount": float(remaining),
                "checkout_url": checkout,
            }), 201
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": "Création du paiement Mollie impossible", "detail": str(exc)}), 502

    @app.get("/api/mollie/payments/<payment_id>/status-phase6")
    def mollie_payment_status_phase6(payment_id):
        if not _mollie_key():
            return jsonify({"ok": False, "error": "Mollie non configuré"}), 503
        try:
            payment = _mollie_request("GET", "/payments/" + str(payment_id))
            amount = payment.get("amount") if isinstance(payment.get("amount"), dict) else {}
            return jsonify({
                "ok": True,
                "provider": "MOLLIE",
                "payment_id": payment.get("id"),
                "order_id": _payment_order_id(payment),
                "status": payment.get("status"),
                "method": payment.get("method"),
                "amount": amount.get("value"),
                "currency": amount.get("currency"),
                "paid": payment.get("status") == "paid",
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": "Lecture Mollie impossible", "detail": str(exc)}), 502

    @app.post("/api/mollie/payments/<payment_id>/finalize-phase6")
    def mollie_payment_finalize_phase6(payment_id):
        if not _mollie_key():
            return jsonify({"ok": False, "error": "Mollie non configuré"}), 503
        try:
            result = _finalize_payment(app, db, ensure_order_schema, payment_id)
            return jsonify({"ok": True, **result})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": "Finalisation Mollie impossible", "detail": str(exc)}), 502

    @app.post("/api/mollie/webhook-phase6")
    def mollie_webhook_phase6():
        payload = request.get_json(silent=True) if request.is_json else None
        payment_id = str(request.form.get("id") or ((payload or {}).get("id") if isinstance(payload, dict) else "") or "").strip()
        if not payment_id:
            return jsonify({"ok": False, "error": "Identifiant Mollie manquant"}), 400
        if not _mollie_key():
            return jsonify({"ok": False, "error": "Mollie non configuré"}), 503

        try:
            # Sécurité : le webhook ne fait foi qu'après relecture API côté serveur.
            result = _finalize_payment(app, db, ensure_order_schema, payment_id)
            return jsonify({"ok": True, **result})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": "Traitement webhook Mollie impossible", "detail": str(exc)}), 502
