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

from clean_caisse.deliveroo_order_pricing_phase6 import net_item_cents
from clean_caisse.deliveroo_order_plu_phase6 import missing_plu_paths, mismatched_sandbox_plu_paths
from clean_caisse.deliveroo_order_status_phase6 import cancellation_ready, should_sync_order, accepted_import_ready, order_status_and_log


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
    def run_webhook(self, bridge_result='cancelled', bridge_error=None, payload=None, import_error=None):
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
        def import_order(p):
            calls.append('import')
            if import_error:
                raise import_error
            return 'created'
        def sync(order_id, **kwargs):
            calls.append(('sync', kwargs) if kwargs else 'sync')
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
                         should_sync_order=should_sync_order, accepted_import_ready=accepted_import_ready, missing_plu_paths=missing_plu_paths, mismatched_sandbox_plu_paths=mismatched_sandbox_plu_paths,
                         _bridge_order_new=import_order)
        tree = ast.parse(Path('clean_caisse/deliveroo_sandbox_phase6.py').read_text())
        register = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'register_deliveroo_sandbox_phase6')
        function = next(n for n in register.body if isinstance(n, ast.FunctionDef) and n.name == '_capture_webhook')
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<webhook>', 'exec'), namespace)
        with patch.dict(os.environ, {'BECHEFAA_DELIVEROO_WEBHOOK_SECRET': 'test-secret', 'CC_APP_ID': 'app_fad0809f-954d-47e7-983d-afb7c3867cd0'}):
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

    def test_accepted_import_before_sync(self):
        self.assertEqual(self.run_webhook(payload=event('accepted')), (200, ['import', 'sync']))

    def test_missing_plu_reports_failure_without_import(self):
        payload = event('accepted')
        payload['body']['order']['items'] = [{'name': 'Burger', 'quantity': 1}]
        status, calls = self.run_webhook(payload=payload)
        self.assertEqual(status, 200)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], 'sync')
        self.assertEqual(calls[0][1]['status'], 'failed')
        self.assertEqual(calls[0][1]['reason'], 'pos_item_id_not_found')

    def test_swapped_plu_failure_after_acceptance_without_import(self):
        payload = event('accepted')
        payload['body']['order']['items'] = [
            {'name': 'Veggie Burger (V)', 'pos_item_id': 'MU11001'},
            {'name': 'Chicken Burger', 'pos_item_id': 'MU11002'},
        ]
        status, calls = self.run_webhook(payload=payload)
        self.assertEqual(status, 200)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]['reason'], 'pos_item_id_mismatched')
        self.assertEqual(calls[0][1]['status'], 'failed')
        payload['body']['order']['status'] = 'placed'
        payload['body']['order']['status_log'] = [{'status': 'placed'}]
        self.assertEqual(self.run_webhook(payload=payload), (200, []))

    def test_missing_plu_does_not_sync_before_acceptance(self):
        payload = event('placed')
        payload['body']['order']['status_log'] = [{'status': 'placed'}]
        payload['body']['order']['items'] = [{'name': 'Burger'}]
        self.assertEqual(self.run_webhook(payload=payload), (200, []))

    def test_failed_accepted_import_does_not_sync(self):
        self.assertEqual(self.run_webhook(payload=event('accepted'), import_error=ValueError('missing items')),
                         (500, ['import']))


