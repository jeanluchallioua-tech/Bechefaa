"""Phase 4.4 — complément d'encaissement après modification, module isolé.

IMPORTANT : ce fichier n'est volontairement ni importé ni enregistré dans
wsgi_caisse.py. Il prépare uniquement la correction du cas suivant : une
commande déjà encaissée est ensuite modifiée et son total augmente.

Principe :
- le journal caisse_payment_transactions reste la source du montant réellement payé ;
- si 0 < net payé < nouveau total, l'interface doit proposer uniquement le reste ;
- le complément est enregistré comme une nouvelle transaction PAYMENT ;
- pour préserver le Z actuel, le complément doit utiliser le même moyen de paiement
  que le paiement initial ; les paiements mixtes seront traités en phase 5 ;
- aucune commande clôturée par un Z ne peut être modifiée/encaissée.
"""
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import jsonify, request

from clean_caisse.payment_transactions_phase44 import (
    ensure_payment_transaction_schema,
    record_payment_transaction,
)

CENT = Decimal("0.01")
ALLOWED_METHODS = {"ESPÈCES", "CB", "CHÈQUE", "VIREMENT"}


def _money(value):
    try:
        return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Montant invalide")


def _ledger_state(conn, order_id):
    ensure_payment_transaction_schema(conn)
    row = conn.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN transaction_type='PAYMENT' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS paid,
            COALESCE(SUM(CASE WHEN transaction_type='REFUND' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS refunded
        FROM caisse_payment_transactions
        WHERE order_id=%s
    """, (order_id,)).fetchone()
    paid = _money(row["paid"])
    refunded = _money(row["refunded"])
    return paid, refunded, (paid - refunded).quantize(CENT, rounding=ROUND_HALF_UP)


def _initial_method(conn, order_id):
    rows = conn.execute("""
        SELECT DISTINCT method
        FROM caisse_payment_transactions
        WHERE order_id=%s
          AND transaction_type='PAYMENT'
          AND status='SUCCEEDED'
        ORDER BY method
    """, (order_id,)).fetchall()
    methods = [str(r["method"] or "").strip().upper() for r in rows if str(r["method"] or "").strip()]
    if len(methods) == 1:
        return methods[0]
    return None


def register_payment_topup_isolated_phase44(app, db, ensure_order_schema):
    """Active le complément d'encaissement quand cette fonction sera enregistrée."""
    original_meta = app.view_functions.get("history_meta_phase44")
    original_get = app.view_functions.get("get_order_payment_phase41")
    original_put = app.view_functions.get("set_order_payment_phase41")
    if original_meta is None or original_get is None or original_put is None:
        raise RuntimeError("Routes encaissement/historique introuvables")

    def history_meta_topup_phase44(*args, **kwargs):
        flask_response = app.make_response(original_meta(*args, **kwargs))
        if flask_response.status_code < 200 or flask_response.status_code >= 300:
            return flask_response
        payload = flask_response.get_json(silent=True) or {}
        orders = payload.get("orders") or {}
        if not orders:
            return flask_response
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
            by_id = {str(r["order_id"]): (_money(r["paid"]) - _money(r["refunded"])) for r in rows}
            for order_id, info in orders.items():
                total = _money(info.get("total"))
                net = by_id.get(str(order_id), Decimal("0.00"))
                if Decimal("0.00") < net < total:
                    info["payment_status"] = "PARTIELLEMENT PAYÉE"
                    info["paid_amount"] = float(net)
                    info["remaining_amount"] = float((total - net).quantize(CENT))
                    info["topup_required"] = True
            return jsonify(payload)
        except Exception:
            # En cas d'échec du calcul complémentaire, ne pas casser l'historique existant.
            return flask_response

    def get_order_payment_topup_phase44(order_id, *args, **kwargs):
        flask_response = app.make_response(original_get(order_id, *args, **kwargs))
        if flask_response.status_code < 200 or flask_response.status_code >= 300:
            return flask_response
        payload = flask_response.get_json(silent=True) or {}
        info = payload.get("order") or {}
        try:
            with db() as conn:
                ensure_order_schema(conn)
                ensure_payment_transaction_schema(conn)
                _, _, net = _ledger_state(conn, order_id)
            order_total = _money(info.get("total"))
            if Decimal("0.00") < net < order_total:
                remaining = (order_total - net).quantize(CENT)
                # L'UI Phase 4.3 utilise `total` comme montant à encaisser.
                info["order_total"] = float(order_total)
                info["total"] = float(remaining)
                info["remaining_amount"] = float(remaining)
                info["paid_amount"] = float(net)
                info["payment_status"] = "PARTIELLEMENT PAYÉE"
                info["topup_required"] = True
            return jsonify(payload)
        except Exception:
            return flask_response

    def set_order_payment_topup_phase44(order_id, *args, **kwargs):
        payload = request.get_json(silent=True) or {}
        method = str(payload.get("method") or "").strip().upper()
        if method == "ESPECES":
            method = "ESPÈCES"
        if method not in ALLOWED_METHODS:
            return jsonify({"ok": False, "error": "Moyen de paiement invalide"}), 400

        try:
            with db() as conn:
                with conn.transaction():
                    ensure_order_schema(conn)
                    ensure_payment_transaction_schema(conn)
                    order = conn.execute("""
                        SELECT id,num,total,payment_status,payment_method,payment,
                               paid_amount,cash_received,change_due,paid_at,
                               z_closure_id,fiscal_ticket_number
                        FROM caisse_orders
                        WHERE id=%s
                        FOR UPDATE
                    """, (order_id,)).fetchone()
                    if not order:
                        return jsonify({"ok": False, "error": "Commande introuvable"}), 404
                    if order.get("z_closure_id") is not None:
                        return jsonify({"ok": False, "error": "Commande clôturée par le Z : encaissement interdit", "code": "ORDER_Z_LOCKED"}), 409

                    _, _, net = _ledger_state(conn, order_id)
                    total = _money(order["total"])
                    if not (Decimal("0.00") < net < total):
                        # Cas normal : conserver strictement le socle Phase 4.1.
                        return original_put(order_id, *args, **kwargs)

                    initial_method = _initial_method(conn, order_id)
                    if not initial_method:
                        return jsonify({
                            "ok": False,
                            "error": "Complément refusé : moyen du paiement initial indéterminable"
                        }), 409
                    if method != initial_method:
                        return jsonify({
                            "ok": False,
                            "error": "Pour cette clôture, le complément doit utiliser le même moyen de paiement : " + initial_method,
                            "required_method": initial_method,
                        }), 409

                    remaining = (total - net).quantize(CENT, rounding=ROUND_HALF_UP)
                    cash_received = None
                    change_due = Decimal("0.00")
                    if method == "ESPÈCES":
                        cash_received = _money(payload.get("received"))
                        if cash_received < remaining:
                            return jsonify({"ok": False, "error": "Montant reçu insuffisant"}), 400
                        change_due = (cash_received - remaining).quantize(CENT, rounding=ROUND_HALF_UP)

                    paid_at = int(time.time() * 1000)
                    transaction_id = record_payment_transaction(
                        conn, order_id, method, remaining, provider="LOCAL"
                    )

                    old_cash = _money(order.get("cash_received")) if order.get("cash_received") is not None else Decimal("0.00")
                    old_change = _money(order.get("change_due"))
                    if method == "ESPÈCES":
                        new_cash = (old_cash + cash_received).quantize(CENT)
                        new_change = (old_change + change_due).quantize(CENT)
                    else:
                        new_cash = order.get("cash_received")
                        new_change = old_change

                    conn.execute("""
                        UPDATE caisse_orders
                        SET payment=%s,
                            payment_status='PAYÉE',
                            payment_method=%s,
                            paid_amount=%s,
                            cash_received=%s,
                            change_due=%s,
                            paid_at=%s,
                            updated_at=%s
                        WHERE id=%s
                    """, (
                        method, method, total, new_cash, new_change,
                        paid_at, paid_at, order_id,
                    ))

            return jsonify({
                "ok": True,
                "id": order_id,
                "num": order["num"],
                "fiscal_ticket_number": order.get("fiscal_ticket_number"),
                "payment_status": "PAYÉE",
                "payment_method": method,
                "paid_amount": float(total),
                "topup_amount": float(remaining),
                "order_total": float(total),
                "cash_received": None if cash_received is None else float(cash_received),
                "change_due": float(change_due),
                "paid_at": paid_at,
                "transaction_id": transaction_id,
                "topup": True,
            })
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": "Complément d'encaissement impossible", "detail": str(exc)}), 500

    history_meta_topup_phase44.__name__ = "history_meta_topup_phase44"
    get_order_payment_topup_phase44.__name__ = "get_order_payment_topup_phase44"
    set_order_payment_topup_phase44.__name__ = "set_order_payment_topup_phase44"
    app.view_functions["history_meta_phase44"] = history_meta_topup_phase44
    app.view_functions["get_order_payment_phase41"] = get_order_payment_topup_phase44
    app.view_functions["set_order_payment_phase41"] = set_order_payment_topup_phase44
