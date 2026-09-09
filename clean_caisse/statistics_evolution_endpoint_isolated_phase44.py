"""Phase 4.4 — endpoint chronologique statistiques isolé.

IMPORTANT : ce module n'est volontairement ni importé ni enregistré dans
wsgi_caisse.py. Il prépare uniquement les données nécessaires aux courbes
sur /statistiques, sans modifier le noyau statistics_phase44.py.

Lecture seule uniquement. Aucun Z, aucune clôture, aucune écriture métier.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import jsonify

from clean_caisse.statistics_phase44 import _bounds

PARIS = ZoneInfo("Europe/Paris")
UTC = ZoneInfo("UTC")


def register_statistics_evolution_endpoint_isolated_phase44(app, db):
    """Enregistre le futur endpoint chronologique quand l'intégration sera validée.

    Cette fonction n'est appelée nulle part à ce stade.
    """

    @app.get('/api/statistics/evolution-phase44')
    def statistics_evolution_phase44():
        try:
            start_ms, end_ms, period, start_date, end_date = _bounds()
        except ValueError as exc:
            return jsonify({'ok': False, 'error': str(exc)}), 400

        try:
            with db() as conn:
                rows = conn.execute(
                    """
                    SELECT created_at, total
                    FROM caisse_orders
                    WHERE created_at >= %s
                      AND created_at < %s
                      AND COALESCE(cancellation_hidden, FALSE) = FALSE
                      AND UPPER(COALESCE(status, '')) <> 'ANNULÉE'
                    ORDER BY created_at ASC
                    """,
                    (start_ms, end_ms),
                ).fetchall()

            start_day = datetime.fromisoformat(start_date).date()
            end_day = datetime.fromisoformat(end_date).date()

            buckets = {}
            day = start_day
            while day <= end_day:
                key = day.isoformat()
                buckets[key] = {'date': key, 'orders': 0, 'revenue': 0.0}
                day += timedelta(days=1)

            for row in rows:
                created_ms = int(row['created_at'])
                local_day = datetime.fromtimestamp(created_ms / 1000, tz=UTC).astimezone(PARIS).date().isoformat()
                if local_day not in buckets:
                    continue
                buckets[local_day]['orders'] += 1
                buckets[local_day]['revenue'] += float(row['total'] or 0)

            points = [buckets[key] for key in sorted(buckets)]

            for point in points:
                point['revenue'] = round(point['revenue'], 2)

            return jsonify({
                'ok': True,
                'period': period,
                'start_date': start_date,
                'end_date': end_date,
                'points': points,
            })
        except Exception as exc:
            return jsonify({
                'ok': False,
                'error': 'Évolution des ventes indisponible',
                'detail': str(exc),
            }), 500
