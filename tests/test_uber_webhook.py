import hashlib
import hmac
import os
import unittest
from unittest.mock import patch
from flask import Flask
from clean_caisse.uber_webhook_phase6 import register_uber_webhook_phase6

class Store:
    def __init__(self): self.events = {}; self.failed = False
    def __call__(self): return self
    def __enter__(self):
        if self.failed: raise RuntimeError('unavailable')
        return self
    def __exit__(self, *args): pass
    def cursor(self): return self
    def execute(self, sql, args=None):
        if args: self.events.setdefault(args[0], args)
    def commit(self): pass

class UberWebhookTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'BECHEFAA_UBER_CLIENT_SECRET': 'test-secret'})
        self.env.start(); self.addCleanup(self.env.stop)
        self.store = Store()
        app = Flask(__name__)
        register_uber_webhook_phase6(app, self.store)
        self.client = app.test_client()
    def send(self, body=b'{"event_id":"e1","event_type":"orders.notification"}', signature=None):
        if signature is None:
            signature = hmac.new(b'test-secret', body, hashlib.sha256).hexdigest()
        return self.client.post('/api/uber/webhook', data=body, headers={'X-Uber-Signature': signature})
    def test_invalid_signature_never_stored(self):
        self.assertEqual(self.send(signature='bad').status_code, 401)
        self.assertFalse(self.store.events)
    def test_missing_secret_fails_closed(self):
        with patch.dict(os.environ, {'BECHEFAA_UBER_CLIENT_SECRET': ''}):
            self.assertEqual(self.send().status_code, 503)
        self.assertFalse(self.store.events)
    def test_valid_delivery_and_duplicate(self):
        for _ in range(2):
            response = self.send()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b'')
        self.assertEqual(len(self.store.events), 1)
    def test_tampered_body(self):
        signature = hmac.new(b'test-secret', b'{}', hashlib.sha256).hexdigest()
        self.assertEqual(self.send(signature=signature).status_code, 401)
    def test_invalid_json_and_non_object(self):
        for body in (b'not-json', b'[]'):
            self.assertEqual(self.send(body).status_code, 400)
    def test_database_failure_requires_retry(self):
        self.store.failed = True
        self.assertEqual(self.send().status_code, 503)
    def test_status_does_not_claim_order_processing(self):
        self.assertFalse(self.client.get('/api/uber/status-phase6').json['order_processing_enabled'])

if __name__ == '__main__': unittest.main()
