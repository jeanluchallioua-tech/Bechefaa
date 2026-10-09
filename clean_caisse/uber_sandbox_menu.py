"""Full Menu v2 export, restricted to the approved Uber sandbox restaurant."""
import hashlib
import json
import secrets
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import quote

from flask import Response, redirect, render_template_string, request, session
from .uber_sandbox_link import STORE_ID, API, UberFailure, call_uber, get_token

MENU_API = 'https://test-api.uber.com/v2/eats/stores/' + STORE_ID + '/menus'
DAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')


def money(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0:
            raise ValueError()
        return result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Un prix du catalogue est invalide.') from None


def cents(value, markup):
    return int((money(value) * (1 + markup / 100) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def text(value):
    return {'translations': {'fr_fr': str(value)}}


def identifier(prefix, *values):
    raw = json.dumps(values, ensure_ascii=False, separators=(',', ':'))
    return prefix + '_' + hashlib.sha256(raw.encode()).hexdigest()[:24]


def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def build_menu(data, markup):
    """Pure conversion; never alter the POS catalogue or create orders."""
    markup = money(markup)
    if markup > 100:
        raise ValueError('La majoration Uber doit être comprise entre 0 et 100 %.')
    if not isinstance(data, dict):
        raise ValueError('Catalogue indisponible.')
    categories, items, groups, rows = [], [], [], []
    category_map = {}
    for cat in data.get('categories') or []:
        if not isinstance(cat, dict) or cat.get('active', True) is False:
            continue
        name = str(cat.get('name') or '').strip()
        if name and name not in category_map:
            obj = {'id': identifier('cat', cat.get('id') or name), 'title': text(name), 'entities': []}
            categories.append(obj)
            category_map[name] = obj
    seen = set()
    for product in data.get('products') or []:
        if not isinstance(product, dict) or product.get('active', True) is False:
            continue
        if product.get('channels', {}).get('ubereats', True) is False or product.get('marketplace_visible', True) is False or product.get('uber_visible', True) is False:
            continue
        pid = str(product.get('id') or '').strip()
        name = str(product.get('name') or '').strip()
        if not pid or not name or pid in seen:
            raise ValueError('Un article Uber a un identifiant ou un nom manquant ou dupliqué.')
        seen.add(pid)
        category = category_map.get(str(product.get('category') or ''))
        if category is None:
            raise ValueError('Catégorie absente ou désactivée pour : ' + name)
        item_id = identifier('product', pid)
        group_ids, row_groups = [], []
        for gi, group in enumerate(product.get('options') or []):
            if not isinstance(group, dict):
                raise ValueError('Groupe d’options invalide pour : ' + name)
            title = str(group.get('title') or group.get('name') or group.get('label') or '').strip()
            choices = next((group[k] for k in ('choices', 'values', 'options', 'items') if isinstance(group.get(k), list)), [])
            if not choices:
                if group.get('required'):
                    raise ValueError('Options obligatoires absentes pour : ' + name)
                continue
            gid = identifier('group', pid, group.get('key') or title, gi)
            options, row_choices = [], []
            for ci, choice in enumerate(choices):
                if isinstance(choice, (list, tuple)) and choice:
                    label, price = str(choice[0]).strip(), choice[1] if len(choice) > 1 else 0
                elif isinstance(choice, dict):
                    label = str(choice.get('name') or choice.get('label') or choice.get('title') or '').strip()
                    price = choice.get('price', choice.get('extraPrice', 0))
                else:
                    label, price = str(choice or '').strip(), 0
                if not label:
                    raise ValueError('Une option est sans nom pour : ' + name)
                oid = identifier('option', pid, group.get('key') or title, gi, ci, label)
                cost = cents(price, markup)
                items.append({'id': oid, 'title': text(label), 'price_info': {'price': cost},
                    'tax_info': {'vat_rate_percentage': 10}, 'quantity_info': {'quantity': {'max_permitted': 1}},
                    'external_data': json.dumps({'bechefaa_product_id': pid, 'group_index': gi, 'choice_index': ci}, separators=(',', ':'))})
                options.append({'id': oid, 'type': 'ITEM'})
                row_choices.append({'name': label, 'price': cost / 100})
            try:
                maximum = int(group.get('max') or group.get('maxChoices') or 0)
                minimum = max(int(group.get('min') or 0), 1 if group.get('required') else 0)
            except (ValueError, TypeError):
                raise ValueError('Limite d’options invalide pour : ' + name) from None
            maximum = min(maximum if maximum > 0 else len(options), len(options))
            if minimum < 0 or minimum > maximum:
                raise ValueError('Choix obligatoires impossibles pour : ' + name)
            groups.append({'id': gid, 'title': text(title or 'Options'), 'modifier_options': options,
                'quantity_info': {'quantity': {'min_permitted': minimum, 'max_permitted': maximum}}})
            group_ids.append(gid)
            row_groups.append({'name': title, 'minimum': minimum, 'maximum': maximum, 'choices': row_choices})
        cost = cents(product.get('price', 0), markup)
        item = {'id': item_id, 'title': text(name), 'price_info': {'price': cost, 'in_store_price': cents(product.get('price', 0), Decimal(0))},
            'tax_info': {'vat_rate_percentage': float(money(product.get('vat_rate', 10)))},
            'external_data': json.dumps({'bechefaa_product_id': pid}, separators=(',', ':')),
            'modifier_group_ids': {'ids': group_ids}}
        description = product.get('ingredients') or product.get('description') or product.get('desc')
        if description:
            item['description'] = text(description)
        photo = str(product.get('photo') or '')
        if photo.startswith('data:') or '/api/public/catalog/photo/' in photo:
            photo = 'https://caisse.bechefaa.fr/api/public/catalog/photo-marketplace/uber/' + quote(pid, safe='')
        if photo.startswith('https://'):
            item['image_url'] = photo
        sold_out = product.get('channelSoldout', {}).get('ubereats', False) or product.get('availability') in ('unavailable', 'soldout', 'sold_out')
        if sold_out:
            item['suspension_info'] = {'suspension': {'suspend_until': 4102444800, 'reason': 'Indisponible dans le catalogue'}}
        items.append(item)
        category['entities'].append({'id': item_id, 'type': 'ITEM'})
        rows.append({'name': name, 'price': cost / 100, 'category': str(product.get('category')), 'photo': item.get('image_url'), 'groups': row_groups, 'sold_out': bool(sold_out)})
    categories = [cat for cat in categories if cat['entities']]
    if not rows or not categories:
        raise ValueError('Aucun article activé pour Uber Eats. Aucun menu vide ne sera envoyé.')
    payload = {'menus': [{'id': 'bechefaa-sandbox-menu', 'title': text('Carte BÉCHÉFAA — test'),
        'service_availability': [{'day_of_week': day, 'time_periods': [{'start_time': '00:00', 'end_time': '23:59'}]} for day in DAYS],
        'category_ids': [cat['id'] for cat in categories]}], 'categories': categories, 'items': items, 'modifier_groups': groups}
    return payload, rows


def read_source():
    from .app import db, load_catalog
    data, _updated = load_catalog()
    with db() as conn:
        row = conn.execute("SELECT percentage FROM marketplace_markup_settings WHERE channel='UBER_EATS'").fetchone()
    return data, row['percentage'] if row else 15


def verified_menu(expected, actual):
    """Check exported IDs, prices and option constraints, tolerating provider metadata."""
    for key in ('menus', 'categories', 'items', 'modifier_groups'):
        target = {obj['id']: obj for obj in expected[key]}
        found = {obj.get('id'): obj for obj in actual.get(key, []) if isinstance(obj, dict)}
        if set(target) != set(found):
            return False
        for oid, obj in target.items():
            other = found[oid]
            fields = {'menus': ('category_ids', 'service_availability'), 'categories': ('entities',),
                'items': ('modifier_group_ids',), 'modifier_groups': ('modifier_options',)}[key]
            for field in fields:
                if field == 'modifier_group_ids':
                    if (obj.get(field) or {}).get('ids', []) != (other.get(field) or {}).get('ids', []):
                        return False
                elif obj[field] != other.get(field):
                    return False
            if not set(obj['title']['translations'].values()).issubset(set((other.get('title') or {}).get('translations', {}).values())):
                return False
            if key == 'items' and obj['price_info']['price'] != (other.get('price_info') or {}).get('price'):
                return False
            if key == 'modifier_groups':
                quantity = (other.get('quantity_info') or {}).get('quantity', {})
                if any(quantity.get(k, 0) != v for k, v in obj['quantity_info']['quantity'].items()):
                    return False
    return True


def register_uber_sandbox_menu(app):
    def authorized(post=False):
        import hmac
        if session.get('caisse_auth') is not True:
            return False
        expected = session.get('uber_sandbox_csrf', '')
        return not post or bool(expected and hmac.compare_digest(expected, request.form.get('csrf', '')))

    def page(message='', status=200):
        try:
            data, markup = read_source()
            payload, rows = build_menu(data, markup)
        except Exception:
            return Response('Le catalogue ou les réglages Uber sont indisponibles. Aucun envoi effectué.', status=503)
        nonce = secrets.token_urlsafe(32)
        session['uber_menu_preview'] = {'digest': fingerprint(payload), 'nonce': nonce}
        session.setdefault('uber_sandbox_csrf', secrets.token_urlsafe(32))
        html = render_template_string('''<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Carte Uber Eats — test</title><style>body{font-family:Arial;max-width:900px;margin:auto;padding:24px;color:#17212b}button{font-size:18px;padding:16px;margin:8px 0;cursor:pointer}.result{background:#fff4ce;padding:16px}article{border-bottom:1px solid #ddd;padding:16px 0}img{width:120px;height:90px;object-fit:contain;float:right}summary{cursor:pointer}li{margin:6px 0}</style>
        <h1>Carte Uber Eats — restaurant de test</h1><p>BÉCHÉFAA Test Store · {{ count }} articles · {{ group_count }} groupes d’options<br>Majoration Uber enregistrée : {{ markup }} %.</p>
        <p>Pour les essais, cette carte de test est disponible tous les jours de 00 h 00 à 23 h 59. Les horaires du restaurant réel restent indépendants.</p>
        {% if message %}<p class="result">{{ message }}</p>{% endif %}
        <form method="post" action="/administration/uber-sandbox/menu/upload"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="nonce" value="{{ nonce }}"><button>Envoyer la carte au restaurant de test</button></form>
        <p>L’envoi remplace la carte actuellement présente dans ce restaurant de test.</p>
        <form method="post" action="/administration/uber-sandbox/menu/verify"><input type="hidden" name="csrf" value="{{ csrf }}"><button>Vérifier la carte chez Uber</button></form>
        <a href="/administration/uber-sandbox">Retour à la liaison Uber</a>
        {% for row in rows %}<article>{% if row.photo %}<img src="{{ row.photo }}" loading="lazy" alt="{{ row.name }}">{% endif %}<b>{{ row.name }} — {{ '%.2f'|format(row.price) }} €</b><p>{{ row.category }}{% if row.sold_out %} · Indisponible{% endif %}</p>
        {% if row.groups %}<details><summary>Voir les options</summary>{% for group in row.groups %}<p><b>{{ group.name }}</b> · {{ group.minimum }} à {{ group.maximum }} choix</p><ul>{% for choice in group.choices %}<li>{{ choice.name }}{% if choice.price %} (+{{ '%.2f'|format(choice.price) }} €){% endif %}</li>{% endfor %}</ul>{% endfor %}</details>{% endif %}</article>{% endfor %}</html>''',
            count=len(rows), group_count=len(payload['modifier_groups']), rows=rows, markup=markup, message=message, csrf=session['uber_sandbox_csrf'], nonce=nonce)
        response = Response(html, status=status, content_type='text/html; charset=utf-8')
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.get('/administration/uber-sandbox/menu')
    def uber_menu_page():
        if not authorized():
            return redirect('/', code=303)
        return page()

    @app.post('/administration/uber-sandbox/menu/upload')
    def uber_menu_upload():
        if not authorized(True):
            return Response('Accès refusé.', status=403)
        preview = session.pop('uber_menu_preview', None)
        if not preview or not secrets.compare_digest(preview['nonce'], request.form.get('nonce', '')):
            return page('Envoi déjà effectué ou aperçu expiré. Vérifiez l’aperçu avant de réessayer.', 409)
        try:
            data, markup = read_source()
            payload, _rows = build_menu(data, markup)
            if fingerprint(payload) != preview['digest']:
                return page('La carte ou les prix ont changé. Consultez le nouvel aperçu avant de l’envoyer.', 409)
            token = get_token('client_credentials', scope='eats.store')
            details = call_uber(API + '/pos_data', token=token)
            if details.get('store_id') != STORE_ID or details.get('integration_enabled') is not True:
                return page('La liaison du restaurant de test doit être confirmée avant l’envoi.', 409)
            call_uber(MENU_API, 'PUT', token=token, body=payload)
        except (UberFailure, ValueError) as error:
            return page('Carte non confirmée par Uber. ' + str(error), 502)
        except Exception:
            return page('Le catalogue est indisponible. Aucun envoi effectué.', 503)
        return page('Uber a accepté l’envoi de la carte de test. Cliquez sur « Vérifier la carte chez Uber » pour contrôler le menu enregistré.')

    @app.post('/administration/uber-sandbox/menu/verify')
    def uber_menu_verify():
        if not authorized(True):
            return Response('Accès refusé.', status=403)
        try:
            data, markup = read_source()
            payload, _rows = build_menu(data, markup)
            token = get_token('client_credentials', scope='eats.store')
            actual = call_uber(MENU_API, token=token, response_limit=4 * 1024 * 1024)
            message = 'Carte confirmée chez Uber : articles, prix et options correspondent à l’aperçu.' if verified_menu(payload, actual) else 'La carte lue chez Uber ne correspond pas encore à l’aperçu. Aucun nouvel envoi effectué.'
            return page(message)
        except (UberFailure, ValueError) as error:
            return page('Vérification non aboutie. ' + str(error), 502)
        except Exception:
            return page('Le catalogue est indisponible. Vérification non effectuée.', 503)
