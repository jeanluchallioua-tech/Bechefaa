import ast
import hashlib
import hmac
import json
import os
import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from clean_caisse.deliveroo_order_status_phase6 import cancellation_ready, should_sync_order


def event(status='canceled', log=None):
    return {'event': 'order.status_update', 'body': {'order': {
        'id': 'fr:cancel-test', 'status': status,
        'status_log': log if log is not None else [
            {'status': 'placed'}, {'status': 'accepted'}, {'status': status}],
    }}}


class CancellationTests(unittest.TestCase):
    def test_both_spellings_without_prior_acceptance(self):
        for status in ('canceled', 'cancelled'):
            payload = event(status, [{'status': status}])
            self.assertTrue(cancellation_ready(payload))
            self.assertTrue(should_sync_order(payload, 'fr:test', False))

    def test_old_acceptance_does_not_ack_missing_cancel_log(self):
        payload = event(log=[{'status': 'accepted'}])
        self.assertFalse(cancellation_ready(payload))
        self.assertFalse(should_sync_order(payload, 'fr:test', True))

    def test_old_cancellation_does_not_override_current_status(self):
        self.assertFalse(cancellation_ready(event('accepted', [{'status': 'canceled'}])))

    def test_existing_accepted_and_rejected_sync_preserved(self):
        for status in ('accepted', 'rejected'):
            self.assertTrue(should_sync_order(event(status), 'fr:test', True))
            self.assertFalse(should_sync_order(event(status), 'fr:test', False))

    def test_missing_order_id_or_wrong_event_never_sync(self):
        self.assertFalse(should_sync_order(event(), '', True))
        payload = event()
        payload['event'] = 'order.new'
        self.assertFalse(cancellation_ready(payload))
        self.assertFalse(should_sync_order(payload, 'fr:test', True))

    def test_latest_log_fallback(self):
        payload = event()
        del payload['body']['order']['status']
        self.assertTrue(cancellation_ready(payload))
        payload['body']['order']['status_log'].append({'status': 'confirmed'})
        self.assertFalse(cancellation_ready(payload))


