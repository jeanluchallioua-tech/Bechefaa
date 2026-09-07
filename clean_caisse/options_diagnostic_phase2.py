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
            if not isinstance(data, dict):
                return jsonify({'ok': False, 'error': 'Catalogue invalide'}), 500

            products = data.get('products') if isinstance(data.get('products'), list) else []

            # Tous les noms de groupes réellement référencés par les produits.
            referenced_groups = []
            seen = set()
            for p in products:
                if not isinstance(p, dict):
                    continue
                selections = p.get('optionSelections')
                if not isinstance(selections, dict):
                    continue
                for name in selections.keys():
                    name = str(name)
                    if name not in seen:
                        seen.add(name)
                        referenced_groups.append(name)

            def compact(value, depth=0):
                """Petit aperçu JSON lisible, sans modifier les données."""
                if depth >= 3:
                    if isinstance(value, dict):
                        return {'_type': 'object', '_keys': list(value.keys())[:20], '_count': len(value)}
                    if isinstance(value, list):
                        return {'_type': 'array', '_count': len(value)}
                    return value
                if isinstance(value, dict):
                    return {str(k): compact(v, depth + 1) for k, v in list(value.items())[:20]}
                if isinstance(value, list):
                    return [compact(v, depth + 1) for v in value[:12]]
                return value

            # Cherche les définitions des groupes dans tout le niveau racine du catalogue.
            group_locations = {}
            for group_name in referenced_groups:
                hits = []
                for top_key, top_value in data.items():
                    if top_key == 'products':
                        continue
                    if isinstance(top_value, dict):
                        if group_name in top_value:
                            hits.append({
                                'location': f'{top_key}.{group_name}',
                                'value': compact(top_value.get(group_name)),
                            })
                        # Certains catalogues rangent les groupes dans des objets imbriqués.
                        for child_key, child_value in list(top_value.items())[:100]:
                            if isinstance(child_value, dict) and group_name in child_value:
                                hits.append({
                                    'location': f'{top_key}.{child_key}.{group_name}',
                                    'value': compact(child_value.get(group_name)),
                                })
                    elif isinstance(top_value, list):
                        for i, item in enumerate(top_value[:200]):
                            if isinstance(item, dict):
                                possible_name = str(item.get('id') or item.get('key') or item.get('name') or item.get('slug') or '')
                                if possible_name == group_name:
                                    hits.append({
                                        'location': f'{top_key}[{i}]',
                                        'value': compact(item),
                                    })
                group_locations[group_name] = hits

            # Montre aussi la structure exacte de quelques optionSelections produits,
            # car leurs valeurs peuvent contenir des identifiants/règles utiles.
            product_samples = []
            for p in products:
                if not isinstance(p, dict) or not isinstance(p.get('optionSelections'), dict):
                    continue
                product_samples.append({
                    'id': p.get('id'),
                    'name': p.get('name'),
                    'optionSelections': compact(p.get('optionSelections')),
                    'options': compact(p.get('options')) if 'options' in p else None,
                    'optionRules': compact(p.get('optionRules')) if 'optionRules' in p else None,
                })
                if len(product_samples) >= 8:
                    break

            top_level = {}
            for key, value in data.items():
                if key == 'products':
                    top_level[key] = {'type': 'array', 'count': len(products)}
                elif isinstance(value, dict):
                    top_level[key] = {'type': 'object', 'count': len(value), 'keys': list(value.keys())[:80]}
                elif isinstance(value, list):
                    top_level[key] = {'type': 'array', 'count': len(value), 'sample': compact(value[:3])}
                else:
                    top_level[key] = {'type': type(value).__name__, 'value': str(value)[:160]}

            return jsonify({
                'ok': True,
                'catalog': 'catalog_admin_v2',
                'productCount': len(products),
                'referencedGroups': referenced_groups,
                'groupDefinitionLocations': group_locations,
                'productSamples': product_samples,
                'topLevelStructures': top_level,
                'note': 'Diagnostic lecture seule : aucune donnée n’a été modifiée.',
            })
        except Exception as exc:
            return jsonify({'ok': False, 'error': 'Diagnostic impossible', 'detail': str(exc)}), 500
