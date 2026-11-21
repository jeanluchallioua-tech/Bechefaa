"""Read one notified sandbox order; never import or accept an order."""
from uuid import UUID

from flask import jsonify, request, session

from .uber_sandbox_link import STORE_ID, UberFailure, call_uber, get_token


def money(value):
    if not isinstance(value, dict):
        return None
    amount, currency = value.get('amount'), value.get('currency_code')
    if type(amount) is not int or not isinstance(currency, str):
        return None
    return {'amount': amount, 'currency_code': currency}


def item_summary(item, depth=0):
    if not isinstance(item, dict) or depth > 8:
        raise ValueError('invalid item')
    price = item.get('price') or {}
    if not isinstance(price, dict):
        raise ValueError('invalid price')
    groups = item.get('selected_modifier_groups') or []
    if not isinstance(groups, list):
        raise ValueError('invalid modifier groups')
    options = []
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError('invalid modifier group')
        for field, removed in (('selected_items', False), ('removed_items', True)):
            values = group.get(field) or []
            if not isinstance(values, list):
                raise ValueError('invalid modifiers')
            for value in values:
                option = item_summary(value, depth + 1)
                option['removed'] = removed
                options.append(option)
    return {
        'id': item.get('id'), 'title': item.get('title'),
        'quantity': item.get('quantity'),
        'unit_price': money(price.get('unit_price')),
        'total_price': money(price.get('total_price')),
        'options': options,
    }


def order_summary(order, order_id):
    store = order.get('store') or {}
    if not isinstance(store, dict) or store.get('id') != STORE_ID or order.get('id') != order_id:
        raise ValueError('order identity mismatch')
    cart = order.get('cart')
    if not isinstance(cart, dict) or not isinstance(cart.get('items'), list):
        raise ValueError('invalid cart')
    payment = order.get('payment') or {}
    if not isinstance(payment, dict):
        raise ValueError('invalid payment')
    charges = payment.get('charges') or {}
    if not isinstance(charges, dict):
        raise ValueError('invalid charges')
    return {
        'id': order_id, 'store_id': STORE_ID,
        'display_id': order.get('display_id'),
        'current_state': order.get('current_state'),
        'items': [item_summary(item) for item in cart['items']],
        'charges': {key: money(charges.get(key)) for key in
            ('sub_total', 'tax', 'total', 'total_fee', 'total_fee_tax')},
        'amounts_note': 'Montants de l’API restaurant Uber, distincts du total payé côté client et de ses éventuels frais.',
    }


def register_uber_sandbox_order_read(app, db):
    @app.get('/api/uber/sandbox/order-details')
    def uber_sandbox_order_details():
        def result(status=200, **values):
            response = jsonify(read_only=True, order_processing_enabled=False, **values)
            response.status_code = status
            response.headers['Cache-Control'] = 'no-store'
            return response

        if session.get('caisse_auth') is not True:
            return result(403, ok=False, error='caisse_session_required')
        order_id = request.args.get('order_id', '')
        try:
            if str(UUID(order_id)) != order_id:
                raise ValueError('non canonical uuid')
        except (ValueError, AttributeError):
            return result(400, ok=False, error='invalid_order_id')

        # A signed notification for this fixed test store must precede any API
        # request. Never follow a payload URL or accept a caller-supplied store.
        try:
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT to_regclass('uber_webhook_inbox') IS NOT NULL AS inbox_exists")
                    row = cur.fetchone()
                    exists = row['inbox_exists'] if hasattr(row, 'keys') else row[0]
                    notified = False
                    if exists:
                        cur.execute("""SELECT event_key FROM uber_webhook_inbox
                            WHERE event_type = 'orders.notification'
                            AND payload #>> '{meta,resource_id}' = %s
                            AND %s IN (payload #>> '{meta,user_id}',
                                payload #>> '{meta,store_id}', payload ->> 'store_id')
                            LIMIT 1""", (order_id, STORE_ID))
                        notified = cur.fetchone() is not None
        except Exception:
            return result(503, ok=False, error='inbox_read_unavailable',
                message='Vérification de la notification indisponible. Réessayez plus tard.')
        if not notified:
            return result(404, ok=False, error='sandbox_notification_not_found',
                message='Aucune notification reçue pour cette commande du restaurant de test.')
        try:
            token = get_token('client_credentials', scope='eats.store.orders.read')
            order = call_uber('https://test-api.uber.com/v2/eats/order/' + order_id,
                method='GET', token=token, response_limit=4 * 1024 * 1024)
            summary = order_summary(order, order_id)
        except UberFailure as error:
            return result(502, ok=False, error='uber_order_read_failed', message=str(error))
        except (ValueError, TypeError, AttributeError):
            return result(502, ok=False, error='unexpected_order_response',
                message='Uber n’a pas renvoyé les détails attendus pour cette commande du restaurant de test.')
        return result(ok=True, order=summary,
            message='Commande test lue chez Uber. Aucune acceptation, vente ni impression déclenchée.')
