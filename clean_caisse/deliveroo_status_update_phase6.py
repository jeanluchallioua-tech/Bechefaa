"""Manual acceptance and rejection of sandbox ASAP orders; no production or payment writes."""
import hmac
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from urllib.error import HTTPError

STATUS_REVISION = 'manual-status-v3-20261029'


REJECT_REASONS = frozenset({'closing_early', 'busy', 'ingredient_unavailable', 'other'})

def status_request(order_id, token, action, reason=None):
    if action not in ('accepted', 'rejected', 'confirmed'):
        raise ValueError('Action invalide')
    data = {'status': action}
    if action == 'rejected':
        if reason not in REJECT_REASONS:
            raise ValueError('Motif de rejet obligatoire et valide')
        data.update(reject_reason=reason, notes='Test sandbox : rejet demandé par le scénario de certification')
    if not order_id.startswith('fr:'):
        raise ValueError('Invalid sandbox order ID')
    return urllib.request.Request(
        'https://api-sandbox.developers.deliveroo.com/order/v1/orders/' + urllib.parse.quote(order_id, safe=':'),
        data=json.dumps(data).encode(), method='PATCH',
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
                 'Accept': 'application/json', 'User-Agent': 'Bechefaa-Deliveroo-Integration/1.0'})


def accept_request(order_id, token):
    return status_request(order_id, token, 'accepted')