class AcceptedBridgeTests(unittest.TestCase):
    def setUp(self):
        self.payload = event('accepted')
        self.payload['body']['order'].update(items=[{'name': 'Burger', 'pos_item_id': 'burger-1', 'quantity': 1,
            'total_price': {'fractional': 800}, 'discount_amount': {'fractional': 100}}], asap=True, total_price={'fractional': 700})
        tree = ast.parse(Path('clean_caisse/deliveroo_sandbox_phase6.py').read_text())
        register = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'register_deliveroo_sandbox_phase6')
        function = next(n for n in register.body if isinstance(n, ast.FunctionDef) and n.name == '_bridge_order_new')
        self.exists = False
        self.prior = []
        self.inserts = []
        self.item_inserts = []
        def execute(sql, params=None):
            if sql.startswith('SELECT id FROM'):
                return SimpleNamespace(fetchone=lambda: {'id': 'existing'} if self.exists else None)
            if sql.startswith('SELECT payload FROM'):
                return SimpleNamespace(fetchall=lambda: self.prior)
            if 'MAX(num)' in sql:
                return SimpleNamespace(fetchone=lambda: {'n': 48})
            if 'INSERT INTO caisse_order_items' in sql:
                self.item_inserts.append(params)
            if 'INSERT INTO caisse_orders' in sql:
                self.exists = True
                self.inserts.append(params)
            return Mock()
        self.conn = SimpleNamespace(transaction=lambda: nullcontext(), execute=execute)
        self.db = Mock(side_effect=lambda: nullcontext(self.conn))
        namespace = dict(os=os, json=json, db=self.db, order_status_and_log=order_status_and_log, net_item_cents=net_item_cents, missing_plu_paths=missing_plu_paths, mismatched_sandbox_plu_paths=mismatched_sandbox_plu_paths,
                         datetime=__import__('datetime').datetime, timezone=__import__('datetime').timezone)
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<accepted-bridge>', 'exec'), namespace)
        self.bridge = namespace['_bridge_order_new']
        for patcher in (patch.dict(os.environ, {'CC_APP_ID': 'app_fad0809f-954d-47e7-983d-afb7c3867cd0',
                            'BECHEFAA_DELIVEROO_ORDER_BRIDGE_ENABLED': '1'}),
                        patch.dict(sys.modules, {'clean_caisse.app': SimpleNamespace(ensure_order_schema=Mock())})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_complete_update_imported_once_even_if_new_arrives_later(self):
        self.assertEqual(self.bridge(self.payload), 'created')
        self.payload['event'] = 'order.new'
        self.assertEqual(self.bridge(self.payload), 'duplicate')
        self.assertEqual(len(self.inserts), 1)
        self.assertEqual(str(self.inserts[0][8]), '7')

    def test_terminal_history_prevents_import(self):
        for status in ('cancelled', 'canceled', 'rejected'):
            self.prior = [{'payload': event(status)}]
            self.assertEqual(self.bridge(self.payload), 'terminal_event_received')
        self.assertEqual(self.inserts, [])

    def test_production_never_imports(self):
        with patch.dict(os.environ, {'CC_APP_ID': 'production'}):
            self.assertEqual(self.bridge(self.payload), 'not_preproduction')
        self.db.assert_not_called()

    def test_missing_plu_never_writes_order(self):
        del self.payload['body']['order']['items'][0]['pos_item_id']
        self.assertEqual(self.bridge(self.payload), 'missing_plu')
        self.db.assert_not_called()

    def test_swapped_plu_never_writes_order(self):
        self.payload['body']['order']['items'][0].update(name='Chicken Burger', pos_item_id='MU11002')
        self.assertEqual(self.bridge(self.payload), 'mismatched_plu')
        self.db.assert_not_called()

    def test_incomplete_update_never_imports(self):
        self.payload['body']['order']['items'] = []
        with self.assertRaises(ValueError):
            self.bridge(self.payload)
        self.db.assert_not_called()

    def test_only_current_accepted_with_log_qualifies(self):
        self.assertTrue(accepted_import_ready(self.payload))
        self.assertFalse(accepted_import_ready(event('accepted', [])))
        for status in ('placed', 'rejected', 'canceled', 'confirmed'):
            self.assertFalse(accepted_import_ready(event(status)))

    def test_fractional_unit_rounding_matches_exact_total(self):
        order = self.payload['body']['order']
        order['items'] = [{'name': 'Burger', 'pos_item_id': 'burger-1', 'quantity': 3, 'total_price': {'fractional': 1001}}]
        order['total_price'] = {'fractional': 1001}
        self.assertEqual(self.bridge(self.payload), 'created')
        from decimal import Decimal
        self.assertEqual(sum(row[4] * row[5] for row in self.item_inserts), Decimal('10.01'))
        self.assertEqual(sum(row[4] for row in self.item_inserts), 3)


class RecoveryGuardsTests(unittest.TestCase):
    def test_recovery_scoped_authenticated_and_idempotent(self):
        import copy
        tree = ast.parse(Path('clean_caisse/deliveroo_sandbox_phase6.py').read_text())
        register = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'register_deliveroo_sandbox_phase6')
        function = copy.deepcopy(next(n for n in register.body if isinstance(n, ast.FunctionDef) and n.name == 'deliveroo_recover_discount_order_9034'))
        function.decorator_list = []
        payload = event('accepted')
        target = 'fr:6044a42b-b404-432a-a34c-fc0279f89794'
        payload['body']['order']['id'] = target
        cursor = Mock()
        cursor.fetchone.return_value = {'payload': payload}
        conn = Mock()
        conn.cursor.return_value = nullcontext(cursor)
        db = Mock(side_effect=lambda: nullcontext(conn))
        bridge = Mock(return_value='created')
        request = SimpleNamespace(headers={'X-Diagnostic-Pin': 'test-pin'})
        namespace = dict(os=os, hmac=hmac, json=json, request=request, db=db,
                         jsonify=lambda data: data, app=SimpleNamespace(logger=Mock()),
                         accepted_import_ready=accepted_import_ready,
                         _extract_order_id=lambda p: p['body']['order']['id'], _bridge_order_new=bridge)
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<recovery>', 'exec'), namespace)
        recover = namespace['deliveroo_recover_discount_order_9034']
        with patch.dict(os.environ, {'CC_APP_ID': 'production'}):
            self.assertEqual(recover()[1], 403)
            db.assert_not_called()
        settings = {'CC_APP_ID': 'app_fad0809f-954d-47e7-983d-afb7c3867cd0',
                    'BECHEFAA_DELIVEROO_ORDER_BRIDGE_ENABLED': '1', 'BECHEFAA_CAISSE_PIN': 'test-pin'}
        with patch.dict(os.environ, settings):
            request.headers = {}
            self.assertEqual(recover()[1], 403)
            db.assert_not_called()
            request.headers = {'X-Diagnostic-Pin': 'test-pin'}
            for result in ('created', 'duplicate'):
                bridge.return_value = result
                response = recover()
                self.assertTrue(response['ok'])
                self.assertFalse(response['deliveroo_api_called'])
            self.assertEqual(cursor.execute.call_args.args[1], (target,))
            bridge.reset_mock()
            cursor.fetchone.return_value = {'payload': event('cancelled')}
            self.assertEqual(recover()[1], 409)
            bridge.assert_not_called()


if __name__ == '__main__':
    unittest.main()
