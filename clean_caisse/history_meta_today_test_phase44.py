"""Phase 4.4 — test isolé des métadonnées d'historique limitées au jour courant.

Ne remplace aucun endpoint stable. Sert uniquement à valider le filtrage Europe/Paris
et l'exclusion des commandes annulées avant intégration éventuelle.
"""
from flask import jsonify


def register_history_meta_today_test_phase44(app, db):
    @app.get("/api/history-meta-today-phase44-test")
    def history_meta_today_test_phase44():
        try:
            with db() as conn:
                rows = conn.execute("""
                    SELECT id,
                           num,
                           total,
                           COALESCE(payment_status, 'À ENCAISSER') AS payment_status,
                           payment_method,
                           COALESCE(paid_amount, 0) AS paid_amount,
                           cash_received,
                           COALESCE(change_due, 0) AS change_due,
                           paid_at,
                           z_closure_id,
                           fiscal_ticket_number
                    FROM caisse_orders
                    WHERE COALESCE(cancellation_hidden, FALSE) = FALSE
                      AND UPPER(COALESCE(status, '')) <> 'ANNULÉE'
                      AND (to_timestamp(created_at / 1000.0) AT TIME ZONE 'Europe/Paris')::date
                          = (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Paris')::date
                    ORDER BY created_at DESC
                    LIMIT 150
                """).fetchall()
            return jsonify({
                "ok": True,
                "scope": "today_europe_paris_non_cancelled",
                "count": len(rows),
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
            return jsonify({"ok": False, "error": "Métadonnées test indisponibles", "detail": str(exc)}), 500
