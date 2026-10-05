"""Diagnostic read-only des commandes récentes BÉCHÉFAA.

Permet de vérifier rapidement les écarts Historique / Cuisine / Encaissement
sans modifier aucune commande.
"""
from flask import jsonify


def register_orders_live_diag_phase6(app, db, ensure_order_schema):
    @app.get("/api/orders/live-diagnostic-phase6")
    def orders_live_diagnostic_phase6():
        try:
            with db() as conn:
                ensure_order_schema(conn)
                rows=conn.execute("""
                    SELECT o.id,o.num,o.table_number,o.table_label,o.customer_name,
                           o.source,o.status,o.payment,o.total,o.created_at,o.updated_at,
                           COALESCE(o.payment_status,'') AS payment_status,
                           COALESCE(o.paid_amount,0) AS paid_amount,
                           COUNT(i.id) AS item_count
                    FROM caisse_orders o
                    LEFT JOIN caisse_order_items i ON i.order_id=o.id
                    GROUP BY o.id,o.num,o.table_number,o.table_label,o.customer_name,
                             o.source,o.status,o.payment,o.total,o.created_at,o.updated_at,
                             o.payment_status,o.paid_amount
                    ORDER BY o.created_at DESC
                    LIMIT 20
                """).fetchall()
            return jsonify({
                "ok":True,
                "read_only":True,
                "orders":[{
                    "id":r["id"],"num":r["num"],
                    "table_number":r.get("table_number"),
                    "table_label":r.get("table_label"),
                    "customer_name":r.get("customer_name"),
                    "source":r.get("source"),
                    "status":r.get("status"),
                    "payment":r.get("payment"),
                    "payment_status":r.get("payment_status"),
                    "paid_amount":float(r.get("paid_amount") or 0),
                    "total":float(r.get("total") or 0),
                    "item_count":int(r.get("item_count") or 0),
                    "created_at":r.get("created_at"),
                    "updated_at":r.get("updated_at"),
                    "visible_in_kitchen":r.get("status") in ("À préparer","En préparation"),
                } for r in rows]
            })
        except Exception as exc:
            return jsonify({"ok":False,"error":"Diagnostic commandes indisponible","detail":str(exc)}),500
