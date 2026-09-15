"""Phase 5 — compléments d'encaissement mixtes et partiels.

Autorise plusieurs règlements successifs avec Espèces, CB ou Titre restaurant,
en conservant chaque transaction dans le journal financier.
"""
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import jsonify, request

from clean_caisse.payment_transactions_phase44 import (
    ensure_payment_transaction_schema,
    record_payment_transaction,
)
from clean_caisse.fiscal_ticket_phase44 import allocate_fiscal_ticket_number

CENT = Decimal("0.01")
ALLOWED_METHODS = {"ESPÈCES", "CB", "TITRE RESTAURANT"}


def _money(value):
    try:
        return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Montant invalide")


def _ledger_net(conn, order_id):
    ensure_payment_transaction_schema(conn)
    row = conn.execute("""
        SELECT
          COALESCE(SUM(CASE WHEN transaction_type='PAYMENT' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS paid,
          COALESCE(SUM(CASE WHEN transaction_type='REFUND' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS refunded
        FROM caisse_payment_transactions WHERE order_id=%s
    """, (order_id,)).fetchone()
    return (_money(row["paid"]) - _money(row["refunded"])).quantize(CENT)


def _payment_methods(conn, order_id):
    rows = conn.execute("""
        SELECT DISTINCT UPPER(method) AS method
        FROM caisse_payment_transactions
        WHERE order_id=%s AND transaction_type='PAYMENT' AND status='SUCCEEDED' AND method IS NOT NULL
        ORDER BY UPPER(method)
    """, (order_id,)).fetchall()
    return [str(r["method"] or "").strip().upper() for r in rows if str(r["method"] or "").strip()]


