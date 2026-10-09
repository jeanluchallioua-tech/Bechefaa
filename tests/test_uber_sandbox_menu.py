import copy
import unittest
from unittest.mock import patch
from flask import Flask
from clean_caisse.uber_sandbox_link import register_uber_sandbox_link, STORE_ID, API, UberFailure
from clean_caisse.uber_sandbox_menu import build_menu, verified_menu, MENU_API


def catalogue():
    return {'categories': [{'id': 'burger', 'name': 'Burger', 'active': True}], 'products': [
        {'id': 'bacon', 'name': 'Bacon Burger', 'category': 'Burger', 'price': 17.50,
         'photo': 'data:image/jpeg;base64,TEST', 'channels': {'ubereats': True},
         'options': [{'key': 'cooking', 'title': 'Cuisson', 'required': True, 'max': 1, 'choices': [['À point', 0], ['Bien cuit', 0]]},
                     {'key': 'extras', 'title': 'Suppléments', 'max': 0, 'choices': [['Bacon', 4], ['Œuf', 2]]}]},
        {'id': 'disabled', 'name': 'Disabled', 'category': 'Burger', 'price': 2, 'channels': {'ubereats': False}}]}


class UberMenuTests(unittest.TestCase):
    def setUp(self):
        self.data = catalogue()
        self.app = Flask(__name__)
        self.app.secret_key = 'unit-only'
        register_uber_sandbox_link(self.app)
        self.client = self.app.test_client()
        self.source = patch('clean_caisse.uber_sandbox_menu.read_source', side_effect=lambda: (copy.deepcopy(self.data), 15))
        self.source.start()
        self.addCleanup(self.source.stop)
        with self.client.session_transaction() as session:
            session['caisse_auth'] = True
            session['uber_sandbox_csrf'] = 'csrf'

    def preview(self):
        result = self.client.get('/administration/uber-sandbox/menu')
        self.assertEqual(result.status_code, 200)
        with self.client.session_transaction() as session:
            return {'csrf': 'csrf', 'nonce': session['uber_menu_preview']['nonce']}

    def test_conversion_preserves_catalogue_filters_channels_and_prices_options(self):
        before = copy.deepcopy(self.data)
        payload, rows = build_menu(self.data, 15)
        self.assertEqual(self.data, before)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['price'], 20.13)
        self.assertEqual(rows[0]['groups'][1]['choices'][0]['price'], 4.60)
        self.assertEqual(payload['modifier_groups'][0]['quantity_info']['quantity'], {'min_permitted': 1, 'max_permitted': 1})
        self.assertEqual(payload['modifier_groups'][1]['quantity_info']['quantity'], {'min_permitted': 0, 'max_permitted': 2})
        self.assertEqual(rows[0]['photo'], 'https://caisse.bechefaa.fr/api/public/catalog/photo-marketplace/uber/bacon')
        self.assertEqual(len(payload['menus'][0]['service_availability']), 7)
        self.assertEqual(payload, build_menu(self.data, 15)[0])
        self.assertEqual(len({x['id'] for x in payload['items']}), len(payload['items']))

    def test_empty_bad_prices_and_impossible_choices_fail_before_upload(self):
        for change in ('empty', 'price', 'required', 'category'):
            data = catalogue()
            if change == 'empty': data['products'] = []
            if change == 'price': data['products'][0]['price'] = 'NaN'
            if change == 'required': data['products'][0]['options'][0]['choices'] = []
            if change == 'category': data['categories'] = []
            with self.assertRaises(ValueError): build_menu(data, 15)

    def test_pin_and_csrf_protect_all_operations(self):
        with patch('clean_caisse.uber_sandbox_menu.call_uber') as network, patch('clean_caisse.uber_sandbox_menu.get_token') as token:
            for path in ('upload', 'verify'):
                self.assertEqual(self.client.post('/administration/uber-sandbox/menu/' + path).status_code, 403)
            with self.client.session_transaction() as session: session.clear()
            self.assertEqual(self.client.get('/administration/uber-sandbox/menu').status_code, 303)
            self.assertEqual(self.client.post('/administration/uber-sandbox/menu/upload', data={'csrf':'csrf'}).status_code, 403)
            network.assert_not_called(); token.assert_not_called()

    def test_preview_is_read_only_and_html_escaped(self):
        self.data['products'][0]['name'] = '<script>bad()</script>'
        with patch('clean_caisse.uber_sandbox_menu.call_uber') as network:
            response = self.client.get('/administration/uber-sandbox/menu')
            self.assertIn('&lt;script&gt;', response.text)
            self.assertNotIn('<script>bad()', response.text)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            network.assert_not_called()

    def test_upload_exact_fixed_store_only_and_no_replay_without_new_preview(self):
        form = self.preview()
        expected = build_menu(self.data, 15)[0]
        with patch('clean_caisse.uber_sandbox_menu.get_token', return_value='private-token'), patch('clean_caisse.uber_sandbox_menu.call_uber', side_effect=[{'store_id':STORE_ID, 'integration_enabled':True}, {}]) as network:
            response = self.client.post('/administration/uber-sandbox/menu/upload', data=form)
            self.assertEqual(response.status_code, 200)
            self.assertIn('accepté', response.text)
            self.assertNotIn('Carte confirmée', response.text)
            self.assertEqual(network.call_args_list[0].args, (API + '/pos_data',))
            self.assertEqual(network.call_args_list[1].args, (MENU_API, 'PUT'))
            self.assertEqual(network.call_args_list[1].kwargs['body'], expected)
            self.assertNotIn('private-token', response.text)
            self.assertEqual(self.client.post('/administration/uber-sandbox/menu/upload', data=form).status_code, 409)
            self.assertEqual(network.call_count, 2)

    def test_changed_catalogue_and_wrong_link_block_put(self):
        form = self.preview(); self.data['products'][0]['price'] = 18
        with patch('clean_caisse.uber_sandbox_menu.call_uber') as network:
            self.assertEqual(self.client.post('/administration/uber-sandbox/menu/upload', data=form).status_code, 409)
            network.assert_not_called()
        for details in ({'store_id': 'wrong', 'integration_enabled':True}, {'store_id':STORE_ID, 'integration_enabled':False}):
            form = self.preview()
            with patch('clean_caisse.uber_sandbox_menu.get_token', return_value='token'), patch('clean_caisse.uber_sandbox_menu.call_uber', return_value=details) as network:
                self.assertEqual(self.client.post('/administration/uber-sandbox/menu/upload', data=form).status_code, 409)
                self.assertEqual(network.call_count, 1)

    def test_provider_failure_is_never_reported_as_success(self):
        form = self.preview()
        with patch('clean_caisse.uber_sandbox_menu.get_token', return_value='token'), patch('clean_caisse.uber_sandbox_menu.call_uber', side_effect=[{'store_id':STORE_ID, 'integration_enabled':True}, UberFailure('HTTP 403')]):
            response = self.client.post('/administration/uber-sandbox/menu/upload', data=form)
            self.assertEqual(response.status_code, 502)
            self.assertIn('non confirmée', response.text)
            self.assertNotIn('a accepté', response.text)

    def test_readback_verification_detects_prices_options_missing_items(self):
        payload = build_menu(self.data, 15)[0]
        self.assertTrue(verified_menu(payload, copy.deepcopy(payload)))
        for changed in ('price', 'limit', 'item', 'category'):
            actual = copy.deepcopy(payload)
            if changed == 'price': actual['items'][0]['price_info']['price'] += 1
            if changed == 'limit': actual['modifier_groups'][0]['quantity_info']['quantity']['max_permitted'] = 2
            if changed == 'item': actual['items'].pop()
            if changed == 'category': actual['categories'][0]['entities'] = []
            self.assertFalse(verified_menu(payload, actual))
        with patch('clean_caisse.uber_sandbox_menu.get_token', return_value='token'), patch('clean_caisse.uber_sandbox_menu.call_uber', return_value=payload) as network:
            response = self.client.post('/administration/uber-sandbox/menu/verify', data={'csrf':'csrf'})
            self.assertEqual(response.status_code, 200)
            self.assertIn('Carte confirmée', response.text)
            self.assertEqual(network.call_args.args, (MENU_API,))
            self.assertNotIn('body', network.call_args.kwargs)


if __name__ == '__main__': unittest.main()
