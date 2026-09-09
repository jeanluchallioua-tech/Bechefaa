"""Phase 4.4 — endpoint isolé statistiques produits.

IMPORTANT : ce module n'est volontairement ni importé ni enregistré dans
wsgi_caisse.py. Il prépare l'exposition JSON des + vendus / - vendus sans
modifier le noyau statistiques validé ni la page /statistiques.

Lecture seule uniquement. Aucun Z, aucune clôture, aucune écriture métier.
"""

from flask import jsonify, request

from clean_caisse.statistics_phase44 import _bounds
from clean_caisse.statistics_products_adapter_phase44 import fetch_product_rankings


def register_statistics_products_endpoint_isolated_phase44(app, db):
    """Enregistre le futur endpoint produits lorsque l'intégration sera validée.

    Cette fonction n'est appelée nulle part à ce stade.
    """

    @app.get('/api/statistics/products-phase44')
    def statistics_products_phase44():
        try:
            start_ms, end_ms, period, start_date, end_date = _bounds()
        except ValueError as exc:
            return jsonify({'ok': False, 'error': str(exc)}), 400

        try:
            limit = request.args.get('limit', '5')
            rankings = fetch_product_rankings(db, start_ms, end_ms, limit=limit)
            return jsonify({
                'ok': True,
                'period': period,
                'start_date': start_date,
                'end_date': end_date,
                **rankings,
            })
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Limite invalide'}), 400
        except Exception as exc:
            return jsonify({
                'ok': False,
                'error': 'Statistiques produits indisponibles',
                'detail': str(exc),
            }), 500
