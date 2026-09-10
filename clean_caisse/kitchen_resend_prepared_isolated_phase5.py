"""Phase 5 — préserver les plats déjà préparés lors d'un renvoi cuisine.

Module isolé et INACTIF : non importé / non enregistré dans wsgi_caisse.py.

Objectif :
- lors d'une modification d'une commande déjà « Prête », conserver comme préparées
  les lignes qui existaient avant la modification et qui étaient déjà préparées ;
- les nouvelles lignes ajoutées restent prepared=FALSE ;
- ne toucher ni au paiement, ni au Z, ni au flux normal des autres commandes.
"""
from flask import request


def register_kitchen_resend_prepared_isolated_phase5(app, db):
    original_update = app.view_functions.get("update_order")
    if original_update is None:
        raise RuntimeError("Route update_order introuvable")

    def update_order_preserve_prepared_phase5(order_id, *args, **kwargs):
        # Avant la modification, mémoriser uniquement les line_id déjà préparés
        # si la commande est dans l'état cuisine « Prête ».
        prepared_line_ids = set()
        try:
            with db() as conn:
                order = conn.execute(
                    "SELECT status FROM caisse_orders WHERE id=%s",
                    (order_id,),
                ).fetchone()
                if order and order["status"] == "Prête":
                    rows = conn.execute(
                        "SELECT line_id FROM caisse_order_items WHERE order_id=%s AND prepared=TRUE",
                        (order_id,),
                    ).fetchall()
                    prepared_line_ids = {str(row["line_id"]) for row in rows}
        except Exception:
            # Le handler historique reste l'autorité pour produire l'erreur réelle.
            prepared_line_ids = set()

        response = original_update(order_id, *args, **kwargs)

        # Ne rien modifier si l'enregistrement historique a échoué.
        flask_response = response[0] if isinstance(response, tuple) else response
        status_code = response[1] if isinstance(response, tuple) and len(response) > 1 else getattr(flask_response, "status_code", 200)
        if int(status_code or 200) >= 400 or not prepared_line_ids:
            return response

        # Le handler historique réinsère toutes les lignes en FALSE.
        # On rétablit TRUE seulement pour les line_id qui étaient réellement
        # préparés avant la modification. Toute nouvelle ligne reste FALSE.
        try:
            with db() as conn:
                with conn.transaction():
                    conn.execute(
                        "UPDATE caisse_order_items SET prepared=TRUE WHERE order_id=%s AND line_id = ANY(%s)",
                        (order_id, list(prepared_line_ids)),
                    )
        except Exception:
            # Ne jamais transformer une modification réussie en panne globale.
            # Ce module est volontairement limité au marquage cuisine.
            pass

        return response

    update_order_preserve_prepared_phase5.__name__ = "update_order_preserve_prepared_phase5"
    app.view_functions["update_order"] = update_order_preserve_prepared_phase5
