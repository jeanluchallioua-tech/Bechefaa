"""Explicit production menu publication; independent of order-routing activation."""
import copy
import hashlib
import json
import os
import re
from decimal import Decimal, ROUND_HALF_UP
import urllib.error
import urllib.parse
import urllib.request
from flask import Response, jsonify, request
from .deliveroo_menu_builder_phase6 import build_deliveroo_menu_preview
from .deliveroo_production_phase6 import API_HOST, AUTH_HOST, PRODUCTION_APP, NoRedirect

MENU_ID = 'bechefaa-menu-01'
REVISION = 'production-menu-v5-identified-client-20261102'
INTEGRATOR_USER_AGENT = 'BECHEFAA-POS/1.0 (+https://caisse.bechefaa.fr)'
LEGACY_WRITES = {'/api/deliveroo/menu-upload-phase6'}


def target():
    brand = os.environ.get('BECHEFAA_DELIVEROO_PRODUCTION_BRAND_ID', '').strip()
    site = os.environ.get('BECHEFAA_DELIVEROO_PRODUCTION_SITE_ID', '').strip()
    if (os.environ.get('CC_APP_ID') != PRODUCTION_APP
        or os.environ.get('BECHEFAA_DELIVEROO_API_URL', '').rstrip('/') != API_HOST
        or os.environ.get('BECHEFAA_DELIVEROO_AUTH_URL', '').rstrip('/') != AUTH_HOST
        or not brand or brand == 'bceaa87a-74db-434e-b548-6da7e7de67a6'
        or not site or site == '101'
        or not os.environ.get('BECHEFAA_DELIVEROO_CLIENT_ID', '').strip()
        or not os.environ.get('BECHEFAA_DELIVEROO_CLIENT_SECRET', '').strip()):
        raise ValueError('Configuration production incomplète ou cible sandbox.')
    return {'brand_id': brand, 'site_id': site, 'menu_id': MENU_ID}


