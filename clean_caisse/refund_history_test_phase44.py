"""Phase 4.4 — test isolé de lecture du statut de remboursement dans l'historique.

Aucune écriture : agrège la commande, le journal financier et le montant net.
"""
from flask import jsonify, request


def register_refund_history_test_phase44(app, db):
    @app.get("/api/refund-history-phase44-test")
    def refund_history_phase44_test():
        order_id = str(request.args.get("order_id") or "").strip()
        if not order_id:
            return jsonify({"ok": False, "error": "order_id obligatoire"}), 400
        try:
            with db() as conn:
                order = conn.execute("""
                    SELECT id,num,total,payment_status,payment_method,COALESCE(paid_amount,0) AS paid_amount
                    FROM caisse_orders WHERE id=%s
                """, (order_id,)).fetchone()
                if not order:
                    return jsonify({"ok": False, "error": "Commande introuvable"}), 404
                totals = conn.execute("""
                    SELECT
                      COALESCE(SUM(CASE WHEN transaction_type='PAYMENT' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS paid,
                      COALESCE(SUM(CASE WHEN transaction_type='REFUND' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS refunded,
                      COALESCE(SUM(CASE WHEN transaction_type='REFUND' AND status='PENDING_EXTERNAL' THEN amount ELSE 0 END),0) AS pending_refund
                    FROM caisse_payment_transactions WHERE order_id=%s
                """, (order_id,)).fetchone()
            paid = float(totals["paid"] or 0)
            refunded = float(totals["refunded"] or 0)
            pending = float(totals["pending_refund"] or 0)
            return jsonify({
                "ok": True,
                "read_only": True,
                "order": {
                    "id": order["id"],
                    "num": order["num"],
                    "total": float(order["total"] or 0),
                    "payment_status": order["payment_status"],
                    "payment_method": order["payment_method"],
                },
                "financial": {
                    "paid": paid,
                    "refunded": refunded,
                    "pending_refund": pending,
                    "net_paid": round(paid - refunded, 2),
                },
                "display": {
                    "status": order["payment_status"],
                    "refunded_amount": refunded,
                    "net_paid": round(paid - refunded, 2),
                },
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": "Lecture remboursement impossible", "detail": str(exc)}), 500
