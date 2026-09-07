"""Correctifs de cohérence issus de l'audit final de la Phase 1.

- Le tableau cuisine expose bien les commandes Terminées dans la troisième colonne.
- Correctif isolé, PostgreSQL uniquement.
"""
from flask import jsonify, request


def register_phase1_audit_guard(app, db, ensure_order_schema, order_payload):
    @app.get("/api/kitchen/board")
    def kitchen_board_phase1():
        try:
            with db() as conn:
                ensure_order_schema(conn)
                conn.commit()
                rows = conn.execute(
                    """SELECT id, num, customer_name, source, payment, status, total, created_at, updated_at
                       FROM caisse_orders
                       WHERE status IN ('À préparer', 'En préparation', 'Terminée')
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