def parse_scheduled_time(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if stamp.tzinfo is None: raise ValueError()
        return stamp.astimezone(timezone.utc)
    except (ValueError, TypeError):
        raise ValueError('Horodatage programmé absent ou invalide')

def validate_accept_candidate(payload, scheduled=False, confirming=False, enforce_time=True):
    from .deliveroo_order_plu_phase6 import missing_plu_paths, mismatched_sandbox_plu_paths
    from .deliveroo_order_pricing_phase6 import net_item_cents
    body = payload.get('body') if isinstance(payload, dict) else None
    order = body.get('order') if isinstance(body, dict) else None
    if not isinstance(order, dict) or not order.get('id'):
        raise ValueError('Commande complète absente')
    if str(order.get('location_id') or '') != '101':
        raise ValueError('Cette commande ne concerne pas le site sandbox 101')
    if str(order.get('status') or '').lower() != ('accepted' if confirming else 'placed'):
        raise ValueError('Statut incompatible : ' + ('accepted requis pour confirmer' if confirming else 'placed requis pour accepter ou rejeter'))
    if order.get('asap') is not (False if scheduled else True):
        raise ValueError('Type de commande incompatible avec cette action')
    if scheduled:
        confirm_at = parse_scheduled_time(order.get('confirm_at'))
        parse_scheduled_time(order.get('start_preparing_at'))
        if confirming and enforce_time and datetime.now(timezone.utc) < confirm_at:
            raise ValueError('Trop tôt : attendre confirm_at avant de confirmer')
    items = order.get('items')
    if not isinstance(items, list) or not items:
        raise ValueError('Panier absent')
    if missing_plu_paths(payload) or mismatched_sandbox_plu_paths(payload):
        raise ValueError('PLU manquant ou incohérent : ne pas accepter')
    for item in items:
        if not isinstance(item, dict) or not str(item.get('name') or '').strip() or not isinstance(item.get('quantity'), int) or isinstance(item.get('quantity'), bool) or item['quantity'] <= 0:
            raise ValueError('Article incomplet')
    net_item_cents(order)
    return order


def register_deliveroo_status_update_phase6(app, db):
    from flask import jsonify as flask_jsonify, request, Response
    from .deliveroo_prep_stages_phase6 import safe_deliveroo_error

    def jsonify(data):
        return flask_jsonify({'status_revision': STATUS_REVISION, **data})

    def allowed():
        return (os.environ.get('CC_APP_ID', '').strip() == 'app_fad0809f-954d-47e7-983d-afb7c3867cd0'
                and os.environ.get('BECHEFAA_DELIVEROO_ORDER_BRIDGE_ENABLED') == '1'
                and urllib.parse.urlparse(os.environ.get('BECHEFAA_DELIVEROO_API_URL') or 'https://api-sandbox.developers.deliveroo.com').hostname == 'api-sandbox.developers.deliveroo.com'
                and urllib.parse.urlparse(os.environ.get('BECHEFAA_DELIVEROO_AUTH_URL') or 'https://auth-sandbox.developers.deliveroo.com').hostname == 'auth-sandbox.developers.deliveroo.com')

    def authorized():
        pin = os.environ.get('BECHEFAA_CAISSE_PIN', '').strip()
        return allowed() and bool(pin) and hmac.compare_digest(pin, request.headers.get('X-Diagnostic-Pin', '').strip())

    def read_candidate(cur, target=None, scheduled=False, confirming=False):
        if target:
            cur.execute('SELECT order_id,payload,received_at FROM deliveroo_sandbox_events WHERE order_id=%s ORDER BY received_at DESC LIMIT 1', (target,))
            rows = [cur.fetchone()]
        else:
            cur.execute('''SELECT order_id,payload,received_at FROM (
                SELECT DISTINCT ON (order_id) order_id,payload,received_at FROM deliveroo_sandbox_events
                ORDER BY order_id,received_at DESC) latest ORDER BY received_at DESC LIMIT 20''')
            rows = cur.fetchall()
        for row in rows:
            if not row or (datetime.now(timezone.utc) - row['received_at']).total_seconds() > 600:
                continue
            payload = row['payload']
            if isinstance(payload, str): payload = json.loads(payload)
            order = (payload.get('body') or {}).get('order') or {}
            if not target and (order.get('status') not in (('placed', 'accepted') if scheduled else ('placed',)) or order.get('asap') is not (False if scheduled else True)):
                continue
            order = validate_accept_candidate(payload, scheduled, confirming or (scheduled and not target and order.get('status') == 'accepted'), enforce_time=bool(target))
            if str(order['id']) != str(row['order_id']):
                raise ValueError('Identifiants de commande incohérents')
            return {'order_id': str(order['id']), 'reference': str(order.get('display_id') or ''),
                    'status': order['status'], 'total': order.get('total_price'), 'item_count': len(order['items']),
                    'asap': order['asap'], 'confirm_at': order.get('confirm_at'), 'start_preparing_at': order.get('start_preparing_at'),
                    'server_time': datetime.now(timezone.utc).isoformat()}
        raise ValueError('Aucune nouvelle commande ' + ('programmée placed/accepted' if scheduled else 'ASAP placed') + ' récente. Ne pas relancer un test déjà validé.')

    @app.get('/api/deliveroo/scheduled-state-phase6')
    def scheduled_state():
        return state_response(scheduled=True)

    @app.get('/api/deliveroo/status-update-state-phase6')
    def status_state():
        return state_response()

    def state_response(scheduled=False):
        if not authorized(): return jsonify({'ok': False, 'error': 'Accès préproduction/PIN requis'}), 403
        try:
            with db() as conn:
                with conn.cursor() as cur: context = read_candidate(cur, scheduled=scheduled)
            return jsonify({'ok': True, **context})
        except ValueError as exc: return jsonify({'ok': False, 'error': str(exc)}), 409
        except Exception:
            app.logger.exception('Deliveroo placed-order read failed')
            return jsonify({'ok': False, 'error': 'Lecture impossible'}), 500

    def send_action(action, scheduled=False):
        if not authorized(): return jsonify({'ok': False, 'error': 'Accès préproduction/PIN requis'}), 403
        data = request.get_json(silent=True) or {}
        reason = data.get('reject_reason')
        if action == 'rejected' and (not isinstance(reason, str) or reason not in REJECT_REASONS):
            return jsonify({'ok': False, 'error': 'Motif de rejet obligatoire et valide'}), 400
        target = str(data.get('order_id') or '')
        if not target.startswith('fr:'): return jsonify({'ok': False, 'error': 'Commande requise'}), 400
        try:
            from .deliveroo_menu_upload_phase6 import _oauth_token
            with db() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('deliveroo-status:' + target,))
                        cur.execute('''CREATE TABLE IF NOT EXISTS deliveroo_status_action_trace (
                            order_id TEXT NOT NULL, action TEXT NOT NULL, sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            http_status INTEGER NOT NULL, PRIMARY KEY(order_id,action))''')
                        cur.execute("SELECT action,http_status FROM deliveroo_status_action_trace WHERE order_id=%s ORDER BY sent_at DESC LIMIT 1", (target,))
                        previous = cur.fetchone()
                        if previous and previous['action'] != action and not (scheduled and action == 'confirmed' and previous['action'] == 'accepted'):
                            raise ValueError('Une autre action a déjà été confirmée pour cette commande')
                        if previous and previous['action'] == action:
                            return jsonify({'ok': True, 'order_id': target, 'already_sent': True, 'http_status': previous['http_status']})
                        context = read_candidate(cur, target, scheduled, action == 'confirmed')
                        req = status_request(target, _oauth_token(), action, reason)
                        with urllib.request.urlopen(req, timeout=15) as response:
                            status = int(response.status)
                            response.read()
                        if status != 204: raise ValueError('Réponse inattendue : HTTP ' + str(status))
                        cur.execute("INSERT INTO deliveroo_status_action_trace(order_id,action,http_status) VALUES (%s,%s,%s)", (target, action, status))
            return jsonify({'ok': True, 'http_status': status, 'sent': {'status': action, **({'reject_reason': reason} if action == 'rejected' else {})},
                            'next': ('Attendre confirm_at puis confirmer la commande programmée' if scheduled and action == 'accepted' else 'Vérifier le résultat Deliveroo' if action == 'confirmed' else 'Attendre le webhook rejected et le résultat Deliveroo ; aucun ticket attendu' if action == 'rejected' else 'Attendre le webhook accepted puis vérifier la caisse et le résultat Deliveroo'), **context, 'status': action})
        except ValueError as exc: return jsonify({'ok': False, 'error': str(exc)}), 409
        except HTTPError as exc:
            retry = (exc.headers or {}).get('Retry-After')
            return jsonify({'ok': False, 'http_status': exc.code, 'deliveroo_error': safe_deliveroo_error(exc),
                            'retry_after_seconds': int(retry) if str(retry or '').isdigit() else None,
                            'error': 'Action non confirmée. Ne pas relancer la commande.'}), 502
        except Exception:
            app.logger.exception('Deliveroo manual status update failed')
            return jsonify({'ok': False, 'error': 'Envoi non confirmé. Vérifier les traces avant toute nouvelle tentative.'}), 500

    @app.post('/api/deliveroo/accept-asap-phase6')
    def accept_asap():
        return send_action('accepted')

    @app.post('/api/deliveroo/reject-asap-phase6')
    def reject_asap():
        return send_action('rejected')

    @app.post('/api/deliveroo/accept-scheduled-phase6')
    def accept_scheduled():
        return send_action('accepted', scheduled=True)

    @app.post('/api/deliveroo/confirm-scheduled-phase6')
    def confirm_scheduled():
        return send_action('confirmed', scheduled=True)

    @app.get('/api/deliveroo/status-update-page')
    def status_page():
        if not allowed(): return Response(status=404)
        return Response('''<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Accepter ou rejeter — Préproduction</title><style>body{font:17px system-ui;max-width:850px;margin:30px auto;padding:16px}input,button{font:inherit;padding:14px;margin:8px}button:disabled{opacity:.4}pre{background:#f2f4f6;padding:16px;white-space:pre-wrap}</style>
<h1>Accepter ou rejeter — Préproduction</h1><p>Update Order Status API • Scénarios ASAP : acceptation ou rejet • Aucun paiement.</p>
<label>PIN de la caisse <input id="pin" type="password" autocomplete="off"></label>
<button id="load">Charger la nouvelle commande ASAP</button><p id="order"></p>
<button id="accept" disabled>Accepter la commande</button><label>Motif du rejet <select id="reason"><option value="other">Autre — test sandbox</option><option value="busy">Trop de commandes</option><option value="ingredient_unavailable">Ingrédient indisponible</option><option value="closing_early">Fermeture anticipée</option></select></label><button id="reject" disabled>Rejeter la commande</button><pre id="result">Aucun envoi effectué.</pre>
<script>
let current=null,busy=false;
function render(){document.getElementById('load').disabled=busy;document.getElementById('accept').disabled=busy||!current;document.getElementById('reject').disabled=busy||!current;}
async function call(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'X-Diagnostic-Pin':document.getElementById('pin').value,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined,cache:'no-store'});const d=await r.json();document.getElementById('result').textContent=JSON.stringify(d,null,2);return r.ok&&d.ok?d:null;}
document.getElementById('load').onclick=async()=>{busy=true;render();try{current=await call('/api/deliveroo/status-update-state-phase6');document.getElementById('order').textContent=current?'Référence '+current.reference+' — '+current.order_id+' — '+current.item_count+' article(s)':'';}catch(e){current=null;document.getElementById('result').textContent=e.message}finally{busy=false;render()}};
document.getElementById('accept').onclick=async()=>{if(!current||busy)return;if(!confirm('Accepter uniquement la commande '+current.reference+' dans le sandbox Deliveroo ?'))return;busy=true;render();try{await call('/api/deliveroo/accept-asap-phase6',{order_id:current.order_id});}catch(e){document.getElementById('result').textContent=e.message}finally{current=null;busy=false;render()}};
document.getElementById('reject').onclick=async()=>{if(!current||busy)return;if(!confirm('Rejeter uniquement la commande '+current.reference+' dans le sandbox Deliveroo, motif : '+document.getElementById('reason').selectedOptions[0].text+' ?'))return;busy=true;render();try{await call('/api/deliveroo/reject-asap-phase6',{order_id:current.order_id,reject_reason:document.getElementById('reason').value});}catch(e){document.getElementById('result').textContent=e.message}finally{current=null;busy=false;render()}};
</script></html>''', content_type='text/html; charset=utf-8')

    @app.get('/api/deliveroo/scheduled-status-page')
    def scheduled_page():
        if not allowed(): return Response(status=404)
        return Response('''<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Commande programmée — Préproduction</title>
<style>body{font:17px system-ui;max-width:850px;margin:30px auto;padding:16px}input,button{font:inherit;padding:14px;margin:8px}button:disabled{opacity:.4}pre{background:#f2f4f6;padding:16px;white-space:pre-wrap}</style>
<h1>Commande programmée — Préproduction</h1><p>1. Accepter. 2. Attendre confirm_at. 3. Confirmer.</p>
<label>PIN de la caisse <input id="pin" type="password" autocomplete="off"></label>
<button id="load">Charger la commande programmée</button><p id="order"></p><p id="clock"></p>
<button id="accept" disabled>Accepter la commande programmée</button>
<button id="confirm" disabled>Confirmer la commande programmée</button><pre id="result">Aucun envoi effectué.</pre>
<script>
let current=null,busy=false,offset=0;
function render(){const c=current;document.getElementById('load').disabled=busy;document.getElementById('accept').disabled=busy||!c||c.status!=='placed';const wait=c?Math.max(0,Math.ceil((Date.parse(c.confirm_at)-Date.now()-offset)/1000)):0;document.getElementById('confirm').disabled=busy||!c||c.status!=='accepted'||wait>0;document.getElementById('clock').textContent=c?'Confirmation autorisée à '+new Date(c.confirm_at).toLocaleTimeString('fr-FR')+(wait?' — attendre '+wait+' s':' — heure atteinte'):'';}
async function call(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'X-Diagnostic-Pin':document.getElementById('pin').value,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined,cache:'no-store'});const d=await r.json();document.getElementById('result').textContent=JSON.stringify(d,null,2);if(!r.ok||!d.ok)return null;if(d.server_time)offset=Date.parse(d.server_time)-Date.now();return d;}
document.getElementById('load').onclick=async()=>{busy=true;render();try{current=await call('/api/deliveroo/scheduled-state-phase6');document.getElementById('order').textContent=current?'Référence '+current.reference+' — '+current.order_id:'';}catch(e){current=null;document.getElementById('result').textContent=e.message}finally{busy=false;render()}};
async function send(action){if(!current||busy)return;if(!window.confirm((action==='accept'?'Accepter':'Confirmer')+' la commande sandbox '+current.reference+' ?'))return;busy=true;render();try{const result=await call('/api/deliveroo/'+action+'-scheduled-phase6',{order_id:current.order_id});current=result&&!result.already_sent?result:null;}catch(e){current=null;document.getElementById('result').textContent=e.message}finally{busy=false;render()}}
document.getElementById('accept').onclick=()=>send('accept');document.getElementById('confirm').onclick=()=>send('confirm');setInterval(render,500);
</script></html>''', content_type='text/html; charset=utf-8')
