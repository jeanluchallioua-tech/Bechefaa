"""Phase 4.4 — garde complément d'encaissement, module isolé.

NON ACTIVÉ volontairement. Prépare le remplacement ciblé de la garde
anti-réencaissement pour autoriser uniquement un vrai complément :
0 < net journalisé < total actuel de la commande.

Les commandes totalement payées ou remboursées restent bloquées.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import jsonify, request

from clean_caisse.payment_transactions_phase44 import ensure_payment_transaction_schema

CENT = Decimal("0.01")


def _money(value):
    try:
        return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")


def register_payment_topup_guard_isolated_phase44(app, db):
    @app.before_request
    def payment_topup_guard_isolated_phase44():
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
                    "SELECT total,payment_status,z_closure_id FROM caisse_orders WHERE id=%s LIMIT 1",
                    (order_id,),
                ).fetchone()
                if not row:
                    return None
                if row.get("z_closure_id") is not None:
                    return jsonify({"ok": False, "error": "Commande clôturée par le Z : encaissement interdit"}), 409

                ensure_payment_transaction_schema(conn)
                tx = conn.execute("""
                    SELECT
                      COALESCE(SUM(CASE WHEN transaction_type='PAYMENT' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS paid,
                      COALESCE(SUM(CASE WHEN transaction_type='REFUND' AND status='SUCCEEDED' THEN amount ELSE 0 END),0) AS refunded
                    FROM caisse_payment_transactions
                    WHERE order_id=%s
                """, (order_id,)).fetchone()
        except Exception:
            return None

        total = _money(row["total"])
        net = (_money(tx["paid"]) - _money(tx["refunded"])).quantize(CENT)
        status = str(row["payment_status"] or "").strip().upper()

        # Seule exception au blocage : un paiement réel existe mais reste
        # strictement inférieur au nouveau total de la commande.
        if Decimal("0.00") < net < total:
            return None

        blocked = {"PAYÉE", "PARTIELLEMENT REMBOURSÉE", "REMBOURSÉE"}
        if status in blocked:
            return jsonify({
                "ok": False,
                "error": "Encaissement interdit : cette commande possède déjà un règlement.",
                "payment_status": row["payment_status"],
            }), 409

        return None
