"""Phase 4.4 — garde serveur isolée contre le ré-encaissement.

Ne modifie pas le moteur Phase 4.3. Intercepte uniquement les PUT de paiement
pour une commande déjà payée/remboursée et renvoie 409 avant le handler.
"""
from flask import jsonify, request


def register_payment_refund_guard_phase44(app, db):
    @app.before_request
    def payment_refund_guard_phase44():
        if request.method != "PUT":
            return None

        prefix = "/api/orders/"
        suffix = "/payment-phase41"
        path = request.path
        if not (path.startswith(prefix) and path.endswith(suffix)):
            return None

        order_id = path[len(prefix):-len(suffix)]
        if not order_id or "/" in order_id:
            return None

        try:
            with db() as conn:
                row = conn.execute(
                    "SELECT payment_status FROM caisse_orders WHERE id=%s LIMIT 1",
                    (order_id,),
                ).fetchone()
        except Exception:
            # Fail open here so this supplemental guard cannot break the stable
            # Phase 4.3 payment route if its own lookup is unavailable.
            return None

        if not row:
            return None

        status = str(row["payment_status"] or "").strip().upper()
        blocked = {"PAYÉE", "PARTIELLEMENT REMBOURSÉE", "REMBOURSÉE"}
        if status in blocked:
            return jsonify({
                "ok": False,
                "error": "Encaissement interdit : cette commande possède déjà un règlement.",
                "payment_status": row["payment_status"],
            }), 409

        return None
