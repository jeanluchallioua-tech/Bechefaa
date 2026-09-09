"""Phase 4.4 — métadonnées groupées pour l'historique.

Évite les appels HTTP/SQL par commande pour l'annulation et le numéro de ticket
comptable. Une seule requête PostgreSQL retourne les métadonnées des commandes
visibles dans l'historique.
"""
from flask import jsonify


def register_history_meta_phase44(app, db):
    @app.get("/api/orders/history-meta-phase44")
    def history_meta_phase44():
        try:
            with db() as conn:
                rows = conn.execute("""
                    SELECT id,
                           COALESCE(payment_status, 'À ENCAISSER') AS payment_status,
                           COALESCE(paid_amount, 0) AS paid_amount,
                           z_closure_id,
                           fiscal_ticket_number
                    FROM caisse_orders
                    WHERE COALESCE(cancellation_hidden, FALSE) = FALSE
                    ORDER BY created_at DESC
                    LIMIT 150
                """).fetchall()
            return jsonify({
                "ok": True,
                "orders": {
                    str(r["id"]): {
                        "payment_status": r["payment_status"],
                        "paid_amount": float(r["paid_amount"] or 0),
                        "z_locked": r.get("z_closure_id") is not None,
                        "fiscal_ticket_number": r.get("fiscal_ticket_number"),
                    }
                    for r in rows
                },
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": "Métadonnées historique indisponibles", "detail": str(exc)}), 500
