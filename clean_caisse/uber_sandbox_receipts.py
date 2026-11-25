"""Read-only receipt previews from isolated Uber TEST snapshots."""
from copy import deepcopy
from decimal import Decimal

from flask import Response, render_template_string, session

from .uber_sandbox_accept import canonical_id
from .uber_sandbox_link import STORE_ID


def receipt_order(summary):
    if summary.get('store_id') != STORE_ID or summary.get('current_state') not in ('ACCEPTED', 'FINISHED'):
        raise ValueError('invalid test order')

    def euros(value):
        if not isinstance(value, dict) or type(value.get('amount')) is not int or value.get('currency_code') != 'EUR':
            raise ValueError('missing EUR amount')
        return Decimal(value['amount']) / 100

    def options(values, depth=0):
        if depth > 8:
            raise ValueError('invalid option depth')
        result = []
        for value in values or []:
            name = str(value.get('title') or '').strip()
            if value.get('removed') and not name.lower().startswith('sans '):
                name = 'Sans ' + name
            if value.get('quantity', 1) != 1:
                name = str(value['quantity']) + ' x ' + name
            if name:
                result.append({'name': name})
            result.extend(options(value.get('options'), depth + 1))
        return result

    items = []
    for item in summary['items']:
        qty = item.get('quantity')
        if type(qty) is not int or qty < 1:
            raise ValueError('invalid quantity')
        # Uber total_price already includes selected modifier prices.
        total = euros(item.get('total_price'))
        items.append({'name': str(item.get('title') or ''), 'qty': qty,
                      'unit_price': total / qty, 'options': options(item.get('options'))})
    return {'id': summary['id'], 'source': 'LIVRAISON', 'sales_channel': 'UBER_EATS',
            'customer_name': 'TEST UBER #' + str(summary.get('display_id') or summary['id'][-5:]),
            'payment': 'UBER TEST — HORS VENTES', 'tax_rate': 10,
            'total_ttc': euros(summary['charges'].get('total')), 'items': items}


PAGE = '''<!doctype html><html lang="fr"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tickets Uber TEST {{ ref }}</title>
<style>body{font:18px Arial;margin:24px;color:#17212b} .tickets{display:flex;gap:24px;flex-wrap:wrap}img{max-width:100%;width:384px;border:1px solid #ccc}section{max-width:100%}p{max-width:900px;line-height:1.5}</style>
<h1>Tickets Uber TEST · {{ ref }}</h1>
<p>Aperçus uniquement : aucune vente, aucun envoi en cuisine, aucune impression.</p>
<p>Les prix des articles comprennent leurs options. Le total est celui du restaurant transmis par Uber, hors frais client.
TVA calculée selon la règle actuelle de la caisse (10 %). Uber ne fournit pas de ventilation de TVA dans les réponses reçues.
L’identité du client et l’heure de création ne sont pas présentes dans cet import de test.</p>
<div class="tickets">{% for kind,title in [('kitchen','Ticket cuisine'),('client','Ticket client')] %}
<section><h2>{{ title }}</h2><img alt="{{ title }} Uber TEST" src="/administration/uber-sandbox/receipts/{{ order_id }}/{{ kind }}.png"></section>{% endfor %}</div>
<p><a href="/administration/uber-sandbox/orders?order_id={{ order_id }}">Retour à la gestion Uber</a></p></html>'''


def register_uber_sandbox_receipts(app, db):
    def load(order_id):
        from .uber_sandbox_pos_display import preproduction_host
        if not preproduction_host():
            return None, None, 404
        if session.get('caisse_auth') is not True:
            return None, None, 403
        if not canonical_id(order_id):
            return None, None, 400
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('uber_sandbox_display_orders') IS NOT NULL")
                row = cur.fetchone()
                if not (next(iter(row.values())) if hasattr(row, 'keys') else row[0]):
                    return None, None, 404
                cur.execute('SELECT summary FROM uber_sandbox_display_orders WHERE store_id=%s AND order_id=%s', (STORE_ID, order_id))
                row = cur.fetchone()
                if not row:
                    return None, None, 404
                summary = row['summary'] if hasattr(row, 'keys') else row[0]
                if not isinstance(summary, dict) or summary.get('id') != order_id:
                    raise ValueError('invalid stored order')
                identity = {}
                cur.execute("SELECT to_regclass('caisse_restaurant_settings') IS NOT NULL")
                row = cur.fetchone()
                settings_exist = next(iter(row.values())) if hasattr(row, 'keys') else row[0]
                if settings_exist:
                    cur.execute('SELECT setting_key,setting_value FROM caisse_restaurant_settings')
                    for row in cur.fetchall():
                        key, value = (row['setting_key'], row['setting_value']) if hasattr(row, 'keys') else row
                        identity[key] = value or ''
        return deepcopy(summary), identity, 200

    def preview(order_id, kind=None):
        try:
            if kind is not None and kind not in ('kitchen', 'client'):
                return Response('Ticket introuvable.', status=404)
            summary, identity, status = load(order_id)
            if status != 200:
                return Response('Aperçu réservé aux commandes importées dans la caisse de test.', status=status)
            order = receipt_order(summary)
            if kind:
                from .receipt_photo_layout import receipt_png
                return Response(receipt_png(order, kind, identity), mimetype='image/png')
            return Response(render_template_string(PAGE, order_id=order_id, ref=summary.get('display_id') or order_id[-5:]), mimetype='text/html')
        except Exception:
            app.logger.error('Uber TEST receipt preview unavailable')
            return Response('Aperçu indisponible : vérifiez les montants de la commande importée.', status=503)

    @app.get('/administration/uber-sandbox/receipts/<order_id>')
    def uber_test_receipts_page(order_id):
        response = preview(order_id)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/administration/uber-sandbox/receipts/<order_id>/<kind>.png')
    def uber_test_receipt_image(order_id, kind):
        response = preview(order_id, kind)
        response.headers['Cache-Control'] = 'no-store'
        return response
