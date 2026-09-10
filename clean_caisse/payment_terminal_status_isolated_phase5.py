"""Phase 5 — synchronisation isolée du statut terminal après encaissement.

INACTIF : ce module n'est ni importé ni enregistré dans wsgi_caisse.py.

Objectifs :
- une commande cuisine au statut ``Prête`` devient ``Terminée`` après un
  encaissement complet validé ;
- un remboursement ultérieur ne rouvre jamais le cycle cuisine ;
- permettre une réparation explicite et limitée des commandes déjà PAYÉES ou
  REMBOURSÉES qui seraient encore restées ``Prête`` avant l'activation.

Aucune modification du moteur Z, aucun changement des montants de paiement,
aucune écriture dans le journal financier.
"""
import time

from flask import jsonify


TERMINAL_PAYMENT_STATUSES = {
    "PAYÉE",
    "PARTIELLEMENT REMBOURSÉE",
    "REMBOURSÉE",
}


def _sync_ready_to_finished(conn, order_id):
    row = conn.execute(
        "SELECT id,status,payment_status,z_closure_id FROM caisse_orders WHERE id=%s FOR UPDATE",
        (order_id,),
    ).fetchone()
    if not row:
        return False
    if row.get("z_closure_id") is not None:
        return False

    status = str(row.get("status") or "").strip()
    payment_status = str(row.get("payment_status") or "").strip().upper()
    if status != "Prête" or payment_status not in TERMINAL_PAYMENT_STATUSES:
        return False

    now = int(time.time() * 1000)
    conn.execute(
        "UPDATE caisse_orders SET status='Terminée',updated_at=%s WHERE id=%s",
        (now, order_id),
    )
    return True


def register_payment_terminal_status_isolated_phase5(app, db, ensure_order_schema):
    original_payment = app.view_functions.get("set_order_payment_phase41")
    original_refund = app.view_functions.get("refund_phase44")
    if original_payment is None or original_refund is None:
        raise RuntimeError("Routes paiement/remboursement introuvables")

    def payment_terminal_status_phase5(order_id, *args, **kwargs):
        response = app.make_response(original_payment(order_id, *args, **kwargs))
        if 200 <= response.status_code < 300:
            try:
                with db() as conn:
                    with conn.transaction():
                        ensure_order_schema(conn)
                        _sync_ready_to_finished(conn, order_id)
            except Exception:
                # Un encaissement déjà réussi ne doit jamais être transformé en
                # erreur par cette synchronisation secondaire de statut.
                return response
        return response

    def refund_terminal_status_phase5(order_id, *args, **kwargs):
        response = app.make_response(original_refund(order_id, *args, **kwargs))
        if 200 <= response.status_code < 300:
            try:
                with db() as conn:
                    with conn.transaction():
                        ensure_order_schema(conn)
                        _sync_ready_to_finished(conn, order_id)
            except Exception:
                return response
        return response

    @app.post("/api/phase5/payment-terminal-status/repair")
    def repair_payment_terminal_status_phase5():
        """Répare uniquement les commandes ``Prête`` déjà financièrement closes.

        Cette route ne touche ni aux montants, ni aux transactions, ni au Z.
        Elle est volontairement explicite (POST) et idempotente.
        """
        try:
            with db() as conn:
                with conn.transaction():
                    ensure_order_schema(conn)
                    rows = conn.execute(
                        """
                        SELECT id,num,status,payment_status,z_closure_id
                        FROM caisse_orders
                        WHERE status='Prête'
                          AND UPPER(COALESCE(payment_status,'')) = ANY(%s)
                          AND z_closure_id IS NULL
                        ORDER BY num
                        FOR UPDATE
                        """,
                        (list(TERMINAL_PAYMENT_STATUSES),),
                    ).fetchall()
                    repaired = []
                    for row in rows:
                        if _sync_ready_to_finished(conn, row["id"]):
                            repaired.append(int(row["num"]))
            return jsonify({"ok": True, "repaired": repaired, "count": len(repaired)})
        except Exception as exc:
            return jsonify({"ok": False, "error": "Réparation statut terminal impossible", "detail": str(exc)}), 500

    payment_terminal_status_phase5.__name__ = "payment_terminal_status_phase5"
    refund_terminal_status_phase5.__name__ = "refund_terminal_status_phase5"
    app.view_functions["set_order_payment_phase41"] = payment_terminal_status_phase5
    app.view_functions["refund_phase44"] = refund_terminal_status_phase5
