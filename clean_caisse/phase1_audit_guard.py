"""Correctifs de cohérence issus de l'audit final de la Phase 1 / Z Phase 3.7.

- Le tableau cuisine expose les commandes du cycle courant, y compris Terminées.
- Après un Z, les commandes clôturées restent en PostgreSQL et dans l'historique,
  mais disparaissent du tableau Cuisine.
- Le début du cycle Cuisine est borné par le dernier Z enregistré. Cela masque aussi
  les anciennes commandes historiques créées avant la mise en place de z_closure_id.
- Le schéma Z est garanti avant la lecture Cuisine, y compris sur une base neuve.
"""
from flask import jsonify, request


def register_phase1_audit_guard(app, db, ensure_order_schema, order_payload):
    @app.get("/api/kitchen/board")
    def kitchen_board_phase1():
        try:
            with db() as conn:
                ensure_order_schema(conn)
                conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS z_closure_id BIGINT NULL")
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
                conn.commit()
                rows = conn.execute(
                    """SELECT id, num, customer_name, source, payment, status, total, created_at, updated_at
                       FROM caisse_orders
                       WHERE status IN ('À préparer', 'En préparation', 'Terminée')
                         AND z_closure_id IS NULL
                         AND created_at > COALESCE(
                             (SELECT MAX(closed_at) FROM caisse_z_closures),
                             0
                         )
                       ORDER BY
                         CASE status WHEN 'À préparer' THEN 1 WHEN 'En préparation' THEN 2 ELSE 3 END,
                         updated_at ASC, num ASC
                       LIMIT 150"""
                ).fetchall()
                orders = [order_payload(conn, row) for row in rows]
            return jsonify({"ok": True, "orders": orders, "count": len(orders)})
        except Exception as exc:
            return jsonify({"ok": False, "error": "Cuisine indisponible", "detail": str(exc)}), 500

    @app.after_request
    def use_complete_kitchen_board(response):
        if request.path == "/cuisine-preparation" and response.status_code == 200 and response.mimetype == "text/html":
            html = response.get_data(as_text=True)
            html = html.replace("fetch('/api/kitchen/orders')", "fetch('/api/kitchen/board')")
            response.set_data(html)
            response.content_length = len(response.get_data())
        return response
