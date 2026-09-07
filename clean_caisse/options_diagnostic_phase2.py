"""Phase 2.3 — diagnostic lecture seule des structures d'options de catalog_admin_v2.

Aucune écriture PostgreSQL. Aucun ancien code, aucun Wix/V1/localStorage.
"""
import json

from flask import jsonify


def register_options_diagnostic_phase2(app, db):
    @app.get('/api/admin/options-diagnostic')
    def options_diagnostic():
        try:
            with db() as conn:
                row = conn.execute(
                    "SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1"
                ).fetchone()
            if not row:
                return jsonify({'ok': False, 'error': 'Catalogue catalog_admin_v2 introuvable'}), 404

            data = json.loads(row['data_json'] or '{}')
            products = data.get('products') if isinstance(data, dict) else []
            products = products if isinstance(products, list) else []

            def option_keys(obj):
                if not isinstance(obj, dict):
                    return []
                return sorted([
                    str(k) for k in obj.keys()
                    if any(word in str(k).lower() for word in ('option', 'group', 'choice', 'supplement', 'extra'))
                ])

            rows = []
            for p in products:
                if not isinstance(p, dict):
                    continue
                keys = option_keys(p)
                if not keys:
                    continue
                structures = {}
                for key in keys:
                    value = p.get(key)
                    if isinstance(value, dict):
                        structures[key] = {
                            'type': 'object',
                            'keys': list(value.keys())[:30],
                            'count': len(value),
                        }
                    elif isinstance(value, list):
                        structures[key] = {
                            'type': 'array',
                            'count': len(value),
                            'sampleTypes': sorted({type(x).__name__ for x in value[:20]}),
                        }
                    else:
                        structures[key] = {'type': type(value).__name__, 'value': str(value)[:120]}
                rows.append({
                    'id': p.get('id'),
                    'name': p.get('name'),
                    'optionKeys': keys,
                    'structures': structures,
                })

            top_keys = option_keys(data)
            top_structures = {}
            for key in top_keys:
                value = data.get(key)
                if isinstance(value, dict):
                    top_structures[key] = {
                        'type': 'object',
                        'keys': list(value.keys())[:50],
                        'count': len(value),
                    }
                elif isinstance(value, list):
                    top_structures[key] = {
                        'type': 'array',
                        'count': len(value),
                        'sampleTypes': sorted({type(x).__name__ for x in value[:20]}),
                    }
                else:
                    top_structures[key] = {'type': type(value).__name__, 'value': str(value)[:120]}

            return jsonify({
                'ok': True,
                'catalog': 'catalog_admin_v2',
                'productCount': len(products),
                'topLevelOptionKeys': top_keys,
                'topLevelStructures': top_structures,
                'productsWithOptionKeys': rows,
                'note': 'Diagnostic lecture seule : aucune donnée n’a été modifiée.',
            })
        except Exception as exc:
            return jsonify({'ok': False, 'error': 'Diagnostic impossible', 'detail': str(exc)}), 500
