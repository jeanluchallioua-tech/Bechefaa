"""Phase 4.4 — annulation des commandes non payées.

Une commande annulée reste conservée pour audit mais sort de la séquence
opérationnelle visible. Son ancien numéro est mémorisé dans
original_operational_num afin que, lorsqu'il s'agit du dernier numéro utilisé,
la commande suivante puisse reprendre ce numéro comme si l'annulation n'avait
pas consommé de numéro visible.
"""
import time

from flask import jsonify
from clean_caisse.security_pin_phase44 import register_security_pin_phase44


def _ensure_cancellation_schema(conn, ensure_order_schema):
    ensure_order_schema(conn)
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS cancelled_at BIGINT NULL")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS cancellation_hidden BOOLEAN NOT NULL DEFAULT FALSE")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS original_operational_num BIGINT NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_caisse_orders_cancellation_hidden ON caisse_orders(cancellation_hidden)")


def register_order_cancellation_phase44(app, db, ensure_order_schema):
    # La sécurité est enregistrée avant la route d'annulation : le before_request
    # bloque donc toute annulation sans session PIN valide.
    register_security_pin_phase44(app, db, ensure_order_schema)

    @app.post("/api/orders/<order_id>/cancel-phase44")
    def cancel_order_phase44(order_id):
        now = int(time.time() * 1000)
        try:
            with db() as conn:
                with conn.transaction():
                    _ensure_cancellation_schema(conn, ensure_order_schema)
                    # Verrouillage global volontaire : le numéro visible est unique et
                    # doit être libéré atomiquement avant toute nouvelle commande.
                    conn.execute("LOCK TABLE caisse_orders IN EXCLUSIVE MODE")
                    order = conn.execute("""
                        SELECT id,num,status,payment,payment_status,paid_amount,z_closure_id,
                               cancellation_hidden,original_operational_num
                        FROM caisse_orders WHERE id=%s FOR UPDATE
                    """, (order_id,)).fetchone()
                    if not order:
                        return jsonify({"ok": False, "error": "Commande introuvable"}), 404
                    if order.get("cancellation_hidden"):
                        visible_num = order.get("original_operational_num") or order["num"]
                        return jsonify({"ok": True, "id": order_id, "num": visible_num, "status": "ANNULÉE"})
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

                    original_num = int(order["num"])
                    archive_row = conn.execute(
                        "SELECT COALESCE(MIN(num), 0) - 1 AS archive_num FROM caisse_orders WHERE num < 0"
                    ).fetchone()
                    archive_num = int(archive_row["archive_num"])
                    if archive_num >= 0:
                        archive_num = -1

                    conn.execute("""
                        UPDATE caisse_orders
                        SET status='ANNULÉE',
                            cancellation_hidden=TRUE,
                            original_operational_num=COALESCE(original_operational_num,%s),
                            num=%s,
                            cancelled_at=%s,
                            updated_at=%s
                        WHERE id=%s
                    """, (original_num, archive_num, now, now, order_id))
            return jsonify({
                "ok": True,
                "id": order_id,
                "num": original_num,
                "status": "ANNULÉE",
                "hidden_from_history": True,
                "operational_number_released": True,
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": "Annulation impossible", "detail": str(exc)}), 500
