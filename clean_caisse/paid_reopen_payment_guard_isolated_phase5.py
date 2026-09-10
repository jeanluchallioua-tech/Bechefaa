"""Phase 5 — garde-fou isolé pour l'état paiement après réouverture.

INACTIF : module non importé / non enregistré dans wsgi_caisse.py.

But strict : empêcher le wrapper historique de recalculer l'état paiement d'une
commande normale non payée. Le recalcul n'est autorisé que si, AVANT la
modification, la commande est réellement Terminée, non clôturée par Z et porte
une trace de paiement positive / un état paiement terminal.

Aucun changement du ledger, des montants, du Z, de la cuisine ou des tickets.
"""


def register_paid_reopen_payment_guard_isolated_phase5(app, db, ensure_order_schema):
    original_update = app.view_functions.get("update_order")
    if original_update is None:
        raise RuntimeError("Route update_order introuvable")

    def guarded_paid_reopen_update_phase5(order_id, *args, **kwargs):
        allow_paid_reopen_state = False
        try:
            with db() as conn:
                ensure_order_schema(conn)
                row = conn.execute(
                    "SELECT status,paid_amount,payment_status,z_closure_id FROM caisse_orders WHERE id=%s",
                    (order_id,),
                ).fetchone()
                if row and row["z_closure_id"] is None:
                    status = str(row["status"] or "").strip()
                    payment_status = str(row["payment_status"] or "").strip().upper()
                    try:
                        paid_amount = float(row["paid_amount"] or 0)
                    except (TypeError, ValueError):
                        paid_amount = 0.0
                    allow_paid_reopen_state = (
                        status == "Terminée"
                        and (
                            paid_amount > 0
                            or payment_status in {"PAYÉE", "PARTIELLEMENT PAYÉE", "PARTIELLEMENT REMBOURSÉE", "REMBOURSÉE"}
                        )
                    )
        except Exception:
            allow_paid_reopen_state = False

        if allow_paid_reopen_state:
            return original_update(order_id, *args, **kwargs)

        # Pour une commande normale, neutraliser uniquement le wrapper de
        # recalcul paiement installé précédemment en appelant son handler aval.
        downstream = getattr(original_update, "_paid_reopen_downstream", None)
        if downstream is not None:
            return downstream(order_id, *args, **kwargs)
        return original_update(order_id, *args, **kwargs)

    # Marqueur utilisé uniquement pour diagnostic/chaînage explicite.
    guarded_paid_reopen_update_phase5.__name__ = "guarded_paid_reopen_update_phase5"
    app.view_functions["update_order"] = guarded_paid_reopen_update_phase5
