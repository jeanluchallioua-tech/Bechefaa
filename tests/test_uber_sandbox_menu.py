import copy
import unittest
from unittest.mock import patch
from flask import Flask
from clean_caisse.uber_sandbox_link import register_uber_sandbox_link, STORE_ID, API, UberFailure
from clean_caisse.uber_sandbox_menu import build_menu, verified_menu, menu_differences, photo_report, photo_summary, PREPROD_ORIGIN, MENU_API


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
        self.app.config['SERVER_NAME'] = PREPROD_ORIGIN.split('//')[1]
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
        self.assertTrue(rows[0]['photo'].startswith(PREPROD_ORIGIN + '/api/public/catalog/photo-marketplace/uber/bacon?v='))
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

    def test_uber_omitted_item_reference_types_are_equivalent_but_changes_are_rejected(self):
        expected = build_menu(self.data, 15)[0]
        actual = copy.deepcopy(expected)
        for category in actual['categories']:
            for entry in category['entities']: entry.pop('type')
        for group in actual['modifier_groups']:
            for entry in group['modifier_options']: entry.pop('type')
        self.assertEqual(menu_differences(expected, actual), [])
        wrong = copy.deepcopy(actual)
        wrong['categories'][0]['entities'][0]['type'] = 'MODIFIER_GROUP'
        self.assertFalse(verified_menu(expected, wrong))
        wrong = copy.deepcopy(actual)
        wrong['modifier_groups'][0]['modifier_options'][0]['id'] = 'different-choice'
        self.assertFalse(verified_menu(expected, wrong))
        wrong = copy.deepcopy(actual)
        wrong['categories'][0]['entities'].append(copy.deepcopy(wrong['categories'][0]['entities'][0]))
        self.assertFalse(verified_menu(expected, wrong))
        wrong = copy.deepcopy(actual)
        wrong['items'][0]['price_info']['price'] += 1
        self.assertFalse(verified_menu(expected, wrong))

    def test_diagnostic_identifies_real_price_and_constraint_differences(self):
        payload = build_menu(self.data, 15)[0]
        actual = copy.deepcopy(payload)
        actual['items'][-1]['price_info']['price'] = 0
        actual['modifier_groups'][0]['quantity_info']['quantity']['max_permitted'] = 2
        actual['access_token'] = 'must-never-display'
        report = '\n'.join(menu_differences(payload, actual))
        self.assertIn('Bacon Burger — prix en centimes', report)
        self.assertIn('2013', report)
        self.assertIn('Cuisson — max_permitted', report)
        self.assertNotIn('must-never-display', report)
        with patch('clean_caisse.uber_sandbox_menu.get_token', return_value='token'), patch('clean_caisse.uber_sandbox_menu.call_uber', return_value=actual) as network:
            response = self.client.post('/administration/uber-sandbox/menu/verify', data={'csrf':'csrf'})
            self.assertIn('Différences relevées', response.text)
            self.assertIn('prix en centimes', response.text)
            self.assertNotIn('must-never-display', response.text)
            self.assertEqual(network.call_args.args, (MENU_API,))
            self.assertNotIn('body', network.call_args.kwargs)

    def test_photo_version_changes_only_when_photo_changes(self):
        original, _ = build_menu(self.data, 15)
        renamed = copy.deepcopy(self.data)
        renamed['products'][0]['name'] = 'Nouveau nom'
        self.assertEqual(original['items'][-1]['image_url'], build_menu(renamed, 15)[0]['items'][-1]['image_url'])
        updated = copy.deepcopy(self.data)
        updated['products'][0]['photo'] = 'data:image/jpeg;base64,NEWPHOTO'
        changed, _ = build_menu(updated, 15)
        self.assertNotEqual(original['items'][-1]['image_url'], changed['items'][-1]['image_url'])
        original['items'][-1].pop('image_url'); changed['items'][-1].pop('image_url')
        self.assertEqual(original, changed)

    def test_photo_report_never_confuses_cdn_url_with_visual_confirmation(self):
        expected = build_menu(self.data, 15)[0]
        actual = copy.deepcopy(expected)
        self.assertEqual(photo_report(expected, actual)[0]['state'], 'same_source')
        actual['items'][-1]['image_url'] = 'https://images.uber.com/processed-or-old.jpg'
        report = photo_report(expected, actual)
        self.assertEqual(report[0]['state'], 'different_url')
        self.assertIn('1 avec une adresse différente', photo_summary(report))
        actual['items'][-1].pop('image_url')
        self.assertEqual(photo_report(expected, actual)[0]['state'], 'missing')
        actual['items'][-1]['image_url'] = 'javascript:alert(1)'
        self.assertIsNone(photo_report(expected, actual)[0]['uber_url'])

    def test_readonly_verification_shows_both_photos_and_a_separate_result(self):
        payload = build_menu(self.data, 15)[0]
        payload['items'][-1]['image_url'] = 'https://images.uber.com/older.jpg'
        with patch('clean_caisse.uber_sandbox_menu.get_token', return_value='token'), patch('clean_caisse.uber_sandbox_menu.call_uber', return_value=payload) as network:
            result = self.client.post('/administration/uber-sandbox/menu/verify', data={'csrf':'csrf'})
            self.assertEqual(result.status_code, 200)
            self.assertIn('Articles, prix et options confirmés', result.text)
            self.assertIn('Photo BÉCHÉFAA à envoyer', result.text)
            self.assertIn('Photo lue chez Uber — à comparer', result.text)
            self.assertIn('https://images.uber.com/older.jpg', result.text)
            self.assertIn(PREPROD_ORIGIN + '/api/public/catalog/photo-marketplace/uber/', result.text)
            self.assertNotIn('Carte confirmée chez Uber', result.text)
            self.assertEqual(network.call_args.args, (MENU_API,))
            self.assertNotIn('body', network.call_args.kwargs)

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

    def test_preview_for_previous_store_cannot_upload_to_replacement(self):
        form = self.preview()
        with self.client.session_transaction() as session:
            pending = session['uber_menu_preview']
            pending['store_id'] = '874dc6f0-80a8-4a22-a66a-28b693e59522'
            session['uber_menu_preview'] = pending
        with patch('clean_caisse.uber_sandbox_menu.call_uber') as network, patch('clean_caisse.uber_sandbox_menu.get_token') as token:
            self.assertEqual(self.client.post('/administration/uber-sandbox/menu/upload', data=form).status_code, 409)
            network.assert_not_called()
            token.assert_not_called()

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
            self.assertIn('Articles, prix et options confirmés', response.text)
            self.assertEqual(network.call_args.args, (MENU_API,))
            self.assertNotIn('body', network.call_args.kwargs)


if __name__ == '__main__': unittest.main()

