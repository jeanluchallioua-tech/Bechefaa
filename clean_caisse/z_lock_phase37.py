"""Phase 3.7 — verrouillage définitif de la journée après Z.

Aucun Z n'est déclenché ici. Les commandes déjà clôturées sont immuables et,
si un Z existe pour la journée courante, toute nouvelle commande est refusée.
Les lectures, l'historique et les impressions restent autorisés.
"""
import re
from datetime import datetime
from flask import jsonify, request


def register_z_lock_phase37(app, db, ensure_order_schema):
    def ensure_lock_schema(conn):
        ensure_order_schema(conn)
        conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS z_closure_id BIGINT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_caisse_orders_z_closure_id ON caisse_orders(z_closure_id)")

    def ensure_z_schema(conn):
        conn.execute("""CREATE TABLE IF NOT EXISTS caisse_z_closures (
            id BIGSERIAL PRIMARY KEY,
            business_date TEXT NOT NULL UNIQUE,
            closed_at BIGINT NOT NULL,
            first_order_num BIGINT NULL,
            last_order_num BIGINT NULL,
            order_count INTEGER NOT NULL DEFAULT 0,
            total_ht NUMERIC(12,2) NOT NULL DEFAULT 0,
            tax_rate NUMERIC(6,3) NOT NULL DEFAULT 10,
            tax_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
            total_ttc NUMERIC(12,2) NOT NULL DEFAULT 0,
            payments_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )""")

    def _order_id_from_path(path):
        for pattern in (r"^/api/orders/(\d+)$", r"^/api/orders/(\d+)/", r"^/api/kitchen/orders/(\d+)(?:/|$)"):
            match = re.match(pattern, path)
            if match:
                return int(match.group(1))
        return None

    @app.before_request
    def reject_z_locked_mutation_phase37():
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return None

        # Création d'une nouvelle commande : interdite après le Z du jour.
        if request.method == "POST" and request.path == "/api/orders":
            day = datetime.now().astimezone().strftime("%Y-%m-%d")
            try:
                with db() as conn:
                    ensure_lock_schema(conn)
                    ensure_z_schema(conn)
                    conn.commit()
                    closed = conn.execute("SELECT id,closed_at FROM caisse_z_closures WHERE business_date=%s", (day,)).fetchone()
                if closed:
                    return jsonify({
                        "ok": False,
                        "error": "Journée clôturée par le Z : aucune nouvelle commande ne peut être créée aujourd'hui",
                        "code": "DAY_Z_CLOSED",
                        "z_closure_id": closed["id"],
                    }), 409
            except Exception as exc:
                return jsonify({"ok": False, "error": "Vérification de clôture Z impossible", "detail": str(exc)}), 503
            return None

        # Mutation d'une commande existante : interdite si elle appartient à un Z.
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
            return jsonify({"ok": False, "error": "Vérification du verrou Z impossible", "detail": str(exc)}), 503
        return None

    @app.get("/api/caisse/z/lock-status")
    def z_lock_status_phase37():
        try:
            day = datetime.now().astimezone().strftime("%Y-%m-%d")
            with db() as conn:
                ensure_lock_schema(conn); ensure_z_schema(conn); conn.commit()
                row = conn.execute("""SELECT COUNT(*) FILTER (WHERE z_closure_id IS NOT NULL) AS locked_orders, COUNT(*) FILTER (WHERE z_closure_id IS NULL) AS unlocked_orders FROM caisse_orders""").fetchone()
                closed = conn.execute("SELECT id FROM caisse_z_closures WHERE business_date=%s", (day,)).fetchone()
            return jsonify({"ok":True,"phase":"3.7-z-day-lock-enforced","locked_orders":int(row["locked_orders"] or 0),"unlocked_orders":int(row["unlocked_orders"] or 0),"today_closed":bool(closed)})
        except Exception as exc:
            return jsonify({"ok":False,"error":"Diagnostic verrou Z indisponible","detail":str(exc)}),500
