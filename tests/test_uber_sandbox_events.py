import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from flask import Flask
from clean_caisse.uber_webhook_phase6 import register_uber_webhook_phase6
from clean_caisse.uber_sandbox_link import STORE_ID


class UberSandboxEventTests(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.conn = self.db.return_value.__enter__.return_value
        self.cursor = self.conn.cursor.return_value.__enter__.return_value
        self.cursor.fetchone.return_value = {'inbox_exists': True}
        self.cursor.fetchall.return_value = []
        app = Flask(__name__)
        app.secret_key = 'test-only'
        register_uber_webhook_phase6(app, self.db)
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session['caisse_auth'] = True

    def test_session_required_before_database_access(self):
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get('/api/uber/sandbox/events').status_code, 403)
        self.db.assert_not_called()

    def test_first_visit_without_table_does_not_create_anything(self):
        self.cursor.fetchone.return_value = (False,)
        response = self.client.get('/api/uber/sandbox/events')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['recent_events'], [])
        self.assertFalse(response.json['inbox_exists'])
        self.assertEqual(self.cursor.execute.call_count, 1)
        self.assertTrue(self.cursor.execute.call_args.args[0].startswith('SELECT'))
        self.conn.commit.assert_not_called()
        self.cursor.fetchall.assert_not_called()

    def test_event_report_reads_only_fixed_store_and_does_not_accept_orders(self):
        self.cursor.fetchall.return_value = [('event-1', datetime(2026,11,17,12,0,tzinfo=timezone.utc), 'orders.notification', 'pending', 'order-test-1')]
        response = self.client.get('/api/uber/sandbox/events?store_id=other-store')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['store_id'], STORE_ID)
        self.assertTrue(response.json['read_only'])
        self.assertFalse(response.json['order_processing_enabled'])
        self.assertEqual(response.json['recent_events_count'], 1)
        event = response.json['recent_events'][0]
        self.assertEqual(event['event_type'], 'orders.notification')
        self.assertEqual(event['received_at'], '2026-11-17T12:00:00+00:00')
        self.assertNotIn('payload', event)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.cursor.execute.call_args.args[1], (STORE_ID,))
        self.assertIn('LIMIT 20', self.cursor.execute.call_args.args[0])
        for call in self.cursor.execute.call_args_list:
            self.assertTrue(call.args[0].startswith('SELECT'))
        self.conn.commit.assert_not_called()

    def test_storage_failure_is_not_confused_with_empty_inbox(self):
        self.cursor.execute.side_effect = RuntimeError('private connection credentials')
        response = self.client.get('/api/uber/sandbox/events')
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json['ok'])
        self.assertNotIn('private connection credentials', response.text)
        self.assertNotIn('recent_events_count', response.json)


if __name__ == '__main__': unittest.main()
