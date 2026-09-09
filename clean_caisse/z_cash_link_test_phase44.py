"""Phase 4.4 — prévisualisation isolée du raccord espèces vers le Z.

Lecture seule : vérifie que le comptage définitif du jour contient tout ce que
le futur raccord Z devra conserver. Ne ferme pas la journée et ne modifie pas
cash_z_phase35.py.
"""
from datetime import datetime
from decimal import Decimal
from html import escape
from zoneinfo import ZoneInfo

from flask import Response

PARIS = ZoneInfo("Europe/Paris")


def _eur(value):
    return f"{Decimal(str(value or 0)):.2f} €".replace(".", ",")


def register_z_cash_link_test_phase44(app, db):
    @app.get("/maintenance/phase44/z-cash-link-test")
    def z_cash_link_test_phase44():
        day = datetime.now(PARIS).strftime("%Y-%m-%d")
        try:
            with db() as conn:
                count = conn.execute("""
                    SELECT business_date,opening_amount,cash_sales,theoretical_amount,
                           counted_amount,difference_amount,counted_at
                    FROM caisse_cash_counts
                    WHERE business_date=%s
                    LIMIT 1
                """, (day,)).fetchone()
                z = conn.execute("""
                    SELECT id,business_date,closed_at,total_ttc
                    FROM caisse_z_closures
                    WHERE business_date=%s
                    LIMIT 1
                """, (day,)).fetchone()
            if not count:
                return Response("Aucun comptage définitif enregistré aujourd'hui.", status=409, mimetype="text/plain")
            rows = [
                ("Fond initial", _eur(count["opening_amount"])),
                ("Ventes espèces", _eur(count["cash_sales"])),
                ("Tiroir théorique", _eur(count["theoretical_amount"])),
                ("Espèces comptées", _eur(count["counted_amount"])),
                ("Écart", _eur(count["difference_amount"])),
            ]
            details = "".join(f'<div class="row"><span>{escape(k)}</span><b>{escape(v)}</b></div>' for k,v in rows)
            z_state = f'Z déjà clôturé aujourd’hui — Z #{z["id"]}' if z else "Z non clôturé aujourd’hui"
            html = f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Prévisualisation raccord Z</title><style>
body{{font-family:Arial,sans-serif;background:#f4f5f7;color:#17191c;padding:22px}}.box{{max-width:680px;margin:auto;background:#fff;border-radius:15px;padding:24px}}.note{{background:#eef6ff;border:1px solid #bfdbfe;border-radius:9px;padding:12px;margin:15px 0}}.ok{{background:#ecfdf5;border:1px solid #86efac;border-radius:9px;padding:12px;margin:15px 0;font-weight:800}}.row{{display:flex;justify-content:space-between;border-top:1px solid #eee;padding:12px 0}}.muted{{color:#64748b}}
</style></head><body><div class="box"><h1>Raccord espèces → Z</h1><p class="muted">Prévisualisation en lecture seule</p><div class="ok">Données espèces prêtes à être rattachées au Z.</div>{details}<div class="note"><b>État :</b> {escape(z_state)}<br><br>Aucune clôture n'est déclenchée par cette page et le Z actuel n'est pas modifié.</div></div></body></html>'''
            return Response(html, content_type="text/html; charset=utf-8")
        except Exception as exc:
            return Response("Prévisualisation raccord Z indisponible : " + escape(str(exc)), status=500, mimetype="text/plain")
