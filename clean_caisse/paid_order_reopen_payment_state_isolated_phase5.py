"""Phase 5 — cohérence paiement/statut après modification d'une commande déjà payée.

INACTIF : ce module n'est ni importé ni enregistré dans wsgi_caisse.py.

Objectif :
- après réouverture d'une commande déjà payée, refléter réellement en base
  si un complément reste à encaisser ;
- si aucun complément n'est dû, conserver PAYÉE ;
- lorsqu'une commande déjà intégralement payée est de nouveau déclarée prête
  en cuisine, la faire repasser automatiquement à Terminée ;
- ne toucher ni au ledger des paiements, ni aux montants encaissés, ni au Z.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


CENT = Decimal("0.01")
TERMINAL_PAYMENT_STATUSES = {"PAYÉE", "PARTIELLEMENT REMBOURSÉE", "REMBOURSÉE"}


def _money(value):
    try:
        return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")


def _response_status(result):
    response = result[0] if isinstance(result, tuple) else result
    status = result[1] if isinstance(result, tuple) and len(result) > 1 else getattr(response, "status_code", 200)
    try:
        return int(status)
    except Exception:
        return 200


def register_paid_order_reopen_payment_state_isolated_phase5(app, db, ensure_order_schema):
    original_update = app.view_functions.get("update_order")
    original_finish = app.view_functions.get("finish_kitchen_order")
    if original_update is None:
        raise RuntimeError("Route update_order introuvable")
    if original_finish is None:
        raise RuntimeError("Route finish_kitchen_order introuvable")

    def update_order_payment_state_phase5(order_id, *args, **kwargs):
        result = original_update(order_id, *args, **kwargs)
        if not (200 <= _response_status(result) < 300):
            return result

        try:
            with db() as conn:
                ensure_order_schema(conn)
                row = conn.execute(
                    "SELECT status,total,paid_amount,payment_status,z_closure_id FROM caisse_orders WHERE id=%s",
                    (order_id,),
                ).fetchone()
                if not row or row["z_closure_id"] is not None:
                    return result

                # Le module de réouverture validé replace une commande payée en
                # « À préparer ». On ne corrige que ce cas précis.
                if str(row["status"] or "") != "À préparer":
                    return result

                total = _money(row["total"])
                paid = _money(row["paid_amount"])
                new_payment_status = "PAYÉE" if paid >= total else "PARTIELLEMENT PAYÉE"

                if str(row["payment_status"] or "") != new_payment_status:
                    conn.execute(
                        "UPDATE caisse_orders SET payment_status=%s WHERE id=%s",
                        (new_payment_status, order_id),
                    )
                    conn.commit()
        except Exception:
            # Compatibilité non bloquante : la modification principale a déjà
            # réussi. Une erreur ici ne doit jamais annuler l'opération métier.
            pass

        return result

    def finish_kitchen_order_payment_state_phase5(order_id, *args, **kwargs):
        result = original_finish(order_id, *args, **kwargs)
        if not (200 <= _response_status(result) < 300):
            return result

        try:
            with db() as conn:
                ensure_order_schema(conn)
                row = conn.execute(
                    "SELECT status,payment_status,z_closure_id FROM caisse_orders WHERE id=%s",
                    (order_id,),
                ).fetchone()
                if not row or row["z_closure_id"] is not None:
                    return result

                if (
                    str(row["status"] or "") == "Prête"
                    and str(row["payment_status"] or "").upper() in TERMINAL_PAYMENT_STATUSES
                ):
                    conn.execute(
                        "UPDATE caisse_orders SET status='Terminée' WHERE id=%s",
                        (order_id,),
                    )
                    conn.commit()
        except Exception:
            pass

        return result

    update_order_payment_state_phase5.__name__ = "update_order_payment_state_phase5"
    finish_kitchen_order_payment_state_phase5.__name__ = "finish_kitchen_order_payment_state_phase5"
    app.view_functions["update_order"] = update_order_payment_state_phase5
    app.view_functions["finish_kitchen_order"] = finish_kitchen_order_payment_state_phase5
