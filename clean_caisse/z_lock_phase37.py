"""Phase 3.7 — verrouillage définitif des commandes après Z.

Aucun Z n'est déclenché ici. Lorsqu'une commande porte un z_closure_id, toute
requête de modification de cette commande est refusée côté serveur. Les lectures,
l'historique et les impressions restent autorisés.
"""
import re
from flask import jsonify, request


def register_z_lock_phase37(app, db, ensure_order_schema):
    def ensure_lock_schema(conn):
        ensure_order_schema(conn)
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS z_closure_id BIGINT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_caisse_orders_z_closure_id ON caisse_orders(z_closure_id)")

    def _order_id_from_path(path):
        patterns = (
            r"^/api/orders/(\d+)$",
            r"^/api/orders/(\d+)/",
            r"^/api/kitchen/orders/(\d+)(?:/|$)",
        )
        for pattern in patterns:
            match = re.match(pattern, path)
            if match:
                return int(match.group(1))
        return None

    @app.before_request
    def reject_closed_order_mutation_phase37():
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return None
        order_id = _order_id_from_path(request.path)
        if order_id is None:
            return None
        try:
            with db() as conn:
                ensure_lock_schema(conn)
                conn.commit()
                row = conn.execute("SELECT z_closure_id FROM caisse_orders WHERE id=%s", (order_id,)).fetchone()
            if row and row.get("z_closure_id") is not None:
                return jsonify({
                    "ok": False,
                    "error": "Commande clôturée par le Z : modification interdite",
                    "code": "ORDER_Z_LOCKED",
                    "z_closure_id": row["z_closure_id"],
                }), 409
        except Exception as exc:
            # Fail closed for a mutation: if the fiscal lock cannot be verified,
            # never risk modifying a potentially closed order.
            return jsonify({"ok": False, "error": "Vérification du verrou Z impossible", "detail": str(exc)}), 503
        return None

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
                "phase": "3.7-z-lock-enforced",
                "locked_orders": int(row["locked_orders"] or 0),
                "unlocked_orders": int(row["unlocked_orders"] or 0),
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": "Diagnostic verrou Z indisponible", "detail": str(exc)}), 500
