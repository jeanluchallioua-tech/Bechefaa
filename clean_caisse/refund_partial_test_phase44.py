"""Phase 4.4 — remboursement partiel LOCAL de test.

Route volontairement isolée. Elle exige explicitement order_id, transaction_id
et amount. Le moteur stable de remboursement reste l'autorité métier.
"""
from flask import jsonify, request


def register_refund_partial_test_phase44(app):
    @app.get("/api/refund-partial-phase44-test")
    def refund_partial_test_phase44_info():
        return jsonify({
            "ok": True,
            "test_only": True,
            "write": True,
            "method": "POST",
            "target": "/api/orders/<order_id>/refund-phase44",
            "required": ["order_id", "transaction_id", "amount"],
            "note": "Cette route GET n'effectue aucun remboursement. Le POST de test doit etre explicite.",
        })

    @app.post("/api/refund-partial-phase44-test")
    def refund_partial_test_phase44():
        payload = request.get_json(silent=True) or {}
        order_id = str(payload.get("order_id") or "").strip()
        transaction_id = str(payload.get("transaction_id") or "").strip()
        amount = payload.get("amount")
        if not order_id or not transaction_id or amount is None:
            return jsonify({"ok": False, "error": "order_id, transaction_id et amount obligatoires"}), 400

        # Le test délègue au moteur Phase 4.4 déjà validé plutôt que dupliquer
        # la logique financière. Le contexte de requête est réutilisé après
        # remplacement temporaire du JSON par les champs attendus.
        endpoint = app.view_functions.get("refund_phase44")
        if endpoint is None:
            return jsonify({"ok": False, "error": "Moteur remboursement Phase 4.4 indisponible"}), 503

        original_json = request.get_json(silent=True) or {}
        # Flask met le JSON en cache ; on remplace uniquement ce cache pendant
        # l'appel interne puis on le restaure.
        cached = getattr(request, "_cached_json", None)
        try:
            request._cached_json = ({
                "transaction_id": transaction_id,
                "amount": amount,
                "reason": str(original_json.get("reason") or "TEST PHASE 4.4").strip(),
                "created_by": str(original_json.get("created_by") or "TEST").strip(),
            },) * 2
            return endpoint(order_id)
        finally:
            if cached is None:
                try:
                    delattr(request, "_cached_json")
                except AttributeError:
                    pass
            else:
                request._cached_json = cached
