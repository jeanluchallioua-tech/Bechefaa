"""Phase 4.4 — test isolé : historique des commandes du jour uniquement.

Ce module n'altère ni /api/orders/history ni l'interface /historique.
Il expose uniquement un endpoint parallèle de validation avant branchement.
"""
from flask import jsonify


def register_history_today_phase44(app, db, ensure_order_schema, order_payload):
    @app.get('/api/orders/history-today-phase44')
    def history_today_phase44():
        try:
            with db() as conn:
                ensure_order_schema(conn)
                conn.commit()
                rows = conn.execute(
                    """
                    SELECT id, num, customer_name, source, payment, status, total, created_at, updated_at
                    FROM caisse_orders
                    WHERE (to_timestamp(created_at / 1000.0) AT TIME ZONE 'Europe/Paris')::date
                          = (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Paris')::date
                    ORDER BY created_at DESC
                    LIMIT 150
                    """
                ).fetchall()
                orders = [order_payload(conn, row) for row in rows]
            return jsonify({'ok': True, 'scope': 'today_europe_paris', 'orders': orders, 'count': len(orders)})
        except Exception as exc:
            return jsonify({'ok': False, 'error': 'Historique du jour indisponible', 'detail': str(exc)}), 500
