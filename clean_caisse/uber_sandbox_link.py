"""Authorization and read-only diagnostics for the one approved Uber test store."""
import hmac
import json
import os
import secrets
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

from flask import Response, redirect, render_template_string, request, session

CLIENT_ID = 'FCLBMak8LUkGK4SH9L6nbECkhta1Hq9p'
STORE_ID = '874dc6f0-80a8-4a22-a66a-28b693e59522'
CALLBACK = 'https://caisse.bechefaa.fr/api/uber/sandbox/callback'
AUTH = 'https://sandbox-login.uber.com/oauth/v2'
API = 'https://test-api.uber.com/v1/eats/stores/' + STORE_ID


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class UberFailure(Exception):
    pass


def call_uber(url, method='GET', token=None, form=None, body=None, response_limit=1024 * 1024):
    headers = {'Accept': 'application/json'}
    data = None
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if form is not None:
        data = urlencode(form).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    elif body is not None:
        data = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    try:
        with build_opener(NoRedirect()).open(Request(url, data=data, headers=headers, method=method), timeout=15) as response:
            raw = response.read(response_limit + 1)
            if len(raw) > response_limit:
                raise ValueError('response too large')
            result = json.loads(raw) if raw else {}
            if not isinstance(result, dict):
                raise ValueError('invalid response')
            return result
    except HTTPError as error:
        raise UberFailure('Uber a répondu HTTP ' + str(error.code) + '. Vérifiez les droits de l’application ou contactez leur support.') from None
    except (URLError, TimeoutError, ValueError):
        raise UberFailure('Réponse Uber indisponible ou invalide. Réessayez plus tard.') from None


def get_token(grant, **extra):
    secret = os.environ.get('BECHEFAA_UBER_CLIENT_SECRET', '')
    if not secret:
        raise UberFailure('La clé Uber est absente de la configuration serveur.')
    try:
        result = call_uber(AUTH + '/token', 'POST', form={
            'client_id': CLIENT_ID, 'client_secret': secret, 'grant_type': grant, **extra,
        })
    except UberFailure as error:
        raise UberFailure('Étape : authentification Uber (' + grant + '). ' + str(error)) from None
    token = result.get('access_token')
    if not isinstance(token, str) or not token:
        raise UberFailure('Uber n’a pas fourni de jeton d’accès.')
    return token