class CancellationBridgeTests(unittest.TestCase):
    def setUp(self):
        # Execute the actual nested bridge without registering routes or touching a DB.
        source = Path('clean_caisse/deliveroo_sandbox_phase6.py').read_text()
        tree = ast.parse(source)
        register = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'register_deliveroo_sandbox_phase6')
        function = next(n for n in register.body if isinstance(n, ast.FunctionDef) and n.name == '_bridge_order_cancelled')
        self.conn = Mock()
        self.conn.transaction.return_value = nullcontext()
        self.conn.execute.return_value.fetchone.return_value = {'id': 'test', 'status': 'À préparer'}
        self.db = Mock(side_effect=lambda: nullcontext(self.conn))
        namespace = {'os': os, 'db': self.db, 'cancellation_ready': cancellation_ready,
                     '_extract_order_id': lambda p: p['body']['order']['id']}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<bridge>', 'exec'), namespace)
        self.bridge = namespace['_bridge_order_cancelled']
        self.env = patch.dict(os.environ, {'CC_APP_ID': 'app_fad0809f-954d-47e7-983d-afb7c3867cd0',
                                         'BECHEFAA_DELIVEROO_ORDER_BRIDGE_ENABLED': '1'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.app_patch = patch.dict(sys.modules, {'clean_caisse.app': SimpleNamespace(ensure_order_schema=Mock())})
        self.app_patch.start()
        self.addCleanup(self.app_patch.stop)

    def test_production_and_disabled_never_write(self):
        for settings in ({'CC_APP_ID': 'production'}, {'BECHEFAA_DELIVEROO_ORDER_BRIDGE_ENABLED': '0'}):
            with patch.dict(os.environ, settings):
                self.bridge(event())
        self.db.assert_not_called()

    def test_cancel_only_matching_deliveroo_order(self):
        self.assertEqual(self.bridge(event()), 'cancelled')
        sql, params = self.conn.execute.call_args.args
        self.assertIn("sales_channel='DELIVEROO'", sql)
        self.assertEqual(params[0], 'Annulée')
        self.assertTrue(params[2].startswith('deliveroo-'))

    def test_terminal_orders_preserved(self):
        for status in ('Annulée', 'Terminée', 'Rejetée'):
            self.conn.reset_mock()
            self.conn.execute.return_value.fetchone.return_value = {'status': status}
            self.assertEqual(self.bridge(event()), 'already_terminal')
            self.assertEqual(self.conn.execute.call_count, 1)

    def test_rejection_is_not_processed_as_cancellation(self):
        self.assertEqual(self.bridge(event('rejected')), 'not_cancelled')
        self.db.assert_not_called()

    def test_missing_import_and_database_failure_not_acknowledged(self):
        self.conn.execute.return_value.fetchone.return_value = None
        self.assertEqual(self.bridge(event()), 'not_imported')
        self.conn.execute.side_effect = RuntimeError('db failure')
        with self.assertRaises(RuntimeError):
            self.bridge(event())


class WebhookOrderingTests(unittest.TestCase):
    def run_webhook(self, bridge_result='cancelled', bridge_error=None, payload=None):
        payload = payload or event()
        raw = json.dumps(payload).encode()
        signature = hmac.new(b'test-secret', b'test-guid ' + raw, hashlib.sha256).hexdigest()
        request = SimpleNamespace(
            headers={'X-Deliveroo-Sequence-Guid': 'test-guid', 'X-Deliveroo-Hmac-Sha256': signature},
            get_data=lambda **kw: raw, get_json=lambda **kw: payload)
        calls = []
        def bridge(p):
            calls.append('cancel')
            if bridge_error:
                raise bridge_error
            return bridge_result
        def sync(order_id):
            calls.append('sync')
            return 200, ''
        conn = Mock()
        conn.cursor.return_value = nullcontext(Mock())
        namespace = dict(os=os, json=json, hmac=hmac, hashlib=hashlib, request=request,
                         Response=lambda **kw: kw['status'], app=SimpleNamespace(logger=Mock()),
                         _persist_diag=Mock(), _persist_order_event=Mock(),
                         _extract_order_id=lambda p: 'fr:test', _accepted_in_status_log=lambda p: True,
                         _bridge_order_cancelled=bridge, _send_sync_status=sync,
                         _bridge_order_rejected=Mock(), _last_webhooks={},
                         db=lambda: nullcontext(conn), cancellation_ready=cancellation_ready,
                         should_sync_order=should_sync_order)
        tree = ast.parse(Path('clean_caisse/deliveroo_sandbox_phase6.py').read_text())
        register = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'register_deliveroo_sandbox_phase6')
        function = next(n for n in register.body if isinstance(n, ast.FunctionDef) and n.name == '_capture_webhook')
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<webhook>', 'exec'), namespace)
        with patch.dict(os.environ, {'BECHEFAA_DELIVEROO_WEBHOOK_SECRET': 'test-secret'}):
            status = namespace['_capture_webhook']('orders')
        return status, calls

    def test_cancel_commits_before_sync(self):
        self.assertEqual(self.run_webhook(), (200, ['cancel', 'sync']))

    def test_missing_import_retries_without_sync(self):
        self.assertEqual(self.run_webhook(bridge_result='not_imported'), (503, ['cancel']))

    def test_database_failure_retries_without_sync(self):
        self.assertEqual(self.run_webhook(bridge_error=RuntimeError('db')), (500, ['cancel']))

    def test_accepted_history_cannot_ack_cancel_before_log(self):
        self.assertEqual(self.run_webhook(payload=event(log=[{'status': 'accepted'}])), (200, []))


if __name__ == '__main__':
    unittest.main()
