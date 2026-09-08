"""Phase 3.7 — fondation de verrouillage des commandes après Z.

Cette étape ne déclenche aucun Z. Elle prépare uniquement l'association persistante
commande -> clôture Z et un endpoint de diagnostic en lecture seule.
"""
from flask import jsonify


def register_z_lock_phase37(app, db, ensure_order_schema):
    def ensure_lock_schema(conn):
        ensure_order_schema(conn)
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS z_closure_id BIGINT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_caisse_orders_z_closure_id ON caisse_orders(z_closure_id)")

    @app.get("/api/caisse/z/lock-status")
    def z_lock_status_phase37():
        try:
            with db() as conn:
                ensure_lock_schema(conn)
                conn.commit()
                row = conn.execute("""SELECT
                    COUNT(*) FILTER (WHERE z_closure_id IS NOT NULL) AS locked_orders,
                    COUNT(*) FILTER (WHERE z_closure_id IS NULL) AS unlocked_orders
                    FROM caisse_orders""").fetchone()
            return jsonify({
                "ok": True,
                "phase": "3.7-z-lock-foundation",
                "locked_orders": int(row["locked_orders"] or 0),
                "unlocked_orders": int(row["unlocked_orders"] or 0),
                "real_z_executed": False,
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": "Diagnostic verrou Z indisponible", "detail": str(exc)}), 500
