"""Phase 2.3 — modification isolée du prix d'une option centrale.

Sécurité : aucune création/suppression/réorganisation. Les indices optionSelections restent inchangés.
Synchronise les copies matérialisées central_<groupe> dans products[].options.
PostgreSQL catalog_admin_v2 uniquement. Aucun Wix/V1/localStorage.
"""
import json
import time
from decimal import Decimal, InvalidOperation

from flask import jsonify, request


def register_option_price_admin_phase23(app, db):
    @app.put('/api/admin/option-lists/<group_key>/<int:option_index>/price', endpoint='phase23_update_option_price')
    def update_option_price(group_key, option_index):
        payload = request.get_json(silent=True) or {}
        try:
            price = Decimal(str(payload.get('price', ''))).quantize(Decimal('0.01'))
        except (InvalidOperation, ValueError, TypeError):
            return jsonify({'ok': False, 'error': 'Prix invalide'}), 400
        if price < 0:
            return jsonify({'ok': False, 'error': 'Prix invalide'}), 400

        try:
            with db() as conn:
                with conn.transaction():
                    row = conn.execute(
                        "SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1 FOR UPDATE"
                    ).fetchone()
                    if not row:
                        return jsonify({'ok': False, 'error': 'Catalogue catalog_admin_v2 introuvable'}), 404
                    data = json.loads(row['data_json'] or '{}')
                    lists = data.get('optionLists')
                    choices = lists.get(group_key) if isinstance(lists, dict) else None
                    if not isinstance(choices, list) or option_index < 0 or option_index >= len(choices):
                        return jsonify({'ok': False, 'error': 'Option introuvable'}), 404

                    choice = choices[option_index]
                    new_price = float(price)
                    if isinstance(choice, list):
                        if len(choice) < 2:
                            return jsonify({'ok': False, 'error': 'Format option non pris en charge'}), 409
                        label = str(choice[0])
                        choice[1] = new_price
                    elif isinstance(choice, dict):
                        label = str(choice.get('name') or choice.get('label') or '')
                        if 'price' in choice:
                            choice['price'] = new_price
                        elif 'prix' in choice:
                            choice['prix'] = new_price
                        else:
                            choice['price'] = new_price
                    else:
                        return jsonify({'ok': False, 'error': 'Format option non pris en charge'}), 409

                    # Les produits peuvent contenir une copie matérialisée des groupes centraux.
                    # On ne touche qu'au choix correspondant par libellé, jamais aux indices/sélections.
                    central_key = 'central_' + group_key
                    for product in data.get('products') or []:
                        if not isinstance(product, dict):
                            continue
                        for group in product.get('options') or []:
                            if not isinstance(group, dict) or str(group.get('key') or '') != central_key:
                                continue
                            materialized = group.get('choices')
                            if not isinstance(materialized, list):
                                continue
                            for item in materialized:
                                if isinstance(item, list) and len(item) >= 2 and str(item[0]) == label:
                                    item[1] = new_price
                                elif isinstance(item, dict) and str(item.get('name') or item.get('label') or '') == label:
                                    item['price'] = new_price

                    conn.execute(
                        "UPDATE catalog_admin_v2 SET data_json=%s::jsonb, updated_at=%s WHERE id=1",
                        (json.dumps(data, ensure_ascii=False), int(time.time() * 1000)),
                    )

            return jsonify({'ok': True, 'group': group_key, 'index': option_index, 'name': label, 'price': new_price})
        except Exception as exc:
            return jsonify({'ok': False, 'error': 'Modification du prix impossible', 'detail': str(exc)}), 500
