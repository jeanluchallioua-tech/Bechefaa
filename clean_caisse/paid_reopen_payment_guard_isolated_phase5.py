"""Phase 5 — garde-fou isolé pour l'état paiement après réouverture.

INACTIF : module non importé / non enregistré dans wsgi_caisse.py.

But strict : empêcher qu'une commande normale non payée soit reclassée à tort
``PARTIELLEMENT PAYÉE`` après modification, tout en laissant intact le flux déjà
validé des commandes réellement payées puis rouvertes.

Aucun changement du ledger, des montants, du Z, de la cuisine ou des tickets.
"""


def _response_status(result):
    response = result[0] if isinstance(result, tuple) else result
    status = result[1] if isinstance(result, tuple) and len(result) > 1 else getattr(response, "status_code", 200)
    try:
        return int(status)
    except Exception:
        return 200


def register_paid_reopen_payment_guard_isolated_phase5(app, db, ensure_order_schema):
    original_update = app.view_functions.get("update_order")
    if original_update is None:
        raise RuntimeError("Route update_order introuvable")

    def guarded_paid_reopen_update_phase5(order_id, *args, **kwargs):
        snapshot = None
        try:
            with db() as conn:
                ensure_order_schema(conn)
                snapshot = conn.execute(
                    "SELECT status,paid_amount,payment_status,z_closure_id FROM caisse_orders WHERE id=%s",
                    (order_id,),
                ).fetchone()
        except Exception:
            snapshot = None

        result = original_update(order_id, *args, **kwargs)
        if not (200 <= _response_status(result) < 300) or not snapshot:
            return result

        try:
            pre_status = str(snapshot["status"] or "").strip()
            pre_payment_status_raw = snapshot["payment_status"]
            pre_payment_status = str(pre_payment_status_raw or "").strip().upper()
            pre_z = snapshot["z_closure_id"]
            try:
                pre_paid_amount = float(snapshot["paid_amount"] or 0)
            except (TypeError, ValueError):
                pre_paid_amount = 0.0

            # Une vraie réouverture payée est laissée entièrement au flux validé.
            genuine_paid_reopen = (
                pre_status == "Terminée"
                and pre_z is None
                and (
                    pre_paid_amount > 0
                    or pre_payment_status in {
                        "PAYÉE",
                        "PARTIELLEMENT PAYÉE",
                        "PARTIELLEMENT REMBOURSÉE",
                        "REMBOURSÉE",
                    }
                )
            )
            if genuine_paid_reopen:
                return result

            # Cas protégé : commande normale sans trace de paiement. Si le wrapper
            # historique vient de la marquer PARTIELLEMENT PAYÉE, restaurer
            # uniquement son état paiement antérieur.
            if pre_z is None and pre_paid_amount <= 0 and pre_payment_status not in {
                "PAYÉE",
                "PARTIELLEMENT PAYÉE",
                "PARTIELLEMENT REMBOURSÉE",
                "REMBOURSÉE",
            }:
                with db() as conn:
                    ensure_order_schema(conn)
                    current = conn.execute(
                        "SELECT status,payment_status,paid_amount,z_closure_id FROM caisse_orders WHERE id=%s",
                        (order_id,),
                    ).fetchone()
                    if not current or current["z_closure_id"] is not None:
                        return result
                    current_payment_status = str(current["payment_status"] or "").strip().upper()
                    try:
                        current_paid_amount = float(current["paid_amount"] or 0)
                    except (TypeError, ValueError):
                        current_paid_amount = 0.0
                    if current_payment_status == "PARTIELLEMENT PAYÉE" and current_paid_amount <= 0:
                        conn.execute(
                            "UPDATE caisse_orders SET payment_status=%s WHERE id=%s",
                            (pre_payment_status_raw, order_id),
                        )
                        conn.commit()
        except Exception:
            # La modification métier a déjà réussi : le garde-fou reste non bloquant.
            pass

        return result

    guarded_paid_reopen_update_phase5.__name__ = "guarded_paid_reopen_update_phase5"
    app.view_functions["update_order"] = guarded_paid_reopen_update_phase5
