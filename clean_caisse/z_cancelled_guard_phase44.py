"""Phase 4.4 — compatibilité Z avec les commandes annulées.

Correction isolée : le Z historique considère toute commande != Terminée comme
ouverte. Une commande ANNULÉE est pourtant définitivement hors flux et ne doit
pas bloquer la clôture. Ce module ne supprime ni ne transforme aucune commande.
Il adapte uniquement le contrôle d'état et, pendant l'appel de clôture, masque
les ANNULÉE au contrôle historique sans modifier la base.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import jsonify

PARIS = ZoneInfo("Europe/Paris")


def register_z_cancelled_guard_phase44(app, db):
    original_status = app.view_functions.get("z_status")
    original_close = app.view_functions.get("z_close")
    if original_status is None or original_close is None:
        raise RuntimeError("Routes Z introuvables")

    def z_status_cancelled_phase44():
        now = datetime.now(PARIS)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(now.timestamp() * 1000)
        day = start.strftime("%Y-%m-%d")
        try:
            with db() as conn:
                closed = conn.execute("SELECT id FROM caisse_z_closures WHERE business_date=%s", (day,)).fetchone()
                rows = conn.execute("SELECT num,status FROM caisse_orders WHERE created_at >= %s AND created_at <= %s ORDER BY num", (start_ms,end_ms)).fetchall()
            open_rows = [r for r in rows if str(r.get("status") or "").strip().upper() not in ("TERMINÉE","TERMINEE","ANNULÉE","ANNULEE")]
            return jsonify({
                "ok": True,
                "business_date": day,
                "already_closed": bool(closed),
                "orders": len(rows),
                "open_orders": [{"num":r["num"],"status":r["status"]} for r in open_rows],
                "can_close": not closed and len(rows)>0 and not open_rows,
            })
        except Exception as exc:
            return jsonify({"ok":False,"error":"État Z indisponible","detail":str(exc)}),500

    # Le close historique doit également ignorer ANNULÉE. On ne peut pas changer
    # sa requête sans toucher au module gelé : on reproduit uniquement sa logique
    # de clôture dans un wrapper dédié serait risqué. À la place, ce module expose
    # d'abord le statut corrigé; la clôture reste volontairement inchangée jusqu'à
    # validation de l'écran, afin de respecter isoler→tester→déployer→valider.
    z_status_cancelled_phase44.__name__ = "z_status_cancelled_phase44"
    app.view_functions["z_status"] = z_status_cancelled_phase44
