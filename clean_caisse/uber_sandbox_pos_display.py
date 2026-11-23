"""Display-only Uber sandbox snapshots. Never write POS orders or payments."""
import hmac
import json

from flask import Response, jsonify, redirect, request, session

from .uber_sandbox_accept import canonical_id, fetch_order, notified_orders
from .uber_sandbox_link import STORE_ID, UberFailure, get_token

PREPROD_HOST = 'app-fad0809f-954d-47e7-983d-afb7c3867cd0.cleverapps.io'

PANEL = r'''
<style id="uber-sandbox-pos-style">
#uber-sandbox-pos{position:fixed;right:12px;bottom:12px;z-index:10010;background:#fff;color:#18251d;border:2px solid #167d46;border-radius:12px;box-shadow:0 4px 22px #0003;font:16px Arial,sans-serif;max-width:min(520px,94vw)}
#uber-sandbox-pos summary{padding:14px;cursor:pointer;font-weight:bold;background:#e7f6ec;border-radius:10px}
#uber-sandbox-pos section{padding:14px;max-height:65vh;overflow:auto}
#uber-sandbox-pos article{padding:12px 0;border-top:1px solid #ddd}
#uber-sandbox-pos p,#uber-sandbox-pos li{font:16px/1.45 Arial,sans-serif;margin:6px 0}
#uber-sandbox-pos ul{padding-left:24px;margin:6px 0}
#uber-sandbox-pos button{font:16px Arial,sans-serif;cursor:pointer;padding:10px}
</style>
<details id="uber-sandbox-pos"><summary>Uber Eats — TEST · <span data-uber-test-count>…</span></summary>
<section><p>Commandes d’essai, hors ventes et statistiques. Aucune impression ni modification du panier en cours.</p>
<button type="button" data-uber-test-refresh>Actualiser les commandes de test</button>
<p data-uber-test-status role="status"></p><div data-uber-test-orders></div>
<p><a href="/administration/uber-sandbox/orders">Importer une commande acceptée chez Uber</a></p></section></details>
<script id="uber-sandbox-pos-script">
(function(){
'use strict';
const root=document.getElementById('uber-sandbox-pos');if(!root)return;
const count=root.querySelector('[data-uber-test-count]'),status=root.querySelector('[data-uber-test-status]'),list=root.querySelector('[data-uber-test-orders]'),button=root.querySelector('[data-uber-test-refresh]');
function text(tag,value,parent){const el=document.createElement(tag);el.textContent=value;parent.appendChild(el);return el;}
function money(value){return value&&Number.isInteger(value.amount)?(value.amount/100).toLocaleString('fr-FR',{minimumFractionDigits:2,maximumFractionDigits:2})+' '+value.currency_code:'montant non transmis';}
function item(value,parent,depth){if(depth>8)return;const line=text('li',String(value.quantity)+' × '+String(value.title)+(value.removed?' (retiré)':'')+(value.total_price?' — '+money(value.total_price):''),parent);if(Array.isArray(value.options)&&value.options.length){const options=document.createElement('ul');line.appendChild(options);value.options.forEach(v=>item(v,options,depth+1));}}
async function refresh(){button.disabled=true;status.textContent='Lecture des commandes de test…';try{
 const response=await fetch('/api/uber/sandbox/pos-display',{cache:'no-store',credentials:'same-origin',headers:{Accept:'application/json'}});
 if(!response.ok)throw new Error('lecture indisponible');const data=await response.json();if(!data.ok||!Array.isArray(data.orders))throw new Error('réponse invalide');
 list.replaceChildren();count.textContent=String(data.orders.length);status.textContent=data.orders.length?'':'Aucune commande importée dans ce bloc de test.';
 data.orders.forEach(snapshot=>{const order=snapshot.order,card=document.createElement('article');text('h3','TEST · Uber '+String(order.display_id||order.id.slice(-5)),card);text('p','État lu à l’import : '+String(order.current_state),card);const ul=document.createElement('ul');card.appendChild(ul);order.items.forEach(v=>item(v,ul,0));text('p','Total restaurant Uber : '+money(order.charges.total),card);text('p','Importé le '+new Date(snapshot.imported_at).toLocaleString('fr-FR'),card);const a=document.createElement('a');a.textContent='Relire l’état actuel chez Uber';a.href='/administration/uber-sandbox/orders?order_id='+encodeURIComponent(order.id);card.appendChild(a);list.appendChild(card);});
}catch(error){status.textContent='Lecture indisponible. Cliquez sur Actualiser pour réessayer.';}finally{button.disabled=false;}}
button.addEventListener('click',refresh);refresh();
if(new URLSearchParams(location.search).has('uber_test_import'))root.open=true;
})();
</script>
'''


