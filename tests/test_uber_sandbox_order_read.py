import copy
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask

from clean_caisse.uber_sandbox_link import STORE_ID, UberFailure
from clean_caisse.uber_webhook_phase6 import register_uber_webhook_phase6


ORDER_ID = 'd65e5495-7aeb-4e2e-abe6-92b2e7a1e6fe'
MODULE = 'clean_caisse.uber_sandbox_order_read'


class OrderReadTests(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.conn = self.db.return_value.__enter__.return_value
        self.cursor = self.conn.cursor.return_value.__enter__.return_value
        self.cursor.fetchone.side_effect = [{'inbox_exists': True}, {'event_key': 'signed-event'}]
        app = Flask(__name__)
        app.secret_key = 'test-only'
        register_uber_webhook_phase6(app, self.db)
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session['caisse_auth'] = True
        self.url = '/api/uber/sandbox/order-details?order_id=' + ORDER_ID
        self.token = patch(MODULE + '.get_token', return_value='test-token').start()
        self.api = patch(MODULE + '.call_uber').start()
        self.addCleanup(patch.stopall)
        # Shape from Uber Get Order Details V2, including a removed modifier.
        self.order = {
            'id': ORDER_ID, 'store': {'id': STORE_ID}, 'current_state': 'CANCELED',
            'eater': {'first_name': 'Private', 'phone': 'secret-phone'},
            'cart': {'items': [{
                'id': 'product-test', 'title': 'Tender Chicken Maison', 'quantity': 1,
                'price': {'total_price': {'amount': 2400, 'currency_code': 'EUR'}},
                'selected_modifier_groups': [{
                    'selected_items': [{'id': 'size', 'title': '10 pièces', 'quantity': 1,
                        'selected_modifier_groups': [{'selected_items': [
                            {'id': 'cheese', 'title': 'Cœur cheddar', 'quantity': 1}]}]}],
                    'removed_items': [{'id': 'sauce', 'title': 'Sauce', 'quantity': 0}],
                }],
            }]},
            'payment': {'charges': {'total': {'amount': 2400, 'currency_code': 'EUR'}}},
        }
        self.api.return_value = copy.deepcopy(self.order)

    def test_read_canceled_order_does_not_accept_import_or_print(self):
        response = self.client.get(self.url + '&store_id=other&resource_href=https://example.com')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['read_only'])
        self.assertFalse(response.json['order_processing_enabled'])
        self.assertEqual(response.json['order']['current_state'], 'CANCELED')
        item = response.json['order']['items'][0]
        self.assertEqual(item['options'][0]['title'], '10 pièces')
        self.assertEqual(item['options'][0]['options'][0]['title'], 'Cœur cheddar')
        self.assertTrue(item['options'][1]['removed'])
        self.assertEqual(response.json['order']['customer']['phone'], 'secret-phone')
        self.assertNotIn('eater', response.json['order'])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.token.assert_called_once_with('client_credentials', scope='eats.store.orders.read')
        self.api.assert_called_once_with('https://test-api.uber.com/v2/eats/order/' + ORDER_ID,
            method='GET', token='test-token', response_limit=4 * 1024 * 1024)
        sql, params = self.cursor.execute.call_args.args
        self.assertIn("event_type = 'orders.notification'", sql)
        self.assertEqual(params, (ORDER_ID, STORE_ID))
        self.assertTrue(all(c.args[0].startswith('SELECT') for c in self.cursor.execute.call_args_list))
        self.conn.commit.assert_not_called()

    def test_auth_and_uuid_validation_precede_database_and_uber(self):
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.db.assert_not_called()
        with self.client.session_transaction() as session:
            session['caisse_auth'] = True
        for value in ('', '../orders', ORDER_ID.upper(), 'https://api.uber.com'):
            self.assertEqual(self.client.get('/api/uber/sandbox/order-details',
                query_string={'order_id': value}).status_code, 400)
        self.db.assert_not_called()
        self.token.assert_not_called()

    def test_no_table_or_notification_prevents_api_call(self):
        for rows in ([(False,)], [{'inbox_exists': True}, None]):
            self.cursor.fetchone.side_effect = rows
            self.assertEqual(self.client.get(self.url).status_code, 404)
        self.token.assert_not_called()
        self.api.assert_not_called()

    def test_database_failure_does_not_disclose_details_or_request_order(self):
        self.cursor.execute.side_effect = RuntimeError('secret-db-connection')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('secret-db-connection', response.text)
        self.api.assert_not_called()

    def test_other_store_or_order_and_malformed_cart_are_rejected(self):
        for field in ('store', 'id', 'cart'):
            with self.subTest(field=field):
                self.cursor.fetchone.side_effect = [(True,), ('signed-event',)]
                data = copy.deepcopy(self.order)
                data[field] = {'id': 'other-store'} if field == 'store' else 'wrong'
                self.api.return_value = data
                self.assertEqual(self.client.get(self.url).status_code, 502)

    def test_api_permission_error_is_reported_without_acceptance_fallback(self):
        self.api.side_effect = UberFailure('Uber a répondu HTTP 403.')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 502)
        self.assertIn('HTTP 403', response.json['message'])
        self.assertEqual(self.api.call_count, 1)
        self.assertFalse(response.json['order_processing_enabled'])


if __name__ == '__main__':
    unittest.main()

