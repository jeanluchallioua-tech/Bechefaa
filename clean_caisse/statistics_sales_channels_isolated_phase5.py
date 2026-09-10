"""Phase 5 — ventilation des statistiques par canal de vente.

INACTIF : ce module n'est ni importé ni enregistré dans wsgi_caisse.py.
Lecture seule côté statistiques. Il ne modifie ni les commandes, ni les paiements,
ni le Z. Il remplace uniquement la ventilation visuelle historique `source` par
les 4 canaux commerciaux : RESTO, SITE, UBER_EATS, DELIVEROO.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask import request

PARIS = ZoneInfo("Europe/Paris")
UTC = ZoneInfo("UTC")
CHANNELS = ("RESTO", "SITE", "UBER_EATS", "DELIVEROO")
LABELS = {
    "RESTO": "Resto",
    "SITE": "Site internet",
    "UBER_EATS": "Uber Eats",
    "DELIVEROO": "Deliveroo",
}


def _period_bounds_from_response(data):
    start = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
    end_inclusive = datetime.strptime(data["end_date"], "%Y-%m-%d").date()
    end = end_inclusive + timedelta(days=1)
    a = datetime.combine(start, time.min, PARIS)
    b = datetime.combine(end, time.min, PARIS)
    return int(a.astimezone(UTC).timestamp() * 1000), int(b.astimezone(UTC).timestamp() * 1000)


def register_statistics_sales_channels_isolated_phase5(app, db):
    @app.after_request
    def statistics_sales_channels_phase5(response):
        # 1) API : remplace seulement la ventilation `sources`.
        if request.path == "/api/statistics/today-phase44" and response.status_code == 200:
            try:
                data = response.get_json(silent=True)
                if not isinstance(data, dict) or not data.get("ok"):
                    return response

                start_ms, end_ms = _period_bounds_from_response(data)
                totals = {key: {"count": 0, "total": 0.0} for key in CHANNELS}

                with db() as conn:
                    try:
                        rows = conn.execute(
                            """
                            SELECT COALESCE(NULLIF(UPPER(sales_channel),''),'RESTO') channel,
                                   COUNT(*) count,
                                   COALESCE(SUM(total),0) total
                            FROM caisse_orders
                            WHERE created_at >= %s AND created_at < %s
                              AND COALESCE(cancellation_hidden,FALSE)=FALSE
                            GROUP BY 1
                            """,
                            (start_ms, end_ms),
                        ).fetchall()
                    except Exception:
                        # Compatibilité historique si la colonne n'existe pas encore :
                        # les commandes de caisse déjà présentes sont classées RESTO.
                        rows = conn.execute(
                            """
                            SELECT 'RESTO' channel, COUNT(*) count, COALESCE(SUM(total),0) total
                            FROM caisse_orders
                            WHERE created_at >= %s AND created_at < %s
                              AND COALESCE(cancellation_hidden,FALSE)=FALSE
                            """,
                            (start_ms, end_ms),
                        ).fetchall()

                for row in rows:
                    key = str(row["channel"] or "RESTO").upper()
                    if key not in totals:
                        key = "RESTO"
                    totals[key]["count"] += int(row["count"] or 0)
                    totals[key]["total"] += float(row["total"] or 0)

                data["sources"] = [
                    {
                        "source": LABELS[key],
                        "channel": key,
                        "count": totals[key]["count"],
                        "total": totals[key]["total"],
                    }
                    for key in CHANNELS
                ]
                response.set_json(data)
                return response
            except Exception:
                # Les statistiques existantes doivent rester disponibles même si
                # cette ventilation additionnelle rencontre une anomalie.
                return response

        # 2) Page : change uniquement l'intitulé du bloc existant.
        if request.path == "/statistiques" and response.status_code == 200:
            if response.content_type and "text/html" in response.content_type:
                html = response.get_data(as_text=True)
                html = html.replace("<h2>Canaux / modes</h2>", "<h2>Canaux de vente</h2>", 1)
                response.set_data(html)
                response.headers["Content-Length"] = len(response.get_data())

        return response