def preproduction_host():
    return request.host.split(':', 1)[0].lower() == PREPROD_HOST


def register_uber_sandbox_pos_display(app, db):
    @app.post('/administration/uber-sandbox/pos-display/import')
    def uber_sandbox_pos_import():
        if not preproduction_host():
            return Response('Affichage réservé à la caisse de préproduction.', status=404)
        if session.get('caisse_auth') is not True:
            return Response('Session caisse de test requise.', status=403)
        csrf = session.get('uber_sandbox_csrf', '')
        supplied = request.form.get('csrf', '')
        if not csrf or not supplied or not hmac.compare_digest(csrf.encode(), supplied.encode()):
            return Response('Actualisez la page des commandes de test.', status=403)
        order_id = request.form.get('order_id', '')
        if not canonical_id(order_id):
            return Response('Identifiant de commande invalide.', status=400)
        try:
            if order_id not in notified_orders(db):
                return Response('Notification absente pour ce restaurant test.', status=404)
            token = get_token('client_credentials', scope='eats.store.orders.read')
            order, _ = fetch_order(order_id, token)
            if order['current_state'] not in ('ACCEPTED', 'FINISHED'):
                return Response('Cette commande n’est pas acceptée chez Uber. Aucun import effectué.', status=409)
            # The projection from order_summary contains no customer credentials,
            # address or phone. This separate table is never read by sales,
            # accounting, kitchen, stock or printing paths.
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute('''CREATE TABLE IF NOT EXISTS uber_sandbox_display_orders (
                        store_id TEXT NOT NULL, order_id TEXT NOT NULL,
                        imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        summary JSONB NOT NULL,
                        PRIMARY KEY (store_id, order_id)
                    )''')
                    cur.execute('''INSERT INTO uber_sandbox_display_orders
                        (store_id, order_id, summary) VALUES (%s, %s, %s::jsonb)
                        ON CONFLICT (store_id, order_id) DO UPDATE
                        SET summary = EXCLUDED.summary, imported_at = NOW()''',
                        (STORE_ID, order_id, json.dumps(order)))
                conn.commit()
            response = redirect('/pos?uber_test_import=' + order_id, code=303)
        except UberFailure as error:
            response = Response('Import non effectué. ' + str(error), status=502)
        except Exception:
            app.logger.error('Uber sandbox display import failed')
            response = Response('Import indisponible. Réessayez depuis la page des commandes de test.', status=503)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/api/uber/sandbox/pos-display')
    def uber_sandbox_pos_list():
        def result(status=200, **values):
            response = jsonify(read_only=True, test_only=True, creates_pos_sales=False, **values)
            response.status_code = status
            response.headers['Cache-Control'] = 'no-store'
            return response
        if not preproduction_host():
            return result(404, ok=False, error='preproduction_required')
        if session.get('caisse_auth') is not True:
            return result(403, ok=False, error='caisse_session_required')
        try:
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT to_regclass('uber_sandbox_display_orders') IS NOT NULL AS display_exists")
                    row = cur.fetchone()
                    exists = row['display_exists'] if hasattr(row, 'keys') else row[0]
                    rows = []
                    if exists:
                        cur.execute('''SELECT imported_at, summary FROM uber_sandbox_display_orders
                            WHERE store_id = %s ORDER BY imported_at DESC, order_id DESC LIMIT 20''', (STORE_ID,))
                        for row in cur.fetchall():
                            imported_at, summary = ((row['imported_at'], row['summary'])
                                if hasattr(row, 'keys') else row)
                            if not isinstance(summary, dict) or summary.get('store_id') != STORE_ID:
                                raise ValueError('invalid sandbox snapshot')
                            rows.append({'imported_at': imported_at.isoformat(), 'order': summary})
            return result(ok=True, orders=rows, store_id=STORE_ID)
        except Exception:
            return result(503, ok=False, error='sandbox_display_unavailable')

    @app.after_request
    def uber_sandbox_pos_panel(response):
        if (not preproduction_host() or session.get('caisse_auth') is not True
            or request.path != '/pos' or response.status_code != 200
            or response.mimetype != 'text/html' or response.is_streamed):
            return response
        html = response.get_data(as_text=True)
        if 'id="uber-sandbox-pos"' not in html and '</body>' in html:
            response.set_data(html.replace('</body>', PANEL + '</body>', 1))
            response.headers['Cache-Control'] = 'no-store'
        return response
