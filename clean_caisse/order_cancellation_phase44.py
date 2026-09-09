"""Phase 4.4 — annulation des commandes non payées.

Le numéro opérationnel de commande reste immuable et n'est jamais réattribué.
Une annulation ne supprime pas physiquement la commande : elle est conservée
pour l'audit mais masquée de l'historique commercial normal.
"""
import time

from flask import jsonify


def _ensure_cancellation_schema(conn, ensure_order_schema):
    ensure_order_schema(conn)
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS cancelled_at BIGINT NULL")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS cancellation_hidden BOOLEAN NOT NULL DEFAULT FALSE")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_caisse_orders_cancellation_hidden ON caisse_orders(cancellation_hidden)")


def register_order_cancellation_phase44(app, db, ensure_order_schema):
    @app.post("/api/orders/<order_id>/cancel-phase44")
    def cancel_order_phase44(order_id):
        now = int(time.time() * 1000)
        try:
            with db() as conn:
                with conn.transaction():
                    _ensure_cancellation_schema(conn, ensure_order_schema)
                    order = conn.execute("""
                        SELECT id,num,status,payment,payment_status,paid_amount,z_closure_id,
                               cancellation_hidden
                        FROM caisse_orders WHERE id=%s FOR UPDATE
                    """, (order_id,)).fetchone()
                    if not order:
                        return jsonify({"ok": False, "error": "Commande introuvable"}), 404
                    if order.get("cancellation_hidden"):
                        return jsonify({"ok": True, "id": order_id, "num": order["num"], "status": "ANNULÉE"})
                    if order.get("z_closure_id") is not None:
                        return jsonify({"ok": False, "error": "Commande clôturée par le Z : annulation interdite", "code": "ORDER_Z_LOCKED"}), 409

                    paid_amount = order.get("paid_amount") or 0
                    payment_status = str(order.get("payment_status") or "À ENCAISSER").upper()
                    if paid_amount > 0 or payment_status not in {"À ENCAISSER", "A ENCAISSER", "NON PAYÉE", "NON PAYEE"}:
                        return jsonify({"ok": False, "error": "Commande déjà payée : utilisez Rembourser", "code": "REFUND_REQUIRED"}), 409

                    tx = conn.execute("""
                        SELECT 1 FROM caisse_payment_transactions
                        WHERE order_id=%s AND transaction_type='PAYMENT' AND status='SUCCEEDED'
                        LIMIT 1
                    """, (order_id,)).fetchone() if conn.execute("SELECT to_regclass('public.caisse_payment_transactions') AS t").fetchone()["t"] else None
                    if tx:
                        return jsonify({"ok": False, "error": "Commande déjà payée : utilisez Rembourser", "code": "REFUND_REQUIRED"}), 409

                    conn.execute("""
                        UPDATE caisse_orders
                        SET status='ANNULÉE', cancellation_hidden=TRUE, cancelled_at=%s, updated_at=%s
                        WHERE id=%s
                    """, (now, now, order_id))
            return jsonify({"ok": True, "id": order_id, "num": order["num"], "status": "ANNULÉE", "hidden_from_history": True})
        except Exception as exc:
            return jsonify({"ok": False, "error": "Annulation impossible", "detail": str(exc)}), 500
