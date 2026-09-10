"""Phase 5 — terminer une commande Prête après paiement du complément.

INACTIF : module isolé, non importé / non enregistré dans wsgi_caisse.py.

Objectif strict :
- envelopper la route d'encaissement telle qu'elle existe après le module MIXTE ;
- après un encaissement réussi, si la commande est Prête et réellement PAYÉE,
  la passer à Terminée ;
- ne toucher ni aux montants, ni au journal financier, ni au Z, ni aux remboursements.
"""
import time


def register_payment_topup_terminal_sync_isolated_phase5(app, db, ensure_order_schema):
    original_payment = app.view_functions.get("set_order_payment_phase41")
    if original_payment is None:
        raise RuntimeError("Route paiement introuvable")

    def payment_topup_terminal_sync_phase5(order_id, *args, **kwargs):
        response = app.make_response(original_payment(order_id, *args, **kwargs))
        if not (200 <= response.status_code < 300):
            return response

        try:
            with db() as conn:
                with conn.transaction():
                    ensure_order_schema(conn)
                    row = conn.execute(
                        "SELECT status,payment_status,z_closure_id FROM caisse_orders WHERE id=%s FOR UPDATE",
                        (order_id,),
                    ).fetchone()
                    if not row or row["z_closure_id"] is not None:
                        return response
                    if (
                        str(row["status"] or "") == "Prête"
                        and str(row["payment_status"] or "").strip().upper() == "PAYÉE"
                    ):
                        conn.execute(
                            "UPDATE caisse_orders SET status='Terminée',updated_at=%s WHERE id=%s",
                            (int(time.time() * 1000), order_id),
                        )
        except Exception:
            # Le paiement réussi reste prioritaire : cette synchronisation de
            # statut ne doit jamais transformer un encaissement en erreur.
            pass

        return response

    payment_topup_terminal_sync_phase5.__name__ = "payment_topup_terminal_sync_phase5"
    app.view_functions["set_order_payment_phase41"] = payment_topup_terminal_sync_phase5
