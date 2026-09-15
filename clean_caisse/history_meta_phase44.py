"""Phase 4.4 — métadonnées groupées pour l'historique du jour.

Évite les appels HTTP/SQL par commande pour l'annulation, l'encaissement et le
numéro de ticket comptable. Une seule requête PostgreSQL retourne les
métadonnées des commandes visibles du jour en Europe/Paris.

Le statut de remboursement est dérivé du journal financier lorsqu'il existe :
un remboursement ne doit jamais être réinterprété comme un reste à encaisser.
"""
from flask import jsonify


def register_history_meta_phase44(app, db):
    @app.get("/api/orders/history-meta-phase44")
    def history_meta_phase44():
        try:
            with db() as conn:
                rows = conn.execute("""
                    SELECT o.id,
                           o.num,
                           o.total,
                           CASE
                               WHEN COALESCE(SUM(CASE WHEN t.transaction_type='REFUND' AND t.status='SUCCEEDED' THEN t.amount ELSE 0 END),0) > 0
                                AND COALESCE(SUM(CASE WHEN t.transaction_type='REFUND' AND t.status='SUCCEEDED' THEN t.amount ELSE 0 END),0)
                                    >= COALESCE(SUM(CASE WHEN t.transaction_type='PAYMENT' AND t.status='SUCCEEDED' THEN t.amount ELSE 0 END),0)
                                   THEN 'REMBOURSÉE'
                               WHEN COALESCE(SUM(CASE WHEN t.transaction_type='REFUND' AND t.status='SUCCEEDED' THEN t.amount ELSE 0 END),0) > 0
                                   THEN 'PARTIELLEMENT REMBOURSÉE'
                               ELSE COALESCE(o.payment_status, 'À ENCAISSER')
                           END AS payment_status,
                           o.payment_method,
                           COALESCE(o.paid_amount, 0) AS paid_amount,
                           o.cash_received,
                           COALESCE(o.change_due, 0) AS change_due,
                           o.paid_at,
                           o.z_closure_id,
                           o.fiscal_ticket_number
                    FROM caisse_orders o
                    LEFT JOIN caisse_payment_transactions t ON t.order_id=o.id
                    WHERE COALESCE(o.cancellation_hidden, FALSE) = FALSE
                      AND UPPER(COALESCE(o.status, '')) <> 'ANNULÉE'
                      AND (to_timestamp(o.created_at / 1000.0) AT TIME ZONE 'Europe/Paris')::date
                          = (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Paris')::date
                    GROUP BY o.id,o.num,o.total,o.payment_status,o.payment_method,o.paid_amount,
                             o.cash_received,o.change_due,o.paid_at,o.z_closure_id,o.fiscal_ticket_number,o.created_at
                    ORDER BY o.created_at DESC
                    LIMIT 150
                """).fetchall()
            return jsonify({
                "ok": True,
                "orders": {
                    str(r["id"]): {
                        "id": r["id"],
                        "num": r["num"],
                        "total": float(r["total"] or 0),
                        "payment_status": r["payment_status"],
                        "payment_method": r.get("payment_method"),
                        "paid_amount": float(r["paid_amount"] or 0),
                        "cash_received": None if r.get("cash_received") is None else float(r["cash_received"]),
                        "change_due": float(r["change_due"] or 0),
                        "paid_at": r.get("paid_at"),
                        "z_locked": r.get("z_closure_id") is not None,
                        "fiscal_ticket_number": r.get("fiscal_ticket_number"),
                    }
                    for r in rows
                },
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": "Métadonnées historique indisponibles", "detail": str(exc)}), 500
