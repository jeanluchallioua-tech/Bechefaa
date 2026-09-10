"""Phase 5 — statut cuisine « Prête » au lieu de « Terminée ».

Module isolé et INACTIF : non importé / non enregistré dans wsgi_caisse.py.

Objectif :
- conserver les colonnes À préparer / En préparation ;
- faire passer une commande entièrement préparée au statut « Prête » ;
- afficher la 3e colonne « Prête » ;
- ne plus utiliser « Terminée » comme sortie normale de la cuisine ;
- laisser l'encaissement et l'historique inchangés pour ce test isolé.
"""
import time

from flask import jsonify, request


def register_kitchen_ready_isolated_phase5(app, db, ensure_order_schema):
    original_finish = app.view_functions.get("finish_kitchen_order")
    if original_finish is None:
        raise RuntimeError("Route finish_kitchen_order introuvable")

    def finish_kitchen_order_ready_phase5(order_id, *args, **kwargs):
        now = int(time.time() * 1000)
        try:
            with db() as conn:
                with conn.transaction():
                    ensure_order_schema(conn)
                    order = conn.execute(
                        "SELECT id,num,status FROM caisse_orders WHERE id=%s FOR UPDATE",
                        (order_id,),
                    ).fetchone()
                    if not order:
                        return jsonify({"ok": False, "error": "Commande introuvable"}), 404

                    if order["status"] == "Prête":
                        return jsonify({
                            "ok": True,
                            "id": order_id,
                            "num": order["num"],
                            "status": "Prête",
                        }), 200

                    if order["status"] not in ("À préparer", "En préparation"):
                        return jsonify({
                            "ok": False,
                            "error": "Cette commande ne peut pas être déclarée prête",
                            "status": order["status"],
                        }), 409

                    remaining = conn.execute(
                        "SELECT COUNT(*) AS n FROM caisse_order_items WHERE order_id=%s AND prepared=FALSE",
                        (order_id,),
                    ).fetchone()["n"]
                    if int(remaining) > 0:
                        return jsonify({
                            "ok": False,
                            "error": "Tous les plats doivent être cochés avant de déclarer la commande prête",
                            "remaining": int(remaining),
                        }), 409

                    conn.execute(
                        "UPDATE caisse_orders SET status='Prête',updated_at=%s WHERE id=%s",
                        (now, order_id),
                    )

            return jsonify({
                "ok": True,
                "id": order_id,
                "num": order["num"],
                "status": "Prête",
            }), 200
        except Exception as exc:
            return jsonify({
                "ok": False,
                "error": "Mise en statut Prête impossible",
                "detail": str(exc),
            }), 500

    finish_kitchen_order_ready_phase5.__name__ = "finish_kitchen_order_ready_phase5"
    app.view_functions["finish_kitchen_order"] = finish_kitchen_order_ready_phase5

    @app.after_request
    def kitchen_ready_ui_phase5(response):
        if request.path != "/cuisine-preparation" or response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        html = html.replace("<h2>Terminée</h2>", "<h2>Prête</h2>")
        html = html.replace("o.status==='Terminée'", "o.status==='Prête'")
        html = html.replace("done=d.orders.filter(o=>o.status==='Terminée')", "done=d.orders.filter(o=>o.status==='Prête')")
        html = html.replace(">Terminer</button>", ">Déclarer prête</button>")
        html = html.replace("utilisez « Terminer »", "utilisez « Déclarer prête »")
        html = html.replace("Impossible de terminer : ", "Impossible de déclarer prête : ")

        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
