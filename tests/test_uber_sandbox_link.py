import os
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from flask import Flask
from clean_caisse.uber_sandbox_link import register_uber_sandbox_link, STORE_ID, CLIENT_ID, CALLBACK, UberFailure


class UberSandboxLinkTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'unit-test-only'
        register_uber_sandbox_link(self.app)
        self.client = self.app.test_client()
        self.env = patch.dict(os.environ, {'BECHEFAA_UBER_CLIENT_SECRET': 'unit-secret'})
        self.env.start()
        self.addCleanup(self.env.stop)
        with self.client.session_transaction() as session:
            session['caisse_auth'] = True
            session['uber_sandbox_csrf'] = 'unit-csrf'

    def start(self):
        return self.client.post('/administration/uber-sandbox/start', data={'csrf': 'unit-csrf'})

    def callback(self, state=None):
        if state is None:
            result = self.start()
            state = parse_qs(urlsplit(result.headers['Location']).query)['state'][0]
        return self.client.get('/api/uber/sandbox/callback', query_string={'state': state, 'code': 'one-use-code'})

    def test_authentication_and_csrf_required_before_any_network(self):
        with patch('clean_caisse.uber_sandbox_link.call_uber') as network:
            self.assertEqual(self.client.post('/administration/uber-sandbox/check').status_code, 403)
            with self.client.session_transaction() as session:
                session.clear()
            self.assertEqual(self.client.get('/administration/uber-sandbox').status_code, 303)
            self.assertEqual(self.callback('invalid').status_code, 403)
            network.assert_not_called()

    def test_start_uses_only_sandbox_and_does_not_expose_secret(self):
        response = self.start()
        url = urlsplit(response.headers['Location'])
        args = parse_qs(url.query)
        self.assertEqual(url.netloc, 'sandbox-login.uber.com')
        self.assertEqual(args['client_id'], [CLIENT_ID])
        self.assertEqual(args['redirect_uri'], [CALLBACK])
        self.assertEqual(args['scope'], ['eats.pos_provisioning'])
        self.assertNotIn('unit-secret', response.headers['Location'])

    def test_bad_or_expired_state_makes_no_network_calls(self):
        with patch('clean_caisse.uber_sandbox_link.call_uber') as network:
            self.start()
            self.assertEqual(self.callback('wrong').status_code, 400)
            with self.client.session_transaction() as session:
                session['uber_sandbox_oauth'] = {'state': 'expired', 'created': time.time()-601}
            self.assertEqual(self.callback('expired').status_code, 400)
            network.assert_not_called()

    def test_wrong_merchant_cannot_activate_store(self):
        with patch('clean_caisse.uber_sandbox_link.call_uber', side_effect=[{'access_token':'private-token'},{'stores':[{'store_id':'other-store'}]}]) as network:
            response = self.callback()
            self.assertEqual(response.status_code, 502)
            self.assertEqual(network.call_count, 2)
            self.assertNotIn(b'private-token', response.data)

    def test_activation_restricted_to_one_test_store_without_order_manager(self):
        with patch('clean_caisse.uber_sandbox_link.call_uber', side_effect=[{'access_token':'private-token'},{'stores':[{'store_id':STORE_ID}]},{}]) as network:
            response = self.callback()
            self.assertEqual(response.status_code, 200)
            activation = network.call_args_list[-1]
            self.assertTrue(activation.args[0].startswith('https://test-api.uber.com/v1/eats/stores/' + STORE_ID + '/pos_data?'))
            self.assertIn('is_order_manager=false', activation.args[0])
            self.assertEqual(activation.args[1], 'POST')
            self.assertNotIn(b'private-token', response.data)
            self.assertNotIn(b'unit-secret', response.data)
            self.assertEqual(self.callback('replayed').status_code, 400)
            self.assertEqual(network.call_count, 3)

    def test_check_only_reads_integration_and_does_not_claim_enabled_when_false(self):
        with patch('clean_caisse.uber_sandbox_link.call_uber', side_effect=[{'access_token':'private-token'}, {'store_id':STORE_ID,'integration_enabled':False}]) as network:
            response = self.client.post('/administration/uber-sandbox/check', data={'csrf':'unit-csrf'})
            self.assertEqual(response.status_code, 200)
            self.assertIn('désactivée', response.text)
            self.assertEqual(network.call_args_list[-1].args[0], 'https://test-api.uber.com/v1/eats/stores/' + STORE_ID + '/pos_data')
            self.assertNotIn('private-token', response.text)

    def test_provider_error_is_not_echoed_with_credentials(self):
        with patch('clean_caisse.uber_sandbox_link.call_uber', side_effect=UberFailure('Uber a répondu HTTP 403.')):
            response = self.client.post('/administration/uber-sandbox/check', data={'csrf':'unit-csrf'})
            self.assertEqual(response.status_code, 502)
            self.assertNotIn('unit-secret', response.text)


if __name__ == '__main__':
    unittest.main()
