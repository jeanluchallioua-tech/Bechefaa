"""Local sandbox kitchen workflow. No POS sale, Uber write or printer call."""
import hmac
import json
import secrets

from flask import Response, jsonify, request, session

from .uber_sandbox_accept import canonical_id, fetch_order, notified_orders
from .uber_sandbox_link import STORE_ID, UberFailure, get_token
from .uber_sandbox_pos_display import preproduction_host

TRANSITIONS = {'À préparer': 'En préparation', 'En préparation': 'Terminée'}


def sandbox_allowed():
    return preproduction_host() and session.get('caisse_auth') is True


def sandbox_csrf():
    return session.setdefault('uber_sandbox_csrf', secrets.token_urlsafe(32))


def valid_csrf():
    expected = session.get('uber_sandbox_csrf', '')
    supplied = request.headers.get('X-Uber-Test-CSRF', '')
    return bool(expected and supplied and hmac.compare_digest(expected.encode(), supplied.encode()))


def reply(status=200, **values):
    response = jsonify(test_only=True, creates_pos_sales=False, printing_enabled=False, **values)
    response.status_code = status
    response.headers['Cache-Control'] = 'no-store'
    return response


def register_uber_sandbox_kitchen(app, db):
    @app.get('/administration/uber-sandbox/kitchen')
    def uber_sandbox_kitchen_page():
        if not sandbox_allowed():
            return Response('Session de caisse de préproduction requise.', status=403)
        # A dedicated test page keeps the approved production kitchen intact.
        from .uber_sandbox_test_panel import panel
        html = '''<!doctype html><html lang="fr"><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Cuisine Uber — TEST</title><body style="font-family:Arial;margin:24px">
        <h1>Cuisine Uber — TEST</h1>
        <p>Commandes d’essai uniquement. Les étapes de préparation restent locales à cette page de test.</p>
        <p><a href="/pos">Retour à la caisse de préproduction</a></p>'''
        response = Response(html + panel(kitchen=True) + '</body></html>', content_type='text/html; charset=utf-8')
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.post('/api/uber/sandbox/kitchen/dispatch')
    def uber_sandbox_kitchen_dispatch():
        if not sandbox_allowed() or not valid_csrf():
            return reply(403, ok=False, error='sandbox_session_or_csrf_required')
        data = request.get_json(silent=True)
        order_id = data.get('order_id') if isinstance(data, dict) else None
        if not canonical_id(order_id):
            return reply(400, ok=False, error='invalid_order_id')
        try:
            if order_id not in notified_orders(db):
                return reply(404, ok=False, error='notification_not_found')
            # Sending to the local test kitchen requires an existing display
            # import; fresh Uber read also blocks canceled/refused orders.
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT to_regclass('uber_sandbox_display_orders') IS NOT NULL AS display_exists")
                    row = cur.fetchone()
                    exists = row['display_exists'] if hasattr(row, 'keys') else row[0]
                    if not exists:
                        return reply(409, ok=False, error='import_required')
                    cur.execute('''SELECT order_id FROM uber_sandbox_display_orders
                        WHERE store_id = %s AND order_id = %s''', (STORE_ID, order_id))
                    if cur.fetchone() is None:
                        return reply(409, ok=False, error='import_required')
            token = get_token('client_credentials', scope='eats.store.orders.read')
            order, _ = fetch_order(order_id, token)
            if order['current_state'] not in ('ACCEPTED', 'FINISHED'):
                return reply(409, ok=False, error='order_not_accepted', message='La commande n’est plus acceptée chez Uber.')
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute('''CREATE TABLE IF NOT EXISTS uber_sandbox_kitchen_orders (
                        store_id TEXT NOT NULL, order_id TEXT NOT NULL,
                        summary JSONB NOT NULL, sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        stage TEXT NOT NULL DEFAULT 'À préparer',
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (store_id, order_id)
                    )''')
                    cur.execute('''INSERT INTO uber_sandbox_kitchen_orders (store_id, order_id, summary)
                        VALUES (%s, %s, %s::jsonb) ON CONFLICT (store_id, order_id) DO NOTHING
                        RETURNING order_id''', (STORE_ID, order_id, json.dumps(order)))
                    created = cur.fetchone() is not None
                conn.commit()
            return reply(ok=True, created=created,
                message='Commande envoyée dans la cuisine de test.' if created else 'Commande déjà envoyée ; aucun doublon créé.')
        except UberFailure as error:
            return reply(502, ok=False, error='uber_read_failed', message=str(error))
        except Exception:
            app.logger.error('Uber sandbox kitchen dispatch failed')
            return reply(503, ok=False, error='sandbox_kitchen_unavailable')

    @app.get('/api/uber/sandbox/kitchen-display')
    def uber_sandbox_kitchen_list():
        if not sandbox_allowed():
            return reply(403, ok=False, error='sandbox_session_required')
        try:
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT to_regclass('uber_sandbox_kitchen_orders') IS NOT NULL AS kitchen_exists")
                    row = cur.fetchone()
                    exists = row['kitchen_exists'] if hasattr(row, 'keys') else row[0]
                    rows = []
                    if exists:
                        cur.execute('''SELECT order_id, summary, sent_at, stage FROM uber_sandbox_kitchen_orders
                            WHERE store_id = %s ORDER BY sent_at DESC, order_id DESC LIMIT 20''', (STORE_ID,))
                        for row in cur.fetchall():
                            row = dict(row) if hasattr(row, 'keys') else dict(zip(('order_id','summary','sent_at','stage'),row))
                            summary = row['summary']
                            if (not isinstance(summary, dict) or summary.get('store_id') != STORE_ID
                                or summary.get('id') != row['order_id'] or row['stage'] not in (*TRANSITIONS, 'Terminée')):
                                raise ValueError('invalid kitchen snapshot')
                            rows.append({'order':summary, 'stage':row['stage'], 'sent_at':row['sent_at'].isoformat()})
            return reply(ok=True, read_only=True, orders=rows, csrf=sandbox_csrf(), store_id=STORE_ID)
        except Exception:
            return reply(503, ok=False, error='sandbox_kitchen_unavailable')

    @app.post('/api/uber/sandbox/kitchen/stage')
    def uber_sandbox_kitchen_stage():
        if not sandbox_allowed() or not valid_csrf():
            return reply(403, ok=False, error='sandbox_session_or_csrf_required')
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return reply(400, ok=False, error='invalid_transition')
        order_id, previous, next_stage = data.get('order_id'), data.get('previous'), data.get('stage')
        if (not canonical_id(order_id) or not isinstance(previous, str)
            or previous not in TRANSITIONS or TRANSITIONS[previous] != next_stage):
            return reply(400, ok=False, error='invalid_transition')
        try:
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute('''UPDATE uber_sandbox_kitchen_orders SET stage = %s, updated_at = NOW()
                        WHERE store_id = %s AND order_id = %s AND stage = %s RETURNING order_id''',
                        (next_stage, STORE_ID, order_id, previous))
                    changed = cur.fetchone() is not None
                conn.commit()
            if not changed:
                return reply(409, ok=False, error='stage_changed', message='L’état a déjà changé. Actualisez les commandes de test.')
            return reply(ok=True, stage=next_stage)
        except Exception:
            return reply(503, ok=False, error='sandbox_kitchen_unavailable')
