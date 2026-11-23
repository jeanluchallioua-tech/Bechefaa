"""Manual acceptance for the single approved sandbox store, isolated from POS sales."""
import hashlib
import hmac
import json
import secrets
import time
from uuid import UUID

from flask import Response, render_template_string, request, session

from .uber_sandbox_link import API, CLIENT_ID, STORE_ID, UberFailure, call_uber, get_token
from .uber_sandbox_order_read import order_summary

PAGE = '''<!doctype html><html lang="fr"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Uber Eats — commandes de test</title>
<style>body{font:18px Arial;max-width:850px;margin:30px auto;padding:20px;color:#17212b}p,li{line-height:1.5}button{padding:14px;font-size:18px;cursor:pointer}code{overflow-wrap:anywhere}.message{background:#fff4ce;padding:16px}article{border:1px solid #ccc;padding:18px;margin:18px 0}.options{margin-left:20px}a{line-height:1.8}</style>
<h1>Uber Eats — commandes de test</h1>
<p>BÉCHÉFAA Test Store · <code>{{ store }}</code></p>
<p>Acceptation manuelle uniquement. Aucune vente dans la caisse, aucun envoi en cuisine et aucune impression. L’acceptation automatique reste désactivée.</p>
{% if message %}<p class="message">{{ message }}</p>{% endif %}
{% if manager is not none %}<p>Gestionnaire des commandes : <b>{{ 'notre application' if manager else 'non confirmé pour notre application' }}</b>.</p>{% endif %}
{% if manager is sameas false %}
<p>Avant de passer une nouvelle commande, autorisez notre application à gérer les commandes de ce restaurant test.</p>
<form method="post" action="/administration/uber-sandbox/start"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="mode" value="order_manager"><button>Autoriser la gestion du restaurant test sur Uber</button></form>
{% endif %}
<p><a href="/administration/uber-sandbox/orders">Actualiser les commandes et les droits Uber</a></p>
{% macro itemline(item) %}<li>{{ item.quantity }} × {{ item.title }}{% if item.get('removed') %} (retiré){% endif %}{% if item.total_price %} — {{ amount(item.total_price) }}{% endif %}
{% if item.options %}<ul class="options">{% for option in item.options %}{{ itemline(option) }}{% endfor %}</ul>{% endif %}</li>{% endmacro %}
{% if order %}<article><h2>Commande {{ order.display_id }}</h2><p>État chez Uber : <b>{{ order.current_state }}</b></p><ul>{% for item in order['items'] %}{{ itemline(item) }}{% endfor %}</ul>
{% if order.charges.total %}<p>Total restaurant transmis par Uber : <b>{{ amount(order.charges.total) }}</b></p>{% endif %}
<p>{{ order.amounts_note }}</p>
{% if can_accept %}<form method="post"><input type="hidden" name="csrf" value="{{ csrf }}"><input type="hidden" name="nonce" value="{{ nonce }}"><input type="hidden" name="order_id" value="{{ order.id }}"><button>Accepter cette commande test chez Uber</button></form>{% else %}<p>Aucune acceptation disponible pour cette commande.</p>{% endif %}</article>{% endif %}
{% if orders %}<h2>Notifications reçues</h2><ul>{% for id in orders %}<li><a href="?order_id={{ id }}">Commande {{ id[-5:] }}</a></li>{% endfor %}</ul>{% else %}<p>Aucune notification de commande reçue pour ce restaurant test.</p>{% endif %}
<p><a href="/administration/uber-sandbox">Retour à la configuration Uber</a></p></html>'''


def canonical_id(value):
    try:
        return str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def notified_orders(db):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('uber_webhook_inbox') IS NOT NULL AS inbox_exists")
            row = cur.fetchone()
            if not (row['inbox_exists'] if hasattr(row, 'keys') else row[0]):
                return []
            cur.execute("""SELECT payload #>> '{meta,resource_id}' AS order_id
                FROM uber_webhook_inbox WHERE event_type = 'orders.notification'
                AND %s IN (payload #>> '{meta,user_id}',
                    payload #>> '{meta,store_id}', payload ->> 'store_id')
                ORDER BY received_at DESC, event_key DESC LIMIT 20""", (STORE_ID,))
            ids = [r['order_id'] if hasattr(r, 'keys') else r[0] for r in cur.fetchall()]
    return list(dict.fromkeys(value for value in ids if canonical_id(value)))


def manager_status():
    token = get_token('client_credentials', scope='eats.store')
    details = call_uber(API + '/pos_data', token=token)
    if details.get('store_id') != STORE_ID:
        raise UberFailure('Uber n’a pas confirmé le restaurant de test attendu.')
    return (details.get('integration_enabled') is True
        and details.get('order_manager_client_id') == CLIENT_ID
        and details.get('is_order_manager_pending') is not True)


def fetch_order(order_id, token):
    raw = call_uber('https://test-api.uber.com/v2/eats/order/' + order_id,
        method='GET', token=token, response_limit=4 * 1024 * 1024)
    summary = order_summary(raw, order_id)  # verifies order and store identities
    return summary, raw.get('order_manager_client_id') == CLIENT_ID


