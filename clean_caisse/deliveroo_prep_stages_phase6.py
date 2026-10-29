"""Manual sandbox preparation stages; no production access or payment writes."""
import hmac
import json
import os
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from urllib.error import HTTPError

STAGES = ('in_kitchen', 'ready_for_collection_soon', 'ready_for_collection', 'collected')


def next_stage(completed):
    if list(completed) != list(STAGES[:len(completed)]):
        raise ValueError('Invalid stored preparation sequence')
    return STAGES[len(completed)] if len(completed) < len(STAGES) else None


def stage_request(order_id, stage, token):
    if stage not in STAGES or not order_id.startswith('fr:'):
        raise ValueError('Invalid preparation stage or sandbox order ID')
    payload = {'stage': stage, 'occurred_at': datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')}
    return urllib.request.Request(
        'https://api-sandbox.developers.deliveroo.com/order/v1/orders/'
        + urllib.parse.quote(order_id, safe=':') + '/prep_stage',
        data=json.dumps(payload).encode(), method='POST',
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json', 'Accept': 'application/json'})


def register_deliveroo_prep_stages_phase6(app, db):
    from flask import jsonify, request, Response
    from .deliveroo_order_status_phase6 import order_status_and_log

    def allowed():
        return (os.environ.get('CC_APP_ID', '').strip() == 'app_fad0809f-954d-47e7-983d-afb7c3867cd0'
                and os.environ.get('BECHEFAA_DELIVEROO_ORDER_BRIDGE_ENABLED') == '1'
                and urllib.parse.urlparse(os.environ.get('BECHEFAA_DELIVEROO_API_URL') or 'https://api-sandbox.developers.deliveroo.com').hostname == 'api-sandbox.developers.deliveroo.com'
                and urllib.parse.urlparse(os.environ.get('BECHEFAA_DELIVEROO_AUTH_URL') or 'https://auth-sandbox.developers.deliveroo.com').hostname == 'auth-sandbox.developers.deliveroo.com')

    def authorized():
        pin = os.environ.get('BECHEFAA_CAISSE_PIN', '').strip()
        return allowed() and bool(pin) and hmac.compare_digest(pin, request.headers.get('X-Diagnostic-Pin', '').strip())

    def load_context(cur, order_id=None):
        cur.execute("SELECT order_id,sync_status,sync_http_status FROM deliveroo_webhook_diag WHERE kind='orders'")
        sync = cur.fetchone()
        if not sync or sync.get('sync_status') != 'succeeded' or sync.get('sync_http_status') != 200:
            raise ValueError('Attendre la synchronisation réussie de la commande du scénario 13')
        target = str(sync.get('order_id') or '')
        if order_id and order_id != target:
            raise ValueError('La dernière commande reçue a changé : recharger avant de continuer')
        cur.execute('SELECT payload,received_at FROM deliveroo_sandbox_events WHERE order_id=%s ORDER BY received_at DESC LIMIT 1', (target,))
        row = cur.fetchone()
        if not row or (datetime.now(timezone.utc) - row['received_at']).total_seconds() > 1800:
            raise ValueError('Aucune commande récente trouvée')
        payload = row['payload']
        if isinstance(payload, str):
            payload = json.loads(payload)
        status, log = order_status_and_log(payload)
        if status in {'canceled', 'cancelled', 'rejected', 'declined'} or not any(
                isinstance(entry, dict) and entry.get('status') == 'accepted' for entry in log):
            raise ValueError('Le webhook ne confirme pas une commande acceptée active')
        pos_id = 'deliveroo-' + uuid.uuid5(uuid.NAMESPACE_URL, target).hex
        cur.execute("SELECT num,status FROM caisse_orders WHERE id=%s AND sales_channel='DELIVEROO'", (pos_id,))
        ticket = cur.fetchone()
        if not ticket or str(ticket['status']).lower() in {'annulée', 'rejetée'}:
            raise ValueError('Commande absente ou annulée dans la caisse de préproduction')
        cur.execute("SELECT to_regclass('deliveroo_prep_stage_trace') AS table_name")
        completed = []
        if cur.fetchone()['table_name']:
            cur.execute('SELECT stage FROM deliveroo_prep_stage_trace WHERE order_id=%s ORDER BY position', (target,))
            completed = [r['stage'] for r in cur.fetchall()]
        order = (payload.get('body') or {}).get('order') or {}
        return {'order_id': target, 'pos_id': pos_id, 'ticket': ticket['num'],
                'reference': str(order.get('display_id') or ''), 'completed': completed, 'next': next_stage(completed)}

    @app.get('/api/deliveroo/prep-stages-state-phase6')
    def prep_state():
        if not authorized():
            return jsonify({'ok': False, 'error': 'Accès préproduction/PIN requis'}), 403
        try:
            with db() as conn:
                with conn.cursor() as cur:
                    context = load_context(cur)
            return jsonify({'ok': True, **context})
        except ValueError as exc:
            return jsonify({'ok': False, 'error': str(exc)}), 409
        except Exception:
            app.logger.exception('Deliveroo prep state read failed')
            return jsonify({'ok': False, 'error': 'Lecture impossible'}), 500

    @app.post('/api/deliveroo/prep-stage-phase6')
    def prep_stage():
        if not authorized():
            return jsonify({'ok': False, 'error': 'Accès préproduction/PIN requis'}), 403
        data = request.get_json(silent=True) or {}
        order_id, stage = str(data.get('order_id') or ''), str(data.get('stage') or '')
        if stage not in STAGES or not order_id.startswith('fr:'):
            return jsonify({'ok': False, 'error': 'Commande et étape requises'}), 400
        try:
            from .deliveroo_menu_upload_phase6 import _oauth_token
            with db() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('deliveroo-prep:' + order_id,))
                        context = load_context(cur, order_id)
                        if stage in context['completed']:
                            return jsonify({'ok': True, 'already_sent': True, **context})
                        if context['next'] != stage:
                            raise ValueError('Étape hors ordre : recharger la commande')
                        if stage == 'in_kitchen':
                            cur.execute("SELECT status FROM caisse_orders WHERE id=%s", (context['pos_id'],))
                            if str(cur.fetchone()['status']).lower() == 'terminée':
                                raise ValueError('Commande déjà terminée')
                        req = stage_request(order_id, stage, _oauth_token())
                        with urllib.request.urlopen(req, timeout=15) as response:
                            http_status = int(response.status)
                            response.read()
                        if http_status != 200:
                            raise ValueError('Réponse Deliveroo inattendue : HTTP ' + str(http_status))
                        cur.execute('''CREATE TABLE IF NOT EXISTS deliveroo_prep_stage_trace (
                            order_id TEXT NOT NULL, stage TEXT NOT NULL, position INTEGER NOT NULL,
                            occurred_at TIMESTAMPTZ NOT NULL, http_status INTEGER NOT NULL,
                            PRIMARY KEY(order_id,stage), UNIQUE(order_id,position))''')
                        sent = json.loads(req.data)
                        cur.execute('INSERT INTO deliveroo_prep_stage_trace(order_id,stage,position,occurred_at,http_status) VALUES (%s,%s,%s,%s,%s)',
                                    (order_id, stage, len(context['completed']), sent['occurred_at'], http_status))
                        local_status = {'in_kitchen': 'En préparation', 'ready_for_collection_soon': 'En préparation',
                                        'ready_for_collection': 'Prête', 'collected': 'Terminée'}[stage]
                        cur.execute("UPDATE caisse_orders SET status=%s,updated_at=%s WHERE id=%s AND sales_channel='DELIVEROO'",
                                    (local_status, int(datetime.now(timezone.utc).timestamp()*1000), context['pos_id']))
                        context['completed'].append(stage)
                        context['next'] = next_stage(context['completed'])
            return jsonify({'ok': True, 'http_status': http_status, 'sent': sent, **context})
        except ValueError as exc:
            return jsonify({'ok': False, 'error': str(exc)}), 409
        except HTTPError as exc:
            return jsonify({'ok': False, 'http_status': exc.code, 'error': 'Étape non confirmée par Deliveroo. Ne pas passer à la suivante.'}), 502
        except Exception:
            app.logger.exception('Deliveroo preparation stage failed')
            return jsonify({'ok': False, 'error': 'Envoi non confirmé. Recharger l’état avant toute nouvelle action.'}), 500

    @app.get('/api/deliveroo/prep-stages-page')
    def prep_page():
        if not allowed():
            return Response(status=404)
        return Response('''<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Préparation Deliveroo — Préproduction</title><style>body{font:17px system-ui;max-width:820px;margin:36px auto;padding:16px}button,input{padding:14px;margin:6px;font:inherit}button:disabled{opacity:.4}pre{white-space:pre-wrap;background:#f2f4f6;padding:14px}</style>
<h1>Préparation Deliveroo — Préproduction</h1><p>Scénario 13 : charger la commande acceptée, puis confirmer les quatre étapes dans l’ordre. Aucun paiement n’est effectué.</p>
<label>PIN de la caisse <input id="pin" type="password" autocomplete="off"></label><button id="load">Charger la commande</button>
<p id="order"></p><div id="steps"></div><pre id="result">Aucune étape envoyée.</pre>
<script>
let current=null,busy=false;const stages=['in_kitchen','ready_for_collection_soon','ready_for_collection','collected'];
const labels=['1 • Début de préparation','2 • Prête dans moins de 60 secondes','3 • Prête à être récupérée','4 • Récupérée'];
function render(){const box=document.getElementById('steps');box.replaceChildren();stages.forEach((stage,i)=>{const b=document.createElement('button');b.textContent=labels[i]+(current?.completed?.includes(stage)?' ✓':'');b.disabled=busy||current?.next!==stage;b.onclick=()=>send(stage);box.appendChild(b)});document.getElementById('load').disabled=busy;}
async function call(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'X-Diagnostic-Pin':document.getElementById('pin').value,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined,cache:'no-store'});const d=await r.json();document.getElementById('result').textContent=JSON.stringify(d,null,2);return r.ok&&d.ok?d:null;}
document.getElementById('load').onclick=async()=>{busy=true;render();try{current=await call('/api/deliveroo/prep-stages-state-phase6');document.getElementById('order').textContent=current?'Ticket '+current.ticket+' — référence Deliveroo '+current.reference+' — '+current.order_id:'';}catch(e){current=null;document.getElementById('result').textContent=e.message}finally{busy=false;render()}};
async function send(stage){if(!current||busy)return;if(!confirm('Confirmer « '+labels[stages.indexOf(stage)]+' » pour le ticket '+current.ticket+' de préproduction ?'))return;busy=true;render();try{const d=await call('/api/deliveroo/prep-stage-phase6',{order_id:current.order_id,stage});current=d;}catch(e){current=null;document.getElementById('result').textContent=e.message}finally{busy=false;render()}}
render();
</script></html>''', content_type='text/html; charset=utf-8')
