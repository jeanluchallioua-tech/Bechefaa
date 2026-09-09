"""Phase 4.4 — raccord isolé du comptage espèces au Z existant.

Ne modifie pas cash_z_phase35.py. Enveloppe uniquement l'action de clôture Z :
- exige le comptage espèces définitif du jour ;
- laisse le Z historique effectuer sa clôture ;
- conserve ensuite une copie immuable des données espèces liée à l'id du Z.
"""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from flask import jsonify

PARIS = ZoneInfo("Europe/Paris")


def _ensure_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS caisse_z_cash_details (
            id BIGSERIAL PRIMARY KEY,
            z_closure_id BIGINT NOT NULL UNIQUE,
            business_date TEXT NOT NULL UNIQUE,
            opening_amount NUMERIC(12,2) NOT NULL,
            cash_sales NUMERIC(12,2) NOT NULL,
            theoretical_amount NUMERIC(12,2) NOT NULL,
            counted_amount NUMERIC(12,2) NOT NULL,
            difference_amount NUMERIC(12,2) NOT NULL,
            counted_at BIGINT NOT NULL,
            linked_at BIGINT NOT NULL
        )
    """)


def register_z_cash_link_phase44(app, db):
    # cash_z_phase35 est enregistré avant ce module dans wsgi_caisse.py.
    original_close = app.view_functions.get("z_close")
    if original_close is None:
        raise RuntimeError("Route Z z_close introuvable")

    def linked_z_close_phase44(*args, **kwargs):
        day = datetime.now(PARIS).strftime("%Y-%m-%d")

        # Précondition : le comptage définitif doit exister avant le Z.
        try:
            with db() as conn:
                _ensure_schema(conn)
                conn.commit()
                count = conn.execute("""
                    SELECT business_date,opening_amount,cash_sales,theoretical_amount,
                           counted_amount,difference_amount,counted_at
                    FROM caisse_cash_counts WHERE business_date=%s LIMIT 1
                """, (day,)).fetchone()
            if not count:
                return jsonify({
                    "ok": False,
                    "error": "Z refusé : le comptage espèces définitif doit être enregistré avant la clôture."
                }), 409
        except Exception as exc:
            return jsonify({"ok":False,"error":"Contrôle espèces avant Z impossible","detail":str(exc)}),500

        # Le Z historique reste seul responsable de la clôture des commandes.
        response = original_close(*args, **kwargs)
        flask_response = app.make_response(response)
        if flask_response.status_code < 200 or flask_response.status_code >= 300:
            return flask_response

        try:
            payload = flask_response.get_json(silent=True) or {}
            closure_id = payload.get("closure_id")
            if not closure_id:
                return jsonify({"ok":False,"error":"Z effectué mais identifiant de clôture introuvable pour le raccord espèces"}),500

            linked_at = int(datetime.now(PARIS).timestamp() * 1000)
            with db() as conn:
                with conn.transaction():
                    _ensure_schema(conn)
                    existing = conn.execute(
                        "SELECT id FROM caisse_z_cash_details WHERE z_closure_id=%s OR business_date=%s FOR UPDATE",
                        (closure_id, day),
                    ).fetchone()
                    if not existing:
                        conn.execute("""
                            INSERT INTO caisse_z_cash_details
                            (z_closure_id,business_date,opening_amount,cash_sales,theoretical_amount,
                             counted_amount,difference_amount,counted_at,linked_at)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """, (closure_id,day,count["opening_amount"],count["cash_sales"],
                              count["theoretical_amount"],count["counted_amount"],
                              count["difference_amount"],count["counted_at"],linked_at))

            payload["cash"] = {
                "opening_amount": float(Decimal(str(count["opening_amount"]))),
                "cash_sales": float(Decimal(str(count["cash_sales"]))),
                "theoretical_amount": float(Decimal(str(count["theoretical_amount"]))),
                "counted_amount": float(Decimal(str(count["counted_amount"]))),
                "difference_amount": float(Decimal(str(count["difference_amount"])))
            }
            payload["cash_linked"] = True
            return jsonify(payload), flask_response.status_code
        except Exception as exc:
            # Le Z historique peut déjà être clôturé : signal explicite, aucune fausse réussite.
            return jsonify({
                "ok": False,
                "error": "Z effectué mais raccord espèces non enregistré",
                "detail": str(exc),
                "z_already_closed": True
            }), 500

    linked_z_close_phase44.__name__ = "linked_z_close_phase44"
    app.view_functions["z_close"] = linked_z_close_phase44

    @app.get("/maintenance/phase44/z-cash-link-status")
    def z_cash_link_status_phase44():
        day = datetime.now(PARIS).strftime("%Y-%m-%d")
        try:
            with db() as conn:
                _ensure_schema(conn); conn.commit()
                z = conn.execute("SELECT id,business_date,closed_at,total_ttc FROM caisse_z_closures WHERE business_date=%s", (day,)).fetchone()
                cash = conn.execute("SELECT * FROM caisse_z_cash_details WHERE business_date=%s", (day,)).fetchone()
            return jsonify({"ok":True,"business_date":day,"z":dict(z) if z else None,"cash_linked":bool(cash),"cash":dict(cash) if cash else None})
        except Exception as exc:
            return jsonify({"ok":False,"error":"État raccord Z/espèces indisponible","detail":str(exc)}),500
