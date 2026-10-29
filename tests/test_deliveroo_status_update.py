import json
import os
import sys
import unittest
from contextlib import nullcontext
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from clean_caisse.deliveroo_status_update_phase6 import accept_request, status_request, validate_accept_candidate, register_deliveroo_status_update_phase6


def payload(status='placed'):
    return {'event': 'order.new', 'body': {'order': {'id': 'fr:accept-test', 'location_id': '101',
        'status': status, 'asap': True, 'display_id': '1234', 'total_price': {'currency_code': 'EUR', 'fractional': 1200},
        'items': [{'pos_item_id': 'MU11001', 'name': 'Chicken Burger', 'quantity': 1,
                   'total_price': {'currency_code': 'EUR', 'fractional': 1200}}]}}}


class StatusUpdateTests(unittest.TestCase):
    def setUp(self):
        self.routes = {}
        def register(path):
            def decorator(f): self.routes[path] = f; return f
            return decorator
        self.app = SimpleNamespace(get=register, post=register, logger=Mock())
        self.body = {'order_id': 'fr:accept-test'}
        self.request = SimpleNamespace(headers={'X-Diagnostic-Pin': 'test-pin'}, get_json=lambda **kw: self.body)
        self.payload = payload()
        self.recorded = False
        self.row = None
        self.calls = []
        def execute(sql, params=None):
            self.calls.append((sql, params))
            if 'SELECT action,http_status FROM' in sql: self.row = {'http_status': 204, 'action': self.recorded} if self.recorded else None
            elif 'SELECT order_id,payload,received_at' in sql:
                self.row = {'order_id': 'fr:accept-test', 'payload': self.payload, 'received_at': datetime.now(timezone.utc)}
            elif 'INSERT INTO deliveroo_status_action_trace' in sql: self.recorded = params[1]
        cur = SimpleNamespace(execute=execute, fetchone=lambda: self.row, fetchall=lambda: [self.row] if self.row else [])
        conn = SimpleNamespace(cursor=lambda: nullcontext(cur), transaction=lambda: nullcontext())
        self.db = Mock(side_effect=lambda: nullcontext(conn))
        with patch.dict(sys.modules, {'flask': SimpleNamespace(jsonify=lambda d: d, request=self.request, Response=Mock())}):
            register_deliveroo_status_update_phase6(self.app, self.db)
        self.env = patch.dict(os.environ, {'CC_APP_ID': 'app_fad0809f-954d-47e7-983d-afb7c3867cd0',
            'BECHEFAA_DELIVEROO_ORDER_BRIDGE_ENABLED': '1', 'BECHEFAA_CAISSE_PIN': 'test-pin',
            'BECHEFAA_DELIVEROO_API_URL': 'https://api-sandbox.developers.deliveroo.com',
            'BECHEFAA_DELIVEROO_AUTH_URL': 'https://auth-sandbox.developers.deliveroo.com'})
        self.env.start(); self.addCleanup(self.env.stop)
        auth = patch.dict(sys.modules, {'clean_caisse.deliveroo_menu_upload_phase6': SimpleNamespace(_oauth_token=lambda: 'fake')})
        auth.start(); self.addCleanup(auth.stop)
        network = patch('urllib.request.urlopen', return_value=nullcontext(SimpleNamespace(status=204, read=lambda: b'')))
        self.urlopen = network.start(); self.addCleanup(network.stop)

    def send(self): return self.routes['/api/deliveroo/accept-asap-phase6']()

    def reject(self): return self.routes['/api/deliveroo/reject-asap-phase6']()

    def test_reject_requires_valid_explicit_reason(self):
        for reason in (None, '', 'unknown', [], {}):
            self.body['reject_reason'] = reason
            self.assertEqual(self.reject()[1], 400)
        self.db.assert_not_called()
        self.urlopen.assert_not_called()

    def test_reject_204_payload_and_no_pos_or_payment_writes(self):
        self.body['reject_reason'] = 'other'
        result = self.reject()
        self.assertTrue(result['ok'])
        self.assertEqual(result['status'], 'rejected')
        req = self.urlopen.call_args.args[0]
        data = json.loads(req.data)
        self.assertEqual(req.method, 'PATCH')
        self.assertEqual(data['status'], 'rejected')
        self.assertEqual(data['reject_reason'], 'other')
        self.assertIn('sandbox', data['notes'])
        self.assertFalse(any('caisse_orders' in sql or 'payment' in sql for sql, _ in self.calls))
        self.assertTrue(self.reject()['already_sent'])
        self.assertEqual(self.urlopen.call_count, 1)
        self.assertEqual(self.send()[1], 409)

    def test_accept_prevents_later_reject_even_before_webhook(self):
        self.send()
        self.body['reject_reason'] = 'other'
        self.assertEqual(self.reject()[1], 409)
        self.assertEqual(self.urlopen.call_count, 1)

    def test_reject_accepted_order_is_blocked(self):
        self.payload = payload('accepted')
        self.body['reject_reason'] = 'other'
        self.assertEqual(self.reject()[1], 409)
        self.urlopen.assert_not_called()

    def test_reject_wrong_pin_or_production_is_blocked(self):
        self.body['reject_reason'] = 'other'
        for settings in ({'CC_APP_ID': 'production'}, {'BECHEFAA_CAISSE_PIN': 'wrong'}):
            with patch.dict(os.environ, settings): self.assertEqual(self.reject()[1], 403)
        self.db.assert_not_called()
        self.urlopen.assert_not_called()

    def test_placed_order_load_is_read_only(self):
        result = self.routes['/api/deliveroo/status-update-state-phase6']()
        self.assertTrue(result['ok'])
        self.assertEqual(result['status'], 'placed')
        self.urlopen.assert_not_called()
        self.assertFalse(any('INSERT' in sql or 'UPDATE' in sql for sql, _ in self.calls))

    def test_accept_uses_patch_and_204_without_payment_or_prep_writes(self):
        result = self.send()
        self.assertTrue(result['ok'])
        self.assertEqual(result['http_status'], 204)
        self.assertEqual(result['status'], 'accepted')
        req = self.urlopen.call_args.args[0]
        self.assertEqual(req.method, 'PATCH')
        self.assertEqual(json.loads(req.data), {'status': 'accepted'})
        self.assertTrue(req.full_url.endswith('/order/v1/orders/fr:accept-test'))
        self.assertEqual(req.get_header('User-agent'), 'Bechefaa-Deliveroo-Integration/1.0')
        self.assertFalse(any('UPDATE caisse_orders' in sql or 'payment' in sql for sql, _ in self.calls))

    def test_double_click_never_sends_twice(self):
        self.send()
        self.assertTrue(self.send()['already_sent'])
        self.assertEqual(self.urlopen.call_count, 1)

    def test_terminal_or_already_accepted_never_sends(self):
        for status in ('accepted', 'canceled', 'cancelled', 'rejected'):
            self.payload['body']['order']['status'] = status
            self.assertEqual(self.send()[1], 409)
        self.urlopen.assert_not_called()

    def test_wrong_site_scheduled_bad_plu_or_inconsistent_price_never_sent(self):
        cases = ({'location_id': '102'}, {'asap': False}, {'total_price': {'fractional': 99}})
        for changes in cases:
            self.payload = payload(); self.payload['body']['order'].update(changes)
            self.assertEqual(self.send()[1], 409)
        self.payload = payload(); self.payload['body']['order']['items'][0]['pos_item_id'] = 'MU11002'
        self.assertEqual(self.send()[1], 409)
        self.urlopen.assert_not_called()

    def test_wrong_pin_production_or_production_hosts_never_touch_db(self):
        for settings in ({'CC_APP_ID': 'production'}, {'BECHEFAA_CAISSE_PIN': 'different'},
                         {'BECHEFAA_DELIVEROO_API_URL': 'https://api.developers.deliveroo.com'},
                         {'BECHEFAA_DELIVEROO_AUTH_URL': 'https://auth.developers.deliveroo.com'}):
            with patch.dict(os.environ, settings): self.assertEqual(self.send()[1], 403)
        self.db.assert_not_called(); self.urlopen.assert_not_called()

    def test_503_exposes_retry_after_without_automatic_retry(self):
        self.urlopen.side_effect = HTTPError('sandbox', 503, 'Not ready', {'Retry-After': '5'}, BytesIO(b'{"message":"Order not ready"}'))
        result, code = self.send()
        self.assertEqual(code, 502)
        self.assertEqual(result['http_status'], 503)
        self.assertEqual(result['retry_after_seconds'], 5)
        self.assertFalse(self.recorded)
        self.assertEqual(self.urlopen.call_count, 1)

    def test_unexpected_success_code_not_treated_as_acceptance(self):
        self.urlopen.return_value = nullcontext(SimpleNamespace(status=200, read=lambda: b'{}'))
        self.assertEqual(self.send()[1], 409)
        self.assertFalse(self.recorded)


if __name__ == '__main__': unittest.main()