def register_payment_topup_mixed_isolated_phase5(app, db, ensure_order_schema):
    original_meta = app.view_functions.get("history_meta_phase44")
    original_get = app.view_functions.get("get_order_payment_phase41")
    original_put = app.view_functions.get("set_order_payment_phase41")
    if original_meta is None or original_get is None or original_put is None:
        raise RuntimeError("Routes encaissement/historique introuvables")

    def history_meta_topup_mixed_phase5(*args, **kwargs):
        response = app.make_response(original_meta(*args, **kwargs))
        if not 200 <= response.status_code < 300:
            return response
        payload = response.get_json(silent=True) or {}
        orders = payload.get("orders") or {}
        if not orders:
            return response
        try:
            ids = list(orders.keys())
            with db() as conn:
                ensure_order_schema(conn)
                ensure_payment_transaction_schema(conn)
                rows = conn.execute("""
                    SELECT order_id,
                      COALESCE(SUM(CASE WHEN transaction_type='PAYMENT' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS paid,
                      COALESCE(SUM(CASE WHEN transaction_type='REFUND' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS refunded
                    FROM caisse_payment_transactions
                    WHERE order_id = ANY(%s)
                    GROUP BY order_id
                """, (ids,)).fetchall()
            net_by_id = {str(r["order_id"]): (_money(r["paid"]) - _money(r["refunded"])).quantize(CENT) for r in rows}
            for order_id, info in orders.items():
                total = _money(info.get("total"))
                net = net_by_id.get(str(order_id), Decimal("0.00"))
                if Decimal("0.00") < net < total:
                    info["payment_status"] = "PARTIELLEMENT PAYÉE"
                    info["paid_amount"] = float(net)
                    info["remaining_amount"] = float((total - net).quantize(CENT))
                    info["topup_required"] = True
            return jsonify(payload)
        except Exception:
            return response

    def get_order_payment_topup_mixed_phase5(order_id, *args, **kwargs):
        response = app.make_response(original_get(order_id, *args, **kwargs))
        if not 200 <= response.status_code < 300:
            return response
        payload = response.get_json(silent=True) or {}
        info = payload.get("order") or {}
        try:
            with db() as conn:
                ensure_order_schema(conn)
                net = _ledger_net(conn, order_id)
                methods = _payment_methods(conn, order_id)
            total = _money(info.get("total"))
            if Decimal("0.00") < net < total:
                remaining = (total - net).quantize(CENT)
                info["order_total"] = float(total)
                info["total"] = float(remaining)
                info["remaining_amount"] = float(remaining)
                info["paid_amount"] = float(net)
                info["payment_status"] = "PARTIELLEMENT PAYÉE"
                info["topup_required"] = True
                info["previous_payment_methods"] = methods
                info["mixed_payment_allowed"] = True
            return jsonify(payload)
        except Exception:
            return response

    def set_order_payment_topup_mixed_phase5(order_id, *args, **kwargs):
        payload = request.get_json(silent=True) or {}
        method = str(payload.get("method") or "").strip().upper()
        if method == "ESPECES":
            method = "ESPÈCES"

        try:
            with db() as conn:
                ensure_order_schema(conn)
                ensure_payment_transaction_schema(conn)
                order = conn.execute("SELECT id,total,z_closure_id FROM caisse_orders WHERE id=%s", (order_id,)).fetchone()
                if not order:
                    return jsonify({"ok": False, "error": "Commande introuvable"}), 404
                net = _ledger_net(conn, order_id)
                total = _money(order["total"])
            if not (Decimal("0.00") < net < total):
                return original_put(order_id, *args, **kwargs)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": "Contrôle complément impossible", "detail": str(exc)}), 500

        if method not in ALLOWED_METHODS:
            return jsonify({"ok": False, "error": "Moyen de paiement invalide"}), 400

        try:
            with db() as conn:
                with conn.transaction():
                    ensure_order_schema(conn)
                    ensure_payment_transaction_schema(conn)
                    order = conn.execute("""
                        SELECT id,num,total,payment_method,payment,cash_received,change_due,
                               z_closure_id,fiscal_ticket_number
                        FROM caisse_orders WHERE id=%s FOR UPDATE
                    """, (order_id,)).fetchone()
                    if not order:
                        return jsonify({"ok": False, "error": "Commande introuvable"}), 404
                    if order["z_closure_id"] is not None:
                        return jsonify({"ok": False, "error": "Commande clôturée par le Z : encaissement interdit", "code": "ORDER_Z_LOCKED"}), 409

                    net = _ledger_net(conn, order_id)
                    total = _money(order["total"])
                    if not (Decimal("0.00") < net < total):
                        return jsonify({"ok": False, "error": "Le complément n'est plus nécessaire. Rechargez l'historique."}), 409

                    previous_methods = _payment_methods(conn, order_id)
                    remaining = (total - net).quantize(CENT)
                    amount = _money(payload.get("amount")) if payload.get("amount") is not None else remaining
                    if amount <= 0:
                        return jsonify({"ok": False, "error": "Le montant à encaisser doit être supérieur à 0"}), 400
                    if amount > remaining:
                        return jsonify({"ok": False, "error": "Le montant à encaisser dépasse le reste à payer"}), 400

                    cash_received = None
                    change_due = Decimal("0.00")
                    if method == "ESPÈCES":
                        cash_received = _money(payload.get("received"))
                        if cash_received < amount:
                            return jsonify({"ok": False, "error": "Montant reçu insuffisant"}), 400
                        change_due = (cash_received - amount).quantize(CENT)

                    paid_at = int(time.time() * 1000)
                    transaction_id = record_payment_transaction(conn, order_id, method, amount, provider="LOCAL")
                    new_net = (net + amount).quantize(CENT)
                    is_full = new_net >= total

                    old_cash = _money(order["cash_received"]) if order["cash_received"] is not None else Decimal("0.00")
                    old_change = _money(order["change_due"])
                    new_cash = (old_cash + cash_received).quantize(CENT) if method == "ESPÈCES" else order["cash_received"]
                    new_change = (old_change + change_due).quantize(CENT) if method == "ESPÈCES" else old_change

                    all_methods = sorted(set(previous_methods + [method]))
                    stored_method = method if len(all_methods) == 1 else "MIXTE"
                    payment_status = "PAYÉE" if is_full else "PARTIELLEMENT PAYÉE"
                    fiscal_ticket_number = order["fiscal_ticket_number"]
                    if is_full and not fiscal_ticket_number:
                        fiscal_ticket_number = allocate_fiscal_ticket_number(conn, ensure_order_schema, order_id, paid_at)

                    conn.execute("""
                        UPDATE caisse_orders
                        SET payment=%s,payment_status=%s,payment_method=%s,paid_amount=%s,
                            cash_received=%s,change_due=%s,paid_at=%s,updated_at=%s
                        WHERE id=%s
                    """, (stored_method, payment_status, stored_method, new_net, new_cash, new_change, paid_at, paid_at, order_id))

            still_due = (total - new_net).quantize(CENT)
            return jsonify({
                "ok": True,
                "id": order_id,
                "num": order["num"],
                "fiscal_ticket_number": fiscal_ticket_number,
                "payment_status": payment_status,
                "payment_method": stored_method,
                "payment_methods": all_methods,
                "paid_amount": float(new_net),
                "topup_amount": float(amount),
                "remaining_amount": float(still_due),
                "order_total": float(total),
                "cash_received": None if cash_received is None else float(cash_received),
                "change_due": float(change_due),
                "paid_at": paid_at,
                "transaction_id": transaction_id,
                "topup": True,
                "mixed_payment": len(all_methods) > 1,
                "partial": not is_full,
            })
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": "Complément d'encaissement impossible", "detail": str(exc)}), 500

    history_meta_topup_mixed_phase5.__name__ = "history_meta_topup_mixed_phase5"
    get_order_payment_topup_mixed_phase5.__name__ = "get_order_payment_topup_mixed_phase5"
    set_order_payment_topup_mixed_phase5.__name__ = "set_order_payment_topup_mixed_phase5"
    app.view_functions["history_meta_phase44"] = history_meta_topup_mixed_phase5
    app.view_functions["get_order_payment_phase41"] = get_order_payment_topup_mixed_phase5
    app.view_functions["set_order_payment_phase41"] = set_order_payment_topup_mixed_phase5
