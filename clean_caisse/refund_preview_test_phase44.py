"""Phase 4.4 — aperçu isolé des remboursements.

Endpoint de test en lecture seule. Il ne crée aucun remboursement et ne modifie
aucune commande. Il sert à vérifier le solde remboursable par transaction avant
d'ajouter l'interface tactile de remboursement.
"""
from flask import jsonify, request


def register_refund_preview_test_phase44(app, db, ensure_order_schema):
    @app.get("/api/refund-preview-phase44-test")
    def refund_preview_phase44_test():
        order_id = str(request.args.get("order_id") or "").strip()
        if not order_id:
            return jsonify({"ok": False, "error": "order_id obligatoire"}), 400

        try:
            with db() as conn:
                ensure_order_schema(conn)
                order = conn.execute(
                    "SELECT id,num,total,payment_status FROM caisse_orders WHERE id=%s",
                    (order_id,),
                ).fetchone()
                if not order:
                    return jsonify({"ok": False, "error": "Commande introuvable"}), 404

                payments = conn.execute("""
                    SELECT p.id,
                           p.provider,
                           p.method,
                           p.amount,
                           p.status,
                           p.external_reference,
                           p.created_at,
                           COALESCE((
                               SELECT SUM(r.amount)
                               FROM caisse_payment_transactions r
                               WHERE r.parent_transaction_id=p.id
                                 AND r.transaction_type='REFUND'
                                 AND r.status IN ('SUCCEEDED','PENDING_EXTERNAL')
                           ),0) AS refunded_or_pending
                    FROM caisse_payment_transactions p
                    WHERE p.order_id=%s
                      AND p.transaction_type='PAYMENT'
                      AND p.status='SUCCEEDED'
                    ORDER BY p.created_at,p.id
                """, (order_id,)).fetchall()

            result = []
            total_refundable = 0.0
            for p in payments:
                amount = float(p["amount"] or 0)
                already = float(p["refunded_or_pending"] or 0)
                refundable = max(0.0, round(amount - already, 2))
                total_refundable = round(total_refundable + refundable, 2)
                result.append({
                    "transaction_id": p["id"],
                    "provider": p["provider"],
                    "method": p["method"],
                    "amount": amount,
                    "refunded_or_pending": already,
                    "refundable": refundable,
                    "external_reference": p.get("external_reference"),
                    "created_at": p["created_at"],
                })

            return jsonify({
                "ok": True,
                "read_only": True,
                "order": {
                    "id": order["id"],
                    "num": order["num"],
                    "total": float(order["total"] or 0),
                    "payment_status": order["payment_status"],
                },
                "payments": result,
                "total_refundable": total_refundable,
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": "Aperçu remboursement indisponible", "detail": str(exc)}), 500
