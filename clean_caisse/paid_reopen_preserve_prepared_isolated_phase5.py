"""Phase 5 — préserver les plats déjà préparés lors de la réouverture d'une commande payée.

INACTIF : module isolé, non importé / non enregistré dans wsgi_caisse.py.

Objectif strict :
- pour une commande déjà Terminée, mémoriser les line_id préparés avant modification ;
- après une réouverture réussie vers « À préparer », rétablir prepared=TRUE uniquement
  sur les lignes conservées ayant le même line_id ;
- les nouvelles lignes restent prepared=FALSE ;
- ne toucher ni au paiement, ni au Z, ni aux autres commandes.
"""


def register_paid_reopen_preserve_prepared_isolated_phase5(app, db):
    original_update = app.view_functions.get("update_order")
    if original_update is None:
        raise RuntimeError("Route update_order introuvable")

    def update_order_paid_reopen_preserve_prepared_phase5(order_id, *args, **kwargs):
        prepared_line_ids = set()
        was_terminated = False

        try:
            with db() as conn:
                order = conn.execute(
                    "SELECT status,z_closure_id FROM caisse_orders WHERE id=%s",
                    (order_id,),
                ).fetchone()
                if order and str(order["status"] or "") == "Terminée" and order["z_closure_id"] is None:
                    was_terminated = True
                    rows = conn.execute(
                        "SELECT line_id FROM caisse_order_items WHERE order_id=%s AND prepared=TRUE",
                        (order_id,),
                    ).fetchall()
                    prepared_line_ids = {str(row["line_id"]) for row in rows if row["line_id"] is not None}
        except Exception:
            prepared_line_ids = set()
            was_terminated = False

        response = original_update(order_id, *args, **kwargs)
        flask_response = response[0] if isinstance(response, tuple) else response
        status_code = response[1] if isinstance(response, tuple) and len(response) > 1 else getattr(flask_response, "status_code", 200)
        if int(status_code or 200) >= 400 or not was_terminated or not prepared_line_ids:
            return response

        try:
            with db() as conn:
                with conn.transaction():
                    current = conn.execute(
                        "SELECT status,z_closure_id FROM caisse_orders WHERE id=%s FOR UPDATE",
                        (order_id,),
                    ).fetchone()
                    if current and str(current["status"] or "") == "À préparer" and current["z_closure_id"] is None:
                        conn.execute(
                            "UPDATE caisse_order_items SET prepared=TRUE WHERE order_id=%s AND line_id = ANY(%s)",
                            (order_id, list(prepared_line_ids)),
                        )
        except Exception:
            pass

        return response

    update_order_paid_reopen_preserve_prepared_phase5.__name__ = "update_order_paid_reopen_preserve_prepared_phase5"
    app.view_functions["update_order"] = update_order_paid_reopen_preserve_prepared_phase5
