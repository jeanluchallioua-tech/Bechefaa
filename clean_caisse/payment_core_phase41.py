"""Phase 4.1 — socle d'encaissement BÉCHÉFAA.

Ajoute un état d'encaissement persistant sans modifier le flux Cuisine, le
catalogue, les tickets ni le Z. Les commandes clôturées restent protégées par
le verrou Z de Phase 3.7.
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


def _ensure_payment_schema(conn, ensure_order_schema):
    ensure_order_schema(conn)
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS payment_status TEXT NOT NULL DEFAULT 'À ENCAISSER'")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS payment_method TEXT NULL")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS paid_amount NUMERIC(12,2) NOT NULL DEFAULT 0")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS cash_received NUMERIC(12,2) NULL")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS change_due NUMERIC(12,2) NOT NULL DEFAULT 0")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS paid_at BIGINT NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_caisse_orders_payment_status ON caisse_orders(payment_status)")
    ensure_payment_transaction_schema(conn)


def register_payment_core_phase41(app, db, ensure_order_schema):
    @app.get("/api/payment-phase41/status")
    def payment_phase41_status():
        try:
            with db() as conn:
                _ensure_payment_schema(conn, ensure_order_schema)
                conn.commit()
                row = conn.execute("""
                    SELECT
                        COUNT(*) AS orders,
                        COUNT(*) FILTER (WHERE payment_status='PAYÉE') AS paid,
                        COUNT(*) FILTER (WHERE payment_status<>'PAYÉE') AS unpaid
                    FROM caisse_orders
                """).fetchone()
            return jsonify({
                "ok": True,
                "phase": "4.1-payment-core",
                "methods": sorted(ALLOWED_METHODS),
                "orders": int(row["orders"] or 0),
                "paid": int(row["paid"] or 0),
                "unpaid": int(row["unpaid"] or 0),
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": "Socle d'encaissement indisponible", "detail": str(exc)}), 500

    @app.get("/api/orders/<order_id>/payment-phase41")
    def get_order_payment_phase41(order_id):
        try:
            with db() as conn:
                _ensure_payment_schema(conn, ensure_order_schema)
                conn.commit()
                row = conn.execute("""
                    SELECT id,num,total,payment,payment_status,payment_method,
                           paid_amount,cash_received,change_due,paid_at,z_closure_id
                    FROM caisse_orders WHERE id=%s
                """, (order_id,)).fetchone()
            if not row:
                return jsonify({"ok": False, "error": "Commande introuvable"}), 404
            return jsonify({
                "ok": True,
                "order": {
                    "id": row["id"], "num": row["num"], "total": float(row["total"]),
                    "payment": row["payment"], "payment_status": row["payment_status"],
                    "payment_method": row["payment_method"], "paid_amount": float(row["paid_amount"] or 0),
                    "cash_received": None if row["cash_received"] is None else float(row["cash_received"]),
                    "change_due": float(row["change_due"] or 0), "paid_at": row["paid_at"],
                    "z_locked": row.get("z_closure_id") is not None,
                }
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": "Encaissement indisponible", "detail": str(exc)}), 500

    @app.put("/api/orders/<order_id>/payment-phase41")
    def set_order_payment_phase41(order_id):
        payload = request.get_json(silent=True) or {}
        method = str(payload.get("method") or "").strip().upper()
        if method == "ESPECES":
            method = "ESPÈCES"
        if method not in ALLOWED_METHODS:
            return jsonify({"ok": False, "error": "Moyen de paiement invalide"}), 400

        try:
            with db() as conn:
                with conn.transaction():
                    _ensure_payment_schema(conn, ensure_order_schema)
                    row = conn.execute("SELECT id,num,total,payment_status,z_closure_id FROM caisse_orders WHERE id=%s FOR UPDATE", (order_id,)).fetchone()
                    if not row:
                        return jsonify({"ok": False, "error": "Commande introuvable"}), 404
                    if row.get("z_closure_id") is not None:
                        return jsonify({"ok": False, "error": "Commande clôturée par le Z : encaissement interdit", "code": "ORDER_Z_LOCKED"}), 409
                    if row.get("payment_status") == "PAYÉE":
                        return jsonify({"ok": False, "error": "Commande déjà encaissée", "code": "ORDER_ALREADY_PAID"}), 409

                    total = _money(row["total"])
                    cash_received = None
                    change_due = Decimal("0.00")
                    if method == "ESPÈCES":
                        cash_received = _money(payload.get("received"))
                        if cash_received < total:
                            return jsonify({"ok": False, "error": "Montant reçu insuffisant"}), 400
                        change_due = (cash_received - total).quantize(CENT, rounding=ROUND_HALF_UP)

                    paid_at = int(time.time() * 1000)
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
                    """, (method, method, total, cash_received, change_due, paid_at, paid_at, order_id))
                    transaction_id = record_payment_transaction(conn, order_id, method, total, provider="LOCAL")

            return jsonify({
                "ok": True,
                "id": order_id,
                "num": row["num"],
                "payment_status": "PAYÉE",
                "payment_method": method,
                "paid_amount": float(total),
                "cash_received": None if cash_received is None else float(cash_received),
                "change_due": float(change_due),
                "paid_at": paid_at,
                "transaction_id": transaction_id,
            })
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": "Encaissement impossible", "detail": str(exc)}), 500
