import unittest
from unittest.mock import patch
from flask import Flask
from clean_caisse.uber_sandbox_link import register_uber_sandbox_link, STORE_ID, API, UberFailure


class UberStoreDiagnosticTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.secret_key = 'unit-only'
        register_uber_sandbox_link(app)
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session['caisse_auth'] = True
        self.details = {'store_id':STORE_ID, 'name':'BECHEFAA Test Store', 'status':'active', 'timezone':'Europe/Paris',
            'web_url':'https://www.ubereats.com/test-store',
            'location':{'address':'1 Rue Emile Zola','city':'Fontenay-sous-Bois','country':'FR'},
            'contact_emails':['not-to-expose@example.com'], 'private_token':'never-display'}

    def test_no_session_no_network(self):
        with self.client.session_transaction() as session: session.clear()
        with patch('clean_caisse.uber_sandbox_link.get_token') as token, patch('clean_caisse.uber_sandbox_link.call_uber') as network:
            self.assertEqual(self.client.get('/api/uber/sandbox/store-diagnostic').status_code, 403)
            token.assert_not_called(); network.assert_not_called()

    def test_metadata_and_offline_reason_use_only_readonly_fixed_sandbox_endpoints(self):
        with patch('clean_caisse.uber_sandbox_link.get_token', return_value='secret-token'), patch('clean_caisse.uber_sandbox_link.call_uber', side_effect=[self.details, {'status':'OFFLINE','offlineReason':'INVISIBLE'}]) as network:
            response = self.client.get('/api/uber/sandbox/store-diagnostic?store_id=other')
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json['ok'])
            self.assertTrue(response.json['read_only'])
            self.assertEqual(response.json['online_status'], 'OFFLINE')
            self.assertEqual(response.json['offline_reason'], 'INVISIBLE')
            self.assertEqual(response.json['customer_url'], self.details['web_url'])
            self.assertNotIn('never-display', response.text)
            self.assertNotIn('not-to-expose@example.com', response.text)
            self.assertNotIn('secret-token', response.text)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertEqual(network.call_args_list[0].args, (API,))
            self.assertEqual(network.call_args_list[1].args, ('https://test-api.uber.com/v1/eats/store/' + STORE_ID + '/status',))
            self.assertTrue(all('body' not in c.kwargs and len(c.args) == 1 for c in network.call_args_list))

    def test_status_failure_retains_metadata_without_claiming_online(self):
        with patch('clean_caisse.uber_sandbox_link.get_token', return_value='token'), patch('clean_caisse.uber_sandbox_link.call_uber', side_effect=[self.details, UberFailure('HTTP 403')]):
            response = self.client.get('/api/uber/sandbox/store-diagnostic')
            self.assertFalse(response.json['ok'])
            self.assertIsNone(response.json['online_status'])
            self.assertIn('HTTP 403', response.json['status_error'])
            self.assertEqual(response.json['customer_url'], self.details['web_url'])

    def test_wrong_store_stops_before_second_request(self):
        with patch('clean_caisse.uber_sandbox_link.get_token', return_value='token'), patch('clean_caisse.uber_sandbox_link.call_uber', return_value={'store_id':'wrong-store'}) as network:
            response = self.client.get('/api/uber/sandbox/store-diagnostic')
            self.assertEqual(response.status_code, 502)
            self.assertFalse(response.json['ok'])
            self.assertEqual(network.call_count, 1)

    def test_authentication_failure_does_not_send_api_request(self):
        with patch('clean_caisse.uber_sandbox_link.get_token', side_effect=UberFailure('La clé Uber est absente.')), patch('clean_caisse.uber_sandbox_link.call_uber') as network:
            response = self.client.get('/api/uber/sandbox/store-diagnostic')
            self.assertEqual(response.status_code, 502)
            self.assertFalse(response.json['ok'])
            network.assert_not_called()


if __name__ == '__main__': unittest.main()
