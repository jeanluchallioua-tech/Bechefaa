"""Phase 5 — préserver l'avancement cuisine lors d'une modification En préparation.

INACTIF : module non importé / non enregistré dans wsgi_caisse.py.

But strict :
- si une commande est « En préparation » avant modification, mémoriser ses lignes
  déjà prepared=TRUE ;
- après modification réussie, restaurer prepared=TRUE uniquement sur ces line_id ;
- laisser les nouvelles lignes prepared=FALSE ;
- conserver le statut « En préparation » si au moins une ancienne ligne préparée
  a réellement été retrouvée après la modification.

Aucun changement paiement, ledger, Z, ticket ou autre commande.
"""


def _response_status(result):
    response = result[0] if isinstance(result, tuple) else result
    status = result[1] if isinstance(result, tuple) and len(result) > 1 else getattr(response, "status_code", 200)
    try:
        return int(status)
    except Exception:
        return 200


def register_kitchen_in_progress_preserve_isolated_phase5(app, db):
    original_update = app.view_functions.get("update_order")
    if original_update is None:
        raise RuntimeError("Route update_order introuvable")

    def update_order_in_progress_preserve_phase5(order_id, *args, **kwargs):
        prepared_line_ids = set()
        was_in_progress = False
        try:
            with db() as conn:
                order = conn.execute(
                    "SELECT status,z_closure_id FROM caisse_orders WHERE id=%s",
                    (order_id,),
                ).fetchone()
                if order and order["z_closure_id"] is None and str(order["status"] or "") == "En préparation":
                    was_in_progress = True
                    rows = conn.execute(
                        "SELECT line_id FROM caisse_order_items WHERE order_id=%s AND prepared=TRUE",
                        (order_id,),
                    ).fetchall()
                    prepared_line_ids = {str(row["line_id"]) for row in rows if row["line_id"] is not None}
        except Exception:
            was_in_progress = False
            prepared_line_ids = set()

        result = original_update(order_id, *args, **kwargs)
        if not was_in_progress or not prepared_line_ids or not (200 <= _response_status(result) < 300):
            return result

        try:
            with db() as conn:
                with conn.transaction():
                    current = conn.execute(
                        "SELECT status,z_closure_id FROM caisse_orders WHERE id=%s FOR UPDATE",
                        (order_id,),
                    ).fetchone()
                    if not current or current["z_closure_id"] is not None:
                        return result

                    # Ne restaurer que les anciennes line_id encore présentes.
                    rows = conn.execute(
                        "SELECT line_id FROM caisse_order_items WHERE order_id=%s AND line_id = ANY(%s)",
                        (order_id, list(prepared_line_ids)),
                    ).fetchall()
                    retained = [str(row["line_id"]) for row in rows if row["line_id"] is not None]
                    if not retained:
                        return result

                    conn.execute(
                        "UPDATE caisse_order_items SET prepared=TRUE WHERE order_id=%s AND line_id = ANY(%s)",
                        (order_id, retained),
                    )
                    # Le handler historique repasse la commande à « À préparer ».
                    # Puisqu'une ligne déjà préparée subsiste, restaurer l'état
                    # cuisine antérieur « En préparation ».
                    if str(current["status"] or "") == "À préparer":
                        conn.execute(
                            "UPDATE caisse_orders SET status='En préparation' WHERE id=%s",
                            (order_id,),
                        )
        except Exception:
            # La modification principale reste non bloquante.
            pass

        return result

    update_order_in_progress_preserve_phase5.__name__ = "update_order_in_progress_preserve_phase5"
    app.view_functions["update_order"] = update_order_in_progress_preserve_phase5