def production_formulas(menu, markup):
    """Confirmed production recipes; leave certified sandbox builder unchanged."""
    # The shared certification builder invents diet labels rather than reading
    # verified product data. Do not publish those assertions in production.
    for item in menu.get('items', []):
        if 'diets' in item:
            item['diets'] = []
    items = {item['id']: item for item in menu.get('items', [])}
    modifiers = {row['id']: row for row in menu.get('modifiers', [])}
    falafel = items.get('item_2')
    if falafel and falafel.get('type') == 'BUNDLE':
        if falafel.get('price_info', {}).get('price') != 1800:
            raise ValueError('La Formule Falafel Deliveroo doit rester à 18 €.')
        # Remove the certification-only premium Coca. All bundle drinks included.
        for item_id in modifiers['bundle_2_drink']['item_ids']:
            for override in items[item_id]['price_info'].get('overrides', []):
                if override.get('id') == 'item_2' and override.get('type') == 'ITEM':
                    override['price'] = 0
    child_bundle = items.get('item_4')
    if not child_bundle or child_bundle.get('type') != 'BUNDLE':
        return
    tender = copy.deepcopy(items['item_8'])
    original_groups = [modifiers[key] for key in tender.get('modifier_ids', [])]
    type_group = next((group for group in original_groups
                       if any(items[key].get('name', {}).get('fr', '').casefold().startswith('classic')
                              for key in group['item_ids'])), None)
    if type_group is None:
        raise ValueError('Choix Classique/Crispy introuvable pour la Formule Enfant.')
    selected = [key for key in type_group['item_ids']
                if items[key].get('name', {}).get('fr', '').casefold().startswith(('classic', 'crispy'))]
    if len(selected) != 2:
        raise ValueError('La Formule Enfant exige uniquement Classique ou Crispy.')
    # Context-specific copy: do not remove quantity/Cheesy options on standalone tenders.
    tender_id, group_id = 'prod_kids_tender', 'prod_kids_tender_type'
    if tender_id in items or group_id in modifiers:
        raise ValueError('Identifiants de formule déjà utilisés.')
    tender['id'] = tender_id
    tender['modifier_ids'] = [group_id]
    tender['price_info']['overrides'] = [{'type': 'ITEM', 'id': 'item_4', 'price': 0}]
    group = copy.deepcopy(type_group)
    group.update(id=group_id, item_ids=selected, min_selection=1, max_selection=1)
    menu['items'].append(tender)
    menu['modifiers'].append(group)
    modifiers['bundle_4_main']['item_ids'] = [tender_id]
    drinks = modifiers['bundle_2_drink']['item_ids']
    if 'item_76' not in drinks:
        raise ValueError('Capri-Sun absent du choix de boissons.')
    premium = int((Decimal('1.50') * (1 + Decimal(str(markup)) / 100) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    modifiers['bundle_4_drink']['item_ids'] = list(drinks)
    for item_id in drinks:
        price_info = items[item_id]['price_info']
        overrides = [row for row in price_info.get('overrides', [])
                     if not (row.get('id') == 'item_4' and row.get('type') == 'ITEM')]
        overrides.append({'type': 'ITEM', 'id': 'item_4', 'price': 0 if item_id == 'item_76' else premium})
        price_info['overrides'] = overrides


def make_preview(preview, destination):
    if not preview.get('ok') or preview.get('warnings') or preview.get('summary', {}).get('warnings'):
        raise ValueError('Corrigez les avertissements avant publication.')
    menu = copy.deepcopy(preview['payload']['menu'])
    production_formulas(menu, preview.get('markup_percentage', 20))
    items, categories, modifiers = menu.get('items', []), menu.get('categories', []), menu.get('modifiers', [])
    if not items or not categories or menu.get('currency_code') != 'EUR':
        raise ValueError('Menu vide ou devise inattendue.')
    def index(rows):
        result = {str(x.get('id', '')): x for x in rows}
        if '' in result or len(result) != len(rows):
            raise ValueError('Identifiants absents ou dupliqués dans le menu.')
        return result
    item_map, modifier_map = index(items), index(modifiers)
    index(categories)
    for item in items:
        if not item.get('plu') or not item.get('name') or any(x not in modifier_map for x in item.get('modifier_ids', [])):
            raise ValueError('PLU, nom ou références des options invalides.')
        price = item.get('price_info', {}).get('price')
        if type(price) is not int or price < 0:
            raise ValueError('Prix invalide dans le menu.')
    for row in categories + modifiers:
        if any(x not in item_map for x in row.get('item_ids', [])):
            raise ValueError('Référence article inconnue.')
    document = {'menu': menu, 'site_ids': [destination['site_id']], 'pos_name': 'BECHEFAA'}
    content = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    digest = hashlib.sha256(json.dumps(destination, sort_keys=True).encode() + b'\n' + content).hexdigest()
    summary = {**preview['summary'], 'main_items': sum(x.get('type') == 'ITEM' for x in items),
               'choice_items': sum(x.get('type') == 'CHOICE' for x in items),
               'bundles': sum(x.get('type') == 'BUNDLE' for x in items), 'modifiers': len(modifiers),
               'required_modifiers': sum(x.get('min_selection', 0) > 0 for x in modifiers)}
    return {'ok': True, 'revision': REVISION, 'target': destination, 'digest': digest,
            'summary': summary, 'markup_percentage': preview.get('markup_percentage'),
            'bytes': len(content), 'upload_performed': False, 'calls_deliveroo': False,
            'document': document, 'confirmation': f"PUBLIER {destination['brand_id']} / {destination['site_id']}"}


class ProviderFailure(Exception):
    def __init__(self, stage, status=None):
        self.stage, self.status = stage, status


class MenuTransport:
    def __init__(self, opener=None):
        self.opener = opener or urllib.request.build_opener(NoRedirect())

    def send(self, url, method, data=None, token=None, stage='provider', json_response=True):
        headers = {'Accept': 'application/json', 'User-Agent': INTEGRATOR_USER_AGENT}
        if data is not None: headers['Content-Type'] = 'application/json'
        if token: headers['Authorization'] = 'Bearer ' + token
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=25) as response:
                raw = response.read()
                if not 200 <= response.status < 300: raise ProviderFailure(stage, response.status)
                return json.loads(raw) if json_response else None
        except urllib.error.HTTPError as exc:
            code = exc.code
            exc.close()
            raise ProviderFailure(stage, code) from None

    def token(self):
        body = urllib.parse.urlencode({'client_id': os.environ['BECHEFAA_DELIVEROO_CLIENT_ID'],
                                      'client_secret': os.environ['BECHEFAA_DELIVEROO_CLIENT_SECRET'],
                                      'grant_type': 'client_credentials'}).encode()
        req = urllib.request.Request(AUTH_HOST + '/oauth2/token', data=body,
              headers={'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
        try:
            with self.opener.open(req, timeout=15) as response: data = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            code = exc.code; exc.close(); raise ProviderFailure('oauth', code) from None
        token = data.get('access_token')
        if not isinstance(token, str) or not token: raise ProviderFailure('oauth')
        return token

    def probe(self, path, token, identified_client=False):
        """Allowlisted read-only API probes. Never returns provider bodies/secrets."""
        if not (path.startswith('/site/v1/restaurant_locations/') or
                re.fullmatch(r'/menu/v1/brands/[^/]+/menus/[^/]+', path)):
            raise ValueError('Diagnostic path not permitted')
        request_headers={'Accept':'application/json','Authorization':'Bearer '+token}
        if identified_client:request_headers['User-Agent']=INTEGRATOR_USER_AGENT
        req=urllib.request.Request(API_HOST+path, headers=request_headers, method='GET')
        try:
            response=self.opener.open(req,timeout=15)
        except urllib.error.HTTPError as exc:
            response=exc
        try:
            status=getattr(response,'status',None) or response.code
            raw=response.read(2_000_000)
            headers=response.headers
            content_type=headers.get('Content-Type','').split(';')[0][:100]
            result={'method':'GET','path':path,'http_status':status,'content_type':content_type}
            result['request_profile']='identified_integrator' if identified_client else 'python_default'
            for header in ('X-Request-Id','X-Correlation-Id','CF-Ray','Server'):
                value=headers.get(header)
                if value and re.fullmatch(r'[A-Za-z0-9._:/ -]{1,160}',value):
                    result[header.lower()]=value
            try: data=json.loads(raw)
            except (ValueError,UnicodeError):data=None
            if isinstance(data,dict):
                result['response_format']='json'
                # Codes only; arbitrary error messages can contain reflected credentials.
                for key in ('code','error_code','error'):
                    value=data.get(key)
                    if isinstance(value,str) and re.fullmatch(r'[A-Z][A-Z0-9_.-]{0,79}|[a-z_]{1,60}',value):
                        result['provider_'+key]=value
                if path.startswith('/site/') and 200<=status<300:
                    brands=data.get('brand_id') or data.get('brand_ids') or []
                    if isinstance(brands,str):brands=[brands]
                    result['configured_brand_associated']=os.environ.get('BECHEFAA_DELIVEROO_PRODUCTION_BRAND_ID') in brands if isinstance(brands,list) else None
            else:
                result['response_format']='non_json'
                lower=raw[:100000].lower()
                result['response_class']='access_denied' if b'access denied' in lower else 'forbidden' if b'forbidden' in lower else 'other'
                # Return only fixed classifications, never arbitrary HTML/text.
                if headers.get('cf-mitigated','').lower()=='challenge' or b'cf-chl-' in lower or b'just a moment' in lower:
                    result['response_class']='cloudflare_challenge'
                elif b'sorry, you have been blocked' in lower:
                    result['response_class']='cloudflare_block_page'
                for code in ('1006','1007','1008','1010','1015','1020'):
                    if re.search(rb'(?:error\s*(?:code)?\s*:?\s*|error-code[^>]*>\s*)'+code.encode()+rb'\b',lower):
                        result['cloudflare_error_code']=code
                        break
            return result
        finally:
            response.close()

    @staticmethod
    def upload_url(data):
        if isinstance(data, dict):
            for value in data.values():
                found = MenuTransport.upload_url(value)
                if found: return found
        elif isinstance(data, list):
            for value in data:
                found = MenuTransport.upload_url(value)
                if found: return found
        elif isinstance(data, str):
            parsed = urllib.parse.urlsplit(data)
            if (parsed.scheme == 'https' and not parsed.username and not parsed.password
                and parsed.port in (None, 443) and not parsed.fragment
                and re.fullmatch(r'(?:[a-z0-9-]+\.)*s3(?:[.-][a-z0-9-]+)*\.amazonaws\.com', parsed.hostname or '')):
                return data
        return None

    def publish(self, prepared, progress):
        token = self.token()
        dest = prepared['target']
        brand = urllib.parse.quote(dest['brand_id'], safe='')
        menu = urllib.parse.quote(dest['menu_id'], safe='')
        progress('generate_s3')
        result = self.send(API_HOST + '/menu/v3/brands/' + brand + '/menus/' + menu,
                           'PUT', token=token, stage='generate_s3')
        url = self.upload_url(result)
        if not url: raise ProviderFailure('generate_s3')
        progress('s3_upload')
        content = json.dumps(prepared['document'], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        self.send(url, 'PUT', data=content, stage='s3_upload', json_response=False)
        progress('publish_job')
        result = self.send(API_HOST + '/menu/v3/brands/' + brand + '/jobs', 'POST',
               data=b'{"action":"publish_menu_to_live","params":{}}', token=token, stage='publish_job')
        job = result.get('job_id') or result.get('id') if isinstance(result, dict) else None
        if not isinstance(job, str) or not job: raise ProviderFailure('publish_job')
        return job


def ensure_table(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS deliveroo_production_menu_attempts(
        digest TEXT PRIMARY KEY, brand_id TEXT NOT NULL, site_id TEXT NOT NULL,
        menu_id TEXT NOT NULL, state TEXT NOT NULL, stage TEXT NOT NULL,
        job_id TEXT, http_status INTEGER, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())''')


def register_deliveroo_production_menu_phase6(app, db):
    if os.environ.get('CC_APP_ID') != PRODUCTION_APP: return
    transport = MenuTransport()
    app.config['BECHEFAA_DELIVEROO_MENU_TRANSPORT'] = transport

    def prepare(): return make_preview(build_deliveroo_menu_preview(db), target())

    @app.before_request
    def block_legacy_production_menu_tests():
        if request.method == 'POST' and (request.path in LEGACY_WRITES or request.path.startswith('/api/deliveroo/scenario')):
            return jsonify(ok=False, error='Outil de certification indisponible sur la caisse production.'), 409

    @app.get('/api/deliveroo/production-menu-preview')
    def production_menu_preview():
        try: return jsonify(prepare())
        except ValueError as exc: return jsonify(ok=False, error=str(exc), upload_performed=False), 409
        except Exception: return jsonify(ok=False, error='Aperçu production indisponible.', upload_performed=False), 503

    @app.get('/api/deliveroo/production-menu-access')
    def production_menu_access():
        try:
            dest=target()
            client=app.config['BECHEFAA_DELIVEROO_MENU_TRANSPORT']
            token=client.token()
            site_path='/site/v1/restaurant_locations/'+urllib.parse.quote(dest['site_id'],safe='')
            menu_path='/menu/v1/brands/'+urllib.parse.quote(dest['brand_id'],safe='')+'/menus/'+urllib.parse.quote(dest['menu_id'],safe='')
            probes=[]
            for path in (site_path,menu_path):
                try:
                    first=client.probe(path,token)
                    probes.append(first)
                    if first.get('http_status')==403 and first.get('content_type')=='text/html':
                        probes.append(client.probe(path,token,identified_client=True))
                except Exception: probes.append({'method':'GET','path':path,'error':'lecture_non_confirmee'})
            return jsonify(ok=True,revision=REVISION,target=dest,oauth_token_obtained=True,
                probes=probes,read_only=True,writes_database=False,
                s3_url_requested=False,upload_performed=False,order_routing_changed=False,
                note='Un menu absent peut répondre 404 avant son premier envoi. Un jeton valide ne prouve pas les droits sur la marque ni sur V3.')
        except ProviderFailure as exc:
            return jsonify(ok=False,stage=exc.stage,http_status=exc.status,upload_performed=False),502
        except Exception:
            return jsonify(ok=False,error='Diagnostic indisponible. Aucun envoi effectué.',upload_performed=False),503

    @app.post('/api/deliveroo/production-menu-publish')
    def production_menu_publish():
        if request.headers.get('Origin') != 'https://caisse.bechefaa.fr':
            return jsonify(ok=False, error='Publication uniquement depuis la caisse.'), 403
        body = request.get_json(silent=True)
        if not isinstance(body, dict): return jsonify(ok=False, error='Confirmation manquante.'), 400
        try: prepared = prepare()
        except Exception: return jsonify(ok=False, error='Aperçu ou configuration invalide.'), 409
        if body.get('digest') != prepared['digest'] or body.get('confirmation') != prepared['confirmation']:
            return jsonify(ok=False, error='Catalogue modifié ou confirmation incorrecte. Rechargez l’aperçu.'), 409
        dest, digest = prepared['target'], prepared['digest']
        # Session lock serializes the S3/job sequence for this brand. The durable
        # claim is committed before any external request and survives a crash.
        with db() as conn:
            locked = conn.execute('SELECT pg_try_advisory_lock(hashtext(%s)) AS acquired',
                                  ('deliveroo-production-menu:' + dest['brand_id'],)).fetchone()['acquired']
            conn.commit()
            if not locked: return jsonify(ok=False, error='Une publication est déjà en cours.'), 409
            try:
                with conn.transaction():
                    ensure_table(conn)
                    prior_rows = conn.execute("SELECT * FROM deliveroo_production_menu_attempts WHERE digest=%s OR (brand_id=%s AND state IN ('started','submitted','uncertain')) ORDER BY created_at DESC LIMIT 2", (digest, dest['brand_id'])).fetchall()
                    prior = prior_rows[0] if prior_rows else None
                    retry = (len(prior_rows)==1 and body.get('retry_denied_s3') is True
                        and prior['digest']==digest and prior['brand_id']==dest['brand_id']
                        and prior['site_id']==dest['site_id'] and prior['menu_id']==dest['menu_id']
                        and prior['state']=='uncertain' and prior['stage']=='generate_s3'
                        and prior['http_status']==403 and prior['job_id'] is None)
                    if prior and not retry:
                        return jsonify(ok=False, error='Tentative déjà enregistrée. Consultez son statut avant tout nouvel envoi.', attempt={k:prior[k] for k in ('digest','state','stage','job_id','http_status')}), 409
                    if retry:
                        # Preserve the refused pre-upload attempt; allow one explicitly
                        # confirmed recovery only. Never recover upload/job ambiguity.
                        conn.execute('''CREATE TABLE IF NOT EXISTS deliveroo_production_menu_recoveries(
                            digest TEXT PRIMARY KEY, previous_attempt JSONB NOT NULL,
                            recovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW())''')
                        archived=conn.execute('''INSERT INTO deliveroo_production_menu_recoveries(digest,previous_attempt)
                            SELECT digest,to_jsonb(a) FROM deliveroo_production_menu_attempts a WHERE digest=%s
                            ON CONFLICT DO NOTHING RETURNING digest''',(digest,)).fetchone()
                        if not archived:
                            return jsonify(ok=False,error='Reprise unique déjà utilisée. Aucun nouvel envoi.'),409
                        conn.execute("UPDATE deliveroo_production_menu_attempts SET state='started',stage='oauth',http_status=NULL,created_at=NOW() WHERE digest=%s",(digest,))
                    else:
                        conn.execute("INSERT INTO deliveroo_production_menu_attempts(digest,brand_id,site_id,menu_id,state,stage) VALUES(%s,%s,%s,%s,'started','oauth')", (digest,dest['brand_id'],dest['site_id'],dest['menu_id']))
                def progress(stage):
                    with conn.transaction(): conn.execute('UPDATE deliveroo_production_menu_attempts SET stage=%s WHERE digest=%s', (stage,digest))
                try:
                    job = app.config['BECHEFAA_DELIVEROO_MENU_TRANSPORT'].publish(prepared, progress)
                    with conn.transaction(): conn.execute("UPDATE deliveroo_production_menu_attempts SET state='submitted',stage='job_created',job_id=%s WHERE digest=%s", (job,digest))
                    return jsonify(ok=True, published=False, submitted=True, digest=digest, job_id=job, target=dest, next='Vérifier le statut du job et le menu dans le Hub. Les commandes ne sont pas activées.')
                except Exception as exc:
                    stage, status = getattr(exc,'stage',None), getattr(exc,'status',None)
                    with conn.transaction(): conn.execute("UPDATE deliveroo_production_menu_attempts SET state='uncertain',stage=COALESCE(%s,stage),http_status=%s WHERE digest=%s", (stage,status,digest))
                    return jsonify(ok=False, error='Résultat non confirmé. Ne pas renvoyer le menu.', digest=digest, stage=stage, http_status=status), 502
            finally:
                conn.execute('SELECT pg_advisory_unlock(hashtext(%s))', ('deliveroo-production-menu:' + dest['brand_id'],))
                conn.commit()

    @app.get('/api/deliveroo/production-menu-job')
    def production_menu_job():
        try:
            dest = target()
            with db() as conn:
                exists=conn.execute("SELECT to_regclass('deliveroo_production_menu_attempts') AS name").fetchone()['name']
                if not exists: return jsonify(ok=True, attempt=None, calls_deliveroo=False)
                row = conn.execute('SELECT digest,state,stage,job_id,http_status FROM deliveroo_production_menu_attempts WHERE brand_id=%s AND site_id=%s AND menu_id=%s ORDER BY created_at DESC LIMIT 1', (dest['brand_id'],dest['site_id'],dest['menu_id'])).fetchone()
            if not row or not row['job_id']: return jsonify(ok=True, attempt=dict(row) if row else None, calls_deliveroo=False)
            client=app.config['BECHEFAA_DELIVEROO_MENU_TRANSPORT']
            data=client.send(API_HOST+'/menu/v3/brands/'+urllib.parse.quote(dest['brand_id'],safe='')+'/jobs/'+urllib.parse.quote(row['job_id'],safe=''), 'GET',token=client.token(),stage='job_status')
            if data.get('status') in ('success','failed','failure'):
                with db() as conn: conn.execute('UPDATE deliveroo_production_menu_attempts SET state=%s WHERE digest=%s', ('success' if data['status']=='success' else 'failed',row['digest']))
            return jsonify(ok=True, target=dest, attempt=dict(row), response={k:data[k] for k in ('id','status','type','details') if k in data}, calls_deliveroo=True, order_routing_changed=False)
        except Exception: return jsonify(ok=False, error='Statut indisponible. Aucun nouvel envoi effectué.'), 502

    @app.get('/administration/deliveroo-production-menu')
    def production_menu_page():
        return Response(PAGE, content_type='text/html; charset=utf-8')


PAGE = '''<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Menu Deliveroo production</title>
<style>body{font:16px Arial;background:#f4f7fb;color:#14213d;margin:0}main{max-width:900px;margin:30px auto;padding:24px;background:white;border-radius:16px}button,input{padding:12px;font:inherit;margin:8px 0;max-width:100%;box-sizing:border-box}input{width:100%}button{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#edf3fa;padding:16px}#publish{background:#a1271c;color:white}button:disabled{opacity:.5;cursor:not-allowed}</style>
<main><h1>Menu Deliveroo — Production</h1><p>Vérifiez la cible, les prix, les options, les formules, les photos et les horaires avant publication. Ce menu remplacera celui des établissements ciblés. La connexion des commandes reste une étape distincte dans le Partner Hub.</p>
<button id="load">1. Préparer l’aperçu sans envoyer</button><pre id="summary">Aucun aperçu chargé.</pre><a id="document" hidden>Télécharger le menu à vérifier</a>
<label for="confirm">Pour publier, recopiez exactement la phrase affichée dans l’aperçu :</label><input id="confirm" autocomplete="off"><button id="publish" disabled>2. Publier ce menu en production</button>
<label style="display:block"><input id="retry" type="checkbox" style="width:auto"> Autoriser une reprise unique si la tentative précédente a été refusée avant l’envoi du menu (403 à la création de l’URL).</label>
<button id="status">3. Lire le statut de la dernière tentative</button><pre id="result" role="status">Aucun envoi effectué depuis cet écran.</pre></main>
<script>let preview=null,blobUrl=null;const el=id=>document.getElementById(id);const show=x=>el('result').textContent=JSON.stringify(x,null,2);
el('load').onclick=async()=>{el('publish').disabled=true;el('confirm').value='';preview=null;try{let r=await fetch('/api/deliveroo/production-menu-preview',{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok){show(d);return}preview=d;let {document,...summary}=d;el('summary').textContent=JSON.stringify(summary,null,2);if(blobUrl)URL.revokeObjectURL(blobUrl);blobUrl=URL.createObjectURL(new Blob([JSON.stringify(document,null,2)],{type:'application/json'}));el('document').href=blobUrl;el('document').download='bechefaa-menu-production.json';el('document').textContent='Télécharger le menu à vérifier';el('document').hidden=false;}catch(e){show({error:'Aperçu indisponible.'})}};
el('confirm').oninput=()=>{el('publish').disabled=!preview||el('confirm').value!==preview.confirmation};
el('publish').onclick=async()=>{if(!preview||el('confirm').value!==preview.confirmation)return;el('publish').disabled=true;el('load').disabled=true;try{let r=await fetch('/api/deliveroo/production-menu-publish',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({digest:preview.digest,confirmation:el('confirm').value,retry_denied_s3:el('retry').checked})});show(await r.json())}catch(e){show({error:'Réponse interrompue. Consultez le statut ; ne renvoyez pas.'})}finally{preview=null;el('confirm').value='';el('retry').checked=false;el('load').disabled=false}};
el('status').onclick=async()=>{el('status').disabled=true;try{let r=await fetch('/api/deliveroo/production-menu-job',{cache:'no-store'});show(await r.json())}catch(e){show({error:'Statut indisponible.'})}finally{el('status').disabled=false}};
</script></html>'''

