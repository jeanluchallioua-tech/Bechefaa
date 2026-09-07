"""Phase 2.3 — tests isolés d'ajout et d'affectation d'une option centrale.

Ne modifie pas l'administration Options existante.
Ajout uniquement en fin de optionLists[group_key].
Affectation uniquement par ajout de l'index existant dans optionSelections du produit.
"""
import json
import time
from decimal import Decimal, InvalidOperation
from html import escape

from flask import Response, request


def register_option_add_test_phase23(app, db):
    def load_catalog():
        with db() as conn:
            row = conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1").fetchone()
        if not row:
            raise RuntimeError('Catalogue catalog_admin_v2 introuvable')
        data = json.loads(row['data_json'] or '{}')
        return data if isinstance(data, dict) else {}

    def proven_group_metadata(data, group_key):
        """Réutilise les métadonnées d'un groupe central déjà matérialisé dans le catalogue.

        Aucun réglage n'est inventé : title/required/max/priceMode sont copiés depuis
        un produit existant qui utilise déjà central_<group_key>. Pour les groupes
        personnalisés seulement, optionListDefs reste le repli historique.
        """
        central_key = 'central_' + group_key
        for existing_product in data.get('products') or []:
            if not isinstance(existing_product, dict):
                continue
            for existing_group in existing_product.get('options') or []:
                if not isinstance(existing_group, dict) or str(existing_group.get('key') or '') != central_key:
                    continue
                return {
                    'key': central_key,
                    'title': str(existing_group.get('title') or existing_group.get('name') or group_key),
                    'required': bool(existing_group.get('required', False)),
                    'max': existing_group.get('max', 0) or 0,
                    'priceMode': existing_group.get('priceMode', 'extra'),
                    'choices': [],
                }
        defs = data.get('optionListDefs') or {}
        definition = defs.get(group_key) if isinstance(defs, dict) and isinstance(defs.get(group_key), dict) else None
        if definition:
            return {
                'key': central_key,
                'title': str(definition.get('title') or definition.get('label') or group_key),
                'required': bool(definition.get('required', False)),
                'max': definition.get('max', 0) or 0,
                'priceMode': definition.get('priceMode', 'extra'),
                'choices': [],
            }
        raise ValueError('Métadonnées de groupe non prouvées : affectation refusée')

    @app.route('/administration/options-ajout-test', methods=['GET', 'POST'], endpoint='phase23_option_add_test_page')
    def option_add_test_page():
        message = ''
        error = ''

        if request.method == 'POST':
            action = str(request.form.get('action') or 'add').strip()
            try:
                if action == 'assign':
                    product_id = str(request.form.get('product_id') or '').strip()
                    group_key = str(request.form.get('assign_group_key') or '').strip()
                    option_index = int(str(request.form.get('option_index') or '').strip())
                    with db() as conn:
                        with conn.transaction():
                            row = conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1 FOR UPDATE").fetchone()
                            if not row:
                                raise RuntimeError('Catalogue catalog_admin_v2 introuvable')
                            data = json.loads(row['data_json'] or '{}')
                            lists = data.get('optionLists') or {}
                            choices = lists.get(group_key) if isinstance(lists, dict) else None
                            if not isinstance(choices, list) or option_index < 0 or option_index >= len(choices):
                                raise ValueError('Option introuvable')
                            choice = choices[option_index]
                            if isinstance(choice, (list, tuple)):
                                option_name = str(choice[0] if choice else '').strip()
                                option_price = float(choice[1] if len(choice) > 1 else 0)
                            elif isinstance(choice, dict):
                                option_name = str(choice.get('name') or choice.get('label') or '').strip()
                                option_price = float(choice.get('price', 0) or 0)
                            else:
                                raise ValueError('Format option non pris en charge')
                            product = next((p for p in data.get('products') or [] if isinstance(p, dict) and str(p.get('id')) == product_id), None)
                            if not product:
                                raise ValueError('Produit introuvable')
                            selections = product.get('optionSelections')
                            if not isinstance(selections, dict):
                                selections = {}
                                product['optionSelections'] = selections
                            selected = selections.get(group_key)
                            if not isinstance(selected, list):
                                selected = []
                                selections[group_key] = selected
                            normalized = []
                            for value in selected:
                                try:
                                    normalized.append(int(value))
                                except (TypeError, ValueError):
                                    pass
                            if option_index not in normalized:
                                selected.append(option_index)
                            central_key = 'central_' + group_key
                            direct = product.get('options')
                            if not isinstance(direct, list):
                                direct = []
                                product['options'] = direct
                            group = next((g for g in direct if isinstance(g, dict) and str(g.get('key') or '') == central_key), None)
                            if group is None:
                                group = proven_group_metadata(data, group_key)
                                direct.append(group)
                            materialized = group.get('choices')
                            if not isinstance(materialized, list):
                                materialized = []
                                group['choices'] = materialized
                            exists = False
                            for item in materialized:
                                label = str(item[0] if isinstance(item, (list, tuple)) and item else item.get('name') or item.get('label') or '' if isinstance(item, dict) else '').strip()
                                if label == option_name:
                                    exists = True
                                    break
                            if not exists:
                                materialized.append([option_name, option_price])
                            conn.execute("UPDATE catalog_admin_v2 SET data_json=%s::jsonb, updated_at=%s WHERE id=1", (json.dumps(data, ensure_ascii=False), int(time.time() * 1000)))
                    message = f'Option « {option_name} » affectée à « {product.get("name") or product_id} » avec les métadonnées existantes du groupe.'
                else:
                    group_key = str(request.form.get('group_key') or '').strip()
                    name = str(request.form.get('name') or '').strip()
                    raw_price = str(request.form.get('price') or '0').strip()
                    if not group_key:
                        raise ValueError('Groupe invalide.')
                    if not name or len(name) > 120:
                        raise ValueError('Nom invalide.')
                    try:
                        price = Decimal(raw_price).quantize(Decimal('0.01'))
                        if price < 0:
                            raise InvalidOperation
                    except (InvalidOperation, ValueError):
                        raise ValueError('Prix invalide.')
                    with db() as conn:
                        with conn.transaction():
                            row = conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1 FOR UPDATE").fetchone()
                            if not row:
                                raise RuntimeError('Catalogue catalog_admin_v2 introuvable')
                            data = json.loads(row['data_json'] or '{}')
                            lists = data.get('optionLists')
                            choices = lists.get(group_key) if isinstance(lists, dict) else None
                            if not isinstance(choices, list):
                                raise ValueError('Groupe introuvable')
                            for choice in choices:
                                existing = str(choice[0] if isinstance(choice, (list, tuple)) and choice else choice.get('name') or choice.get('label') or '' if isinstance(choice, dict) else choice or '').strip()
                                if existing.casefold() == name.casefold():
                                    raise ValueError('Cette option existe déjà')
                            new_index = len(choices)
                            choices.append([name, float(price)])
                            orders = data.get('optionListOrders')
                            if isinstance(orders, dict) and isinstance(orders.get(group_key), list):
                                present = set()
                                for value in orders[group_key]:
                                    try: present.add(int(value))
                                    except (TypeError, ValueError): pass
                                if new_index not in present:
                                    orders[group_key].append(new_index)
                            conn.execute("UPDATE catalog_admin_v2 SET data_json=%s::jsonb, updated_at=%s WHERE id=1", (json.dumps(data, ensure_ascii=False), int(time.time() * 1000)))
                    message = f'Option « {name} » ajoutée en fin du groupe {group_key}, index {new_index}, prix {price:.2f} €.'
            except Exception as exc:
                error = str(exc)

        try:
            data = load_catalog()
            lists = data.get('optionLists') or {}
            defs = data.get('optionListDefs') or {}
            group_keys = [k for k, v in lists.items() if isinstance(v, list)]
            products = [p for p in data.get('products') or [] if isinstance(p, dict) and p.get('id')]
        except Exception as exc:
            group_keys, defs, products = [], {}, []
            error = error or str(exc)

        def group_label(key):
            definition = defs.get(key) if isinstance(defs, dict) else None
            title = str((definition or {}).get('title') or (definition or {}).get('name') or (definition or {}).get('label') or '').strip() if isinstance(definition, dict) else ''
            return title or key

        options_html = ''.join('<option value="{0}">{1}</option>'.format(escape(k), escape(group_label(k))) for k in group_keys)
        products_html = ''.join('<option value="{0}">{1}</option>'.format(escape(str(p.get('id'))), escape(str(p.get('name') or 'Sans nom'))) for p in products)
        assign_options = []
        for key in group_keys:
            vals = lists.get(key) or []
            for i, choice in enumerate(vals):
                if isinstance(choice, (list, tuple)):
                    label = str(choice[0] if choice else '').strip(); price = choice[1] if len(choice) > 1 else 0
                elif isinstance(choice, dict):
                    label = str(choice.get('name') or choice.get('label') or '').strip(); price = choice.get('price', 0)
                else:
                    label = str(choice or '').strip(); price = 0
                if label:
                    assign_options.append('<option value="{0}|{1}">{2} — {3} ({4:.2f} €)</option>'.format(escape(key), i, escape(group_label(key)), escape(label), float(price or 0)))
        assign_options_html = ''.join(assign_options)
        message_html = f'<div class="ok">{escape(message)}</div>' if message else ''
        error_html = f'<div class="err">{escape(error)}</div>' if error else ''

        html = f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Test options</title><style>body{{font-family:Arial;background:#f4f5f7;margin:0;color:#17191c}}.top{{background:#111827;color:#fff;padding:14px 22px}}.top a{{color:#fff;margin-left:18px}}.wrap{{max-width:760px;margin:auto;padding:24px}}.card{{background:#fff;padding:20px;border-radius:14px;margin-bottom:18px}}label{{display:block;font-weight:700;margin-top:14px}}select,input{{width:100%;padding:11px;margin-top:6px;border:1px solid #ccd1d8;border-radius:8px}}button{{margin-top:18px;background:#175cd3;color:#fff;border:0;padding:11px 18px;border-radius:8px;font-weight:700}}.ok{{background:#e8f7ee;padding:12px;border-radius:8px;margin-bottom:14px}}.err{{background:#fff0ee;color:#9d261d;padding:12px;border-radius:8px;margin-bottom:14px}}.hint{{color:#667085}}</style></head><body><div class="top"><b>BÉCHÉFAA • Test isolé</b><a href="/administration/options-produits">Retour Options</a><a href="/pos">Caisse</a></div><div class="wrap"><h1>Options — test isolé</h1>{message_html}{error_html}<div class="card"><h2>Ajouter une option</h2><p class="hint">Ajout uniquement en fin de liste.</p><form method="post"><input type="hidden" name="action" value="add"><label>Groupe</label><select name="group_key" required>{options_html}</select><label>Nom</label><input name="name" maxlength="120" required><label>Prix</label><input name="price" type="number" min="0" step="0.01" value="0.00" required><button type="submit">Ajouter en fin de liste</button></form></div><div class="card"><h2>Affecter une option à un produit — test</h2><p class="hint">Ajoute seulement la référence de l'option choisie au produit. Aucun index existant n'est déplacé.</p><form method="post" onsubmit="var v=this.option_choice.value.split('|');this.assign_group_key.value=v[0];this.option_index.value=v[1]"><input type="hidden" name="action" value="assign"><input type="hidden" name="assign_group_key"><input type="hidden" name="option_index"><label>Produit</label><select name="product_id" required>{products_html}</select><label>Option</label><select name="option_choice" required>{assign_options_html}</select><button type="submit">Affecter cette option</button></form></div></div></body></html>'''
        return Response(html, content_type='text/html; charset=utf-8')
