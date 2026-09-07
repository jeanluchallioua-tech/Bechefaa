"""Phase 2.3 — page de test isolée pour ajouter une option centrale.

Cette page ne modifie pas l'administration Options existante.
Ajout uniquement en fin de optionLists[group_key], sans suppression ni réindexation.
"""
import json
import time
from decimal import Decimal, InvalidOperation
from html import escape

from flask import Response, request


def register_option_add_test_phase23(app, db):
    def load_catalog():
        with db() as conn:
            row = conn.execute(
                "SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1"
            ).fetchone()
        if not row:
            raise RuntimeError('Catalogue catalog_admin_v2 introuvable')
        data = json.loads(row['data_json'] or '{}')
        return data if isinstance(data, dict) else {}

    @app.route('/administration/options-ajout-test', methods=['GET', 'POST'], endpoint='phase23_option_add_test_page')
    def option_add_test_page():
        message = ''
        error = ''

        if request.method == 'POST':
            group_key = str(request.form.get('group_key') or '').strip()
            name = str(request.form.get('name') or '').strip()
            raw_price = str(request.form.get('price') or '0').strip()

            if not group_key:
                error = 'Groupe invalide.'
            elif not name or len(name) > 120:
                error = 'Nom invalide.'
            else:
                try:
                    price = Decimal(raw_price).quantize(Decimal('0.01'))
                    if price < 0:
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    error = 'Prix invalide.'
                else:
                    try:
                        with db() as conn:
                            with conn.transaction():
                                row = conn.execute(
                                    "SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1 FOR UPDATE"
                                ).fetchone()
                                if not row:
                                    raise RuntimeError('Catalogue catalog_admin_v2 introuvable')

                                data = json.loads(row['data_json'] or '{}')
                                lists = data.get('optionLists')
                                choices = lists.get(group_key) if isinstance(lists, dict) else None
                                if not isinstance(choices, list):
                                    raise ValueError('Groupe introuvable')

                                for choice in choices:
                                    if isinstance(choice, (list, tuple)):
                                        existing = str(choice[0] if choice else '').strip()
                                    elif isinstance(choice, dict):
                                        existing = str(choice.get('name') or choice.get('label') or '').strip()
                                    else:
                                        existing = str(choice or '').strip()
                                    if existing.casefold() == name.casefold():
                                        raise ValueError('Cette option existe déjà')

                                new_index = len(choices)
                                choices.append([name, float(price)])

                                orders = data.get('optionListOrders')
                                if isinstance(orders, dict) and isinstance(orders.get(group_key), list):
                                    order = orders[group_key]
                                    present = set()
                                    for value in order:
                                        try:
                                            present.add(int(value))
                                        except (TypeError, ValueError):
                                            pass
                                    if new_index not in present:
                                        order.append(new_index)

                                conn.execute(
                                    "UPDATE catalog_admin_v2 SET data_json=%s::jsonb, updated_at=%s WHERE id=1",
                                    (json.dumps(data, ensure_ascii=False), int(time.time() * 1000)),
                                )

                        message = f'Option « {name} » ajoutée en fin du groupe {group_key}, index {new_index}, prix {price:.2f} €.'
                    except Exception as exc:
                        error = str(exc)

        try:
            data = load_catalog()
            lists = data.get('optionLists') or {}
            defs = data.get('optionListDefs') or {}
            group_keys = [k for k, v in lists.items() if isinstance(v, list)]
        except Exception as exc:
            group_keys = []
            defs = {}
            error = error or str(exc)

        def group_label(key):
            definition = defs.get(key) if isinstance(defs, dict) else None
            title = ''
            if isinstance(definition, dict):
                title = str(definition.get('title') or definition.get('name') or definition.get('label') or '').strip()
            return title or key

        options_html = ''.join(
            '<option value="{0}">{1}</option>'.format(escape(k), escape(group_label(k))) for k in group_keys
        )
        message_html = f'<div class="ok">{escape(message)}</div>' if message else ''
        error_html = f'<div class="err">{escape(error)}</div>' if error else ''

        html = f'''<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BÉCHÉFAA • Test ajout option</title>
<style>
body{{font-family:Arial;background:#f4f5f7;margin:0;color:#17191c}}.top{{background:#111827;color:#fff;padding:14px 22px}}.top a{{color:#fff;margin-left:18px}}.wrap{{max-width:700px;margin:auto;padding:24px}}.card{{background:#fff;padding:20px;border-radius:14px}}label{{display:block;font-weight:700;margin-top:14px}}select,input{{width:100%;padding:11px;margin-top:6px;border:1px solid #ccd1d8;border-radius:8px}}button{{margin-top:18px;background:#175cd3;color:#fff;border:0;padding:11px 18px;border-radius:8px;font-weight:700}}.ok{{background:#e8f7ee;padding:12px;border-radius:8px;margin-bottom:14px}}.err{{background:#fff0ee;color:#9d261d;padding:12px;border-radius:8px;margin-bottom:14px}}.hint{{color:#667085}}
</style></head><body>
<div class="top"><b>BÉCHÉFAA • Test isolé</b><a href="/administration/options-produits">Retour Options</a><a href="/pos">Caisse</a></div>
<div class="wrap"><h1>Ajouter une option — test</h1><p class="hint">Cette page est séparée de la page Options validée. L'ajout se fait uniquement en fin de liste.</p>{message_html}{error_html}
<div class="card"><form method="post">
<label>Groupe</label><select name="group_key" required>{options_html}</select>
<label>Nom de la nouvelle option</label><input name="name" maxlength="120" required>
<label>Prix</label><input name="price" type="number" min="0" step="0.01" value="0.00" required>
<button type="submit">Ajouter en fin de liste</button>
</form></div></div></body></html>'''
        return Response(html, content_type='text/html; charset=utf-8')