def fingerprint(order):
    return hashlib.sha256(json.dumps(order, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def claim_attempt(db, order_id):
    # Commit the unique claim BEFORE the remote request: retries, concurrent
    # clicks and uncertain network responses cannot submit a second acceptance.
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute('''CREATE TABLE IF NOT EXISTS uber_sandbox_accept_attempts (
                order_id TEXT PRIMARY KEY, store_id TEXT NOT NULL,
                attempted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                outcome TEXT NOT NULL DEFAULT 'unknown'
            )''')
            cur.execute('''INSERT INTO uber_sandbox_accept_attempts (order_id, store_id)
                VALUES (%s, %s) ON CONFLICT (order_id) DO NOTHING RETURNING order_id''',
                (order_id, STORE_ID))
            claimed = cur.fetchone() is not None
        conn.commit()
    return claimed


def save_ack(db, order_id):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""UPDATE uber_sandbox_accept_attempts SET outcome = 'acknowledged'
                WHERE order_id = %s AND store_id = %s""", (order_id, STORE_ID))
        conn.commit()


def register_uber_sandbox_accept(app, db):
    @app.route('/administration/uber-sandbox/orders', methods=['GET', 'POST'])
    def uber_sandbox_orders():
        if session.get('caisse_auth') is not True:
            return Response('Ouvrez cette page depuis votre session caisse de test.', status=403)
        csrf = session.setdefault('uber_sandbox_csrf', secrets.token_urlsafe(32))

        def page(message='', status=200, orders=(), order=None, manager=None, can_accept=False, nonce=''):
            def amount(value):
                return f"{value['amount'] / 100:.2f} {value['currency_code']}".replace('.', ',')
            response = Response(render_template_string(PAGE, message=message, orders=orders,
                order=order, manager=manager, can_accept=can_accept, nonce=nonce,
                csrf=csrf, store=STORE_ID, amount=amount), status=status, content_type='text/html; charset=utf-8')
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'no-referrer'
            return response

        if request.method == 'POST':
            supplied = request.form.get('csrf', '')
            if not supplied or not hmac.compare_digest(csrf.encode(), supplied.encode()):
                return page('Accès refusé. Actualisez la page.', 403)
            preview = session.pop('uber_sandbox_accept_preview', None)
            order_id = request.form.get('order_id', '')
            if (not canonical_id(order_id) or not preview or preview.get('store_id') != STORE_ID
                or preview.get('order_id') != order_id
                or not hmac.compare_digest(str(preview.get('nonce', '')).encode(), request.form.get('nonce', '').encode())
                or not 0 <= time.time() - preview.get('created', 0) <= 180):
                return page('Aperçu expiré ou invalide. Actualisez la page avant d’accepter.', 409)
            claimed = False
            try:
                ids = notified_orders(db)
                if order_id not in ids:
                    return page('Notification introuvable pour ce restaurant test.', 404)
                manager = manager_status()
                if not manager:
                    return page('Droit de gestion des commandes non confirmé. Aucune acceptation envoyée.', 409, orders=ids, manager=False)
                token = get_token('client_credentials', scope='eats.order')
                order, order_manager = fetch_order(order_id, token)
                if order['current_state'] != 'CREATED' or not order_manager:
                    return page('Cette commande n’est plus en attente ou n’est pas gérée par notre application. Aucune acceptation envoyée.', 409, orders=ids, order=order, manager=manager)
                if fingerprint(order) != preview.get('fingerprint'):
                    return page('La commande a changé chez Uber. Actualisez son aperçu avant de l’accepter.', 409, orders=ids, order=order, manager=manager)
                claimed = claim_attempt(db, order_id)
                if not claimed:
                    return page('Une tentative a déjà été enregistrée pour cette commande. Aucun nouvel envoi. Actualisez pour vérifier son état chez Uber.', 409, orders=ids, order=order, manager=manager)
                call_uber('https://test-api.uber.com/v1/eats/orders/' + order_id + '/accept_pos_order',
                    method='POST', token=token, body={'reason': 'Acceptation manuelle — test sandbox BECHEFAA'})
                try:
                    save_ack(db, order_id)
                except Exception:
                    app.logger.error('Uber sandbox acceptance acknowledgement storage failed')
                return page('Uber a reçu la demande d’acceptation de cette commande test. Cliquez sur « Actualiser » pour contrôler son état. Aucune vente ni impression déclenchée.', orders=ids, manager=manager)
            except UberFailure as error:
                prefix = 'Une tentative a été enregistrée. Ne la renvoyez pas ; actualisez pour vérifier son état chez Uber. ' if claimed else 'Aucune acceptation envoyée. '
                return page(prefix + str(error), 502)
            except Exception:
                app.logger.error('Uber sandbox manual acceptance failed')
                return page('Contrôle indisponible. Aucune nouvelle tentative automatique ; actualisez pour vérifier l’état chez Uber.', 503)

        # GET is strictly read-only with respect to Uber and the database.
        session.pop('uber_sandbox_accept_preview', None)
        try:
            ids = notified_orders(db)
            manager = manager_status()
            order_id = request.args.get('order_id') or (ids[0] if ids else '')
            if not order_id:
                return page(orders=ids, manager=manager)
            if not canonical_id(order_id) or order_id not in ids:
                return page('Commande absente des notifications du restaurant test.', 404, orders=ids, manager=manager)
            token = get_token('client_credentials', scope='eats.store.orders.read')
            order, order_manager = fetch_order(order_id, token)
            can_accept = manager and order_manager and order['current_state'] == 'CREATED' and bool(order['items'])
            nonce = secrets.token_urlsafe(32) if can_accept else ''
            if can_accept:
                session['uber_sandbox_accept_preview'] = dict(store_id=STORE_ID, order_id=order_id,
                    fingerprint=fingerprint(order), created=time.time(), nonce=nonce)
            message = ''
            if manager and not order_manager and order['current_state'] == 'CREATED':
                message = 'Uber ne confirme pas notre application comme gestionnaire de cette commande. Aucune acceptation possible pour le moment.'
            return page(message, orders=ids, order=order, manager=manager, can_accept=can_accept, nonce=nonce)
        except UberFailure as error:
            return page(str(error), 502)
        except Exception:
            app.logger.error('Uber sandbox order preview failed')
            return page('Lecture des commandes de test indisponible. Aucune acceptation envoyée.', 503)