def register_uber_sandbox_link(app):
    from .uber_sandbox_menu import register_uber_sandbox_menu
    register_uber_sandbox_menu(app)
    def page(message=None, status=200):
        if message is not None:
            session['uber_sandbox_last_result'] = message
        else:
            message = session.get('uber_sandbox_last_result', '')
        if not session.get('uber_sandbox_csrf'):
            session['uber_sandbox_csrf'] = secrets.token_urlsafe(32)
        html = render_template_string('''<!doctype html><html lang="fr"><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1"><title>Uber Eats — restaurant de test</title>
        <style>body{font-family:Arial;max-width:760px;margin:40px auto;padding:20px;color:#17212b}button{padding:16px;margin:8px 0;font-size:18px;cursor:pointer}p{line-height:1.5}.result{background:#fff4ce;padding:18px;white-space:pre-wrap}code{overflow-wrap:anywhere}</style>
        <h1>Uber Eats — restaurant de test</h1><p>Restaurant : BÉCHÉFAA Test Store<br>Store ID : <code>{{ store }}</code></p>
        <p>Dans Uber Developer Dashboard, ajoutez cette adresse dans <b>Redirect URIs</b>, puis enregistrez :<br><code>{{ callback }}</code></p>
        {% if message %}<p class="result">{{ message }}</p>{% endif %}
        <form method="post" action="/administration/uber-sandbox/check"><input type="hidden" name="csrf" value="{{ csrf }}"><button>Vérifier la liaison du restaurant</button></form>
        <form method="post" action="/administration/uber-sandbox/start"><input type="hidden" name="csrf" value="{{ csrf }}"><button>Autoriser la liaison sur Uber</button></form>
        <p>Connectez-vous avec le compte du restaurant de test fourni par Uber. La liaison concerne exclusivement ce restaurant de test.</p>
        <p>La réception des webhooks est disponible. La récupération et l’acceptation des commandes sont encore en développement. Aucun test effectué ici ne crée de vente dans la caisse.</p>
        <p><a href="/administration/uber-sandbox/menu">Préparer et envoyer la carte de test</a></p>
        <a href="/pos">Retour à la caisse</a></html>''', store=STORE_ID, callback=CALLBACK,
            message=message, csrf=session['uber_sandbox_csrf'])
        response = Response(html, status=status, content_type='text/html; charset=utf-8')
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    def allowed(post=False):
        if session.get('caisse_auth') is not True:
            return False
        if post:
            supplied = request.form.get('csrf', '')
            expected = session.get('uber_sandbox_csrf', '')
            return bool(expected and supplied and hmac.compare_digest(expected, supplied))
        return True

    @app.get('/administration/uber-sandbox')
    def uber_sandbox_page():
        if not allowed():
            return redirect('/', code=303)
        return page()

    @app.post('/administration/uber-sandbox/check')
    def uber_sandbox_check():
        if not allowed(True):
            return Response('Accès refusé. Rouvrez la page depuis votre session caisse.', status=403)
        try:
            token = get_token('client_credentials', scope='eats.store')
            try:
                details = call_uber(API + '/pos_data', token=token)
            except UberFailure as error:
                raise UberFailure('Authentification réussie. Étape : lecture de la liaison du restaurant de test. ' + str(error)) from None
            if details.get('store_id') != STORE_ID:
                raise UberFailure('Uber n’a pas confirmé l’identifiant du restaurant attendu.')
            message = 'Liaison confirmée par Uber.' if details.get('integration_enabled') is True else 'Le restaurant est accessible, mais la liaison est désactivée. Lancez l’autorisation Uber.'
            return page(message)
        except UberFailure as error:
            return page(str(error), 502)

    @app.post('/administration/uber-sandbox/start')
    def uber_sandbox_start():
        if not allowed(True):
            return Response('Accès refusé. Rouvrez la page depuis votre session caisse.', status=403)
        if not os.environ.get('BECHEFAA_UBER_CLIENT_SECRET'):
            return page('La clé Uber est absente de la configuration serveur.', 503)
        state = secrets.token_urlsafe(32)
        session['uber_sandbox_oauth'] = {'state': state, 'created': time.time()}
        return redirect(AUTH + '/authorize?' + urlencode({
            'client_id': CLIENT_ID, 'response_type': 'code', 'redirect_uri': CALLBACK,
            'scope': 'eats.pos_provisioning', 'state': state,
        }), code=303)

    @app.get('/api/uber/sandbox/callback')
    def uber_sandbox_callback():
        if not allowed():
            return Response('Session caisse absente. Ouvrez la caisse et recommencez la liaison.', status=403)
        pending = session.pop('uber_sandbox_oauth', None)
        state = request.args.get('state', '')
        if not pending or not state or not hmac.compare_digest(str(pending.get('state', '')), state) or time.time() - pending.get('created', 0) > 600:
            return page('Autorisation expirée ou invalide. Recommencez depuis cette page.', 400)
        code = request.args.get('code', '')
        if request.args.get('error') or not code:
            return page('L’autorisation Uber n’a pas été accordée.', 400)
        try:
            token = get_token('authorization_code', code=code, redirect_uri=CALLBACK)
            # Verify that the authorizing account owns the exact test restaurant.
            try:
                stores = call_uber('https://test-api.uber.com/v1/eats/stores', token=token)
            except UberFailure as error:
                raise UberFailure('Autorisation reçue. Étape : recherche des restaurants du compte de test. ' + str(error)) from None
            if not any(isinstance(s, dict) and (s.get('store_id') or s.get('id')) == STORE_ID for s in stores.get('stores', [])):
                raise UberFailure('Ce compte Uber n’autorise pas notre restaurant de test. Utilisez le compte fourni par Uber.')
            # Observe-only until order retrieval and acceptance are implemented.
            try:
                call_uber(API + '/pos_data?' + urlencode({'is_order_manager': 'false', 'integrator_store_id': 'bechefaa-test'}), 'POST', token=token, body={})
            except UberFailure as error:
                raise UberFailure('Restaurant de test retrouvé. Étape : activation de la liaison. ' + str(error)) from None
            return page('Uber a accepté la demande de liaison du restaurant de test. Cliquez sur « Vérifier la liaison du restaurant » pour confirmer son état.')
        except UberFailure as error:
            return page(str(error), 502)
