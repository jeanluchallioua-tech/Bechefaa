import json
import os
import sys
import unittest
from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from clean_caisse.deliveroo_prep_stages_phase6 import STAGES, next_stage, stage_request, register_deliveroo_prep_stages_phase6


class PrepStagesTests(unittest.TestCase):
    def setUp(self):
        self.routes = {}
        self.app = SimpleNamespace(logger=Mock())
        def register(path):
            def wrapper(f): self.routes[path] = f; return f
            return wrapper
        self.app.get = self.app.post = register
        self.body = {}
        self.request = SimpleNamespace(headers={'X-Diagnostic-Pin': 'test-pin'}, get_json=lambda **kw: self.body)
        self.order_id = 'fr:prep-test'
        self.completed = []
        self.status = 'À préparer'
        self.log = [{'status': 'accepted'}]
        self.sync = {'order_id': self.order_id, 'sync_status': 'succeeded', 'sync_http_status': 200}
        self.rows = []
        self.calls = []
        self.current_status = 'accepted'
        def execute(sql, params=None):
            self.calls.append((sql, params))
            if 'FROM deliveroo_webhook_diag' in sql: self.rows = [self.sync]
            elif 'SELECT payload,received_at' in sql:
                self.rows = [{'received_at': datetime.now(timezone.utc), 'payload': {'event': 'order.status_update', 'body': {'order': {'id': self.order_id, 'display_id': 'test', 'status': self.current_status, 'status_log': self.log}}}}]
            elif 'SELECT num,status FROM caisse_orders' in sql: self.rows = [{'num': 52, 'status': self.status}]
            elif 'SELECT status FROM caisse_orders' in sql: self.rows = [{'status': self.status}]
            elif 'to_regclass' in sql: self.rows = [{'table_name': 'deliveroo_prep_stage_trace'}]
            elif 'SELECT stage FROM' in sql: self.rows = [{'stage': s} for s in self.completed]
            elif 'INSERT INTO deliveroo_prep_stage_trace' in sql: self.completed.append(params[1])
            elif 'UPDATE caisse_orders' in sql: self.status = params[0]
        self.cur = SimpleNamespace(execute=execute, fetchone=lambda: self.rows[0] if self.rows else None, fetchall=lambda: self.rows)
        self.conn = SimpleNamespace(cursor=lambda: nullcontext(self.cur), transaction=lambda: nullcontext())
        self.db = Mock(side_effect=lambda: nullcontext(self.conn))
        fake_flask = SimpleNamespace(jsonify=lambda data: data, request=self.request, Response=lambda **kw: kw)
        with patch.dict(sys.modules, {'flask': fake_flask}): register_deliveroo_prep_stages_phase6(self.app, self.db)
        self.env = patch.dict(os.environ, {'CC_APP_ID': 'app_fad0809f-954d-47e7-983d-afb7c3867cd0',
            'BECHEFAA_DELIVEROO_ORDER_BRIDGE_ENABLED': '1', 'BECHEFAA_CAISSE_PIN': 'test-pin',
            'BECHEFAA_DELIVEROO_API_URL': 'https://api-sandbox.developers.deliveroo.com',
            'BECHEFAA_DELIVEROO_AUTH_URL': 'https://auth-sandbox.developers.deliveroo.com'})
        self.env.start(); self.addCleanup(self.env.stop)
        self.auth = patch.dict(sys.modules, {'clean_caisse.deliveroo_menu_upload_phase6': SimpleNamespace(_oauth_token=lambda: 'fake-token')})
        self.auth.start(); self.addCleanup(self.auth.stop)
        self.network = patch('urllib.request.urlopen', return_value=nullcontext(SimpleNamespace(status=200, read=lambda: b'{}')))
        self.urlopen = self.network.start(); self.addCleanup(self.network.stop)

    def send(self, stage):
        self.body = {'order_id': self.order_id, 'stage': stage}
        return self.routes['/api/deliveroo/prep-stage-phase6']()

    def test_four_stages_in_order_update_only_preparation(self):
        for i, stage in enumerate(STAGES):
            result = self.send(stage)
            self.assertTrue(result['ok'])
            self.assertEqual(self.completed, list(STAGES[:i+1]))
            self.assertEqual(result['http_status'], 200)
        self.assertEqual(self.status, 'Terminée')
        self.assertEqual(self.urlopen.call_count, 4)
        self.assertFalse(any('payment' in sql.lower() for sql, _ in self.calls))

    def test_skipping_stage_never_sends(self):
        self.assertEqual(self.send('ready_for_collection')[1], 409)
        self.urlopen.assert_not_called()

    def test_duplicate_click_does_not_send_twice(self):
        self.send('in_kitchen')
        self.assertTrue(self.send('in_kitchen')['already_sent'])
        self.assertEqual(self.urlopen.call_count, 1)

    def test_api_error_does_not_advance(self):
        self.urlopen.side_effect = HTTPError('sandbox', 400, 'bad request', {}, None)
        self.assertEqual(self.send('in_kitchen')[1], 502)
        self.assertEqual(self.completed, [])
        self.assertEqual(self.status, 'À préparer')

    def test_no_sync_success_or_no_accepted_log_never_sends(self):
        self.sync['sync_http_status'] = 429
        self.assertEqual(self.send('in_kitchen')[1], 409)
        self.sync['sync_http_status'] = 200
        self.log = []
        self.assertEqual(self.send('in_kitchen')[1], 409)
        self.urlopen.assert_not_called()

    def test_cancelled_or_changed_order_never_sends(self):
        self.current_status = 'cancelled'
        self.assertEqual(self.send('in_kitchen')[1], 409)
        self.current_status = 'accepted'
        self.sync = {**self.sync, 'order_id': 'fr:other'}
        self.assertEqual(self.send('in_kitchen')[1], 409)
        self.urlopen.assert_not_called()

    def test_production_wrong_pin_and_wrong_hosts_never_touch_db(self):
        for settings in ({'CC_APP_ID': 'production'}, {'BECHEFAA_CAISSE_PIN': 'different'},
                         {'BECHEFAA_DELIVEROO_API_URL': 'https://api.developers.deliveroo.com'},
                         {'BECHEFAA_DELIVEROO_AUTH_URL': 'https://auth.developers.deliveroo.com'}):
            with patch.dict(os.environ, settings): self.assertEqual(self.send('in_kitchen')[1], 403)
        self.db.assert_not_called(); self.urlopen.assert_not_called()

    def test_request_uses_current_utc_and_sandbox(self):
        req = stage_request(self.order_id, 'in_kitchen', 'fake')
        body = json.loads(req.data)
        at = datetime.fromisoformat(body['occurred_at'].replace('Z', '+00:00'))
        self.assertLess(abs((datetime.now(timezone.utc)-at).total_seconds()), 2)
        self.assertEqual(body['stage'], 'in_kitchen')
        self.assertIn('api-sandbox.developers.deliveroo.com', req.full_url)
        self.assertTrue(req.full_url.endswith('/prep_stage'))

    def test_sequence_integrity(self):
        self.assertIsNone(next_stage(STAGES))
        with self.assertRaises(ValueError): next_stage(['collected'])


if __name__ == '__main__': unittest.main()
