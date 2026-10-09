"""Signed Uber Eats inbox. Receiving an event does not accept an order."""
import hashlib
import hmac
import json
import os

from flask import Response, jsonify, request


def register_uber_webhook_phase6(app, db):
    from .uber_sandbox_link import register_uber_sandbox_link
    register_uber_sandbox_link(app)

    @app.post('/api/uber/webhook')
    def uber_webhook_phase6():
        secret = os.environ.get('BECHEFAA_UBER_CLIENT_SECRET', '')
        if not secret:
            return jsonify(ok=False, error='uber_not_configured'), 503
        if request.content_length and request.content_length > 1024 * 1024:
            return jsonify(ok=False, error='payload_too_large'), 413
        body = request.get_data()
        signature = request.headers.get('X-Uber-Signature', '')
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return jsonify(ok=False, error='invalid_signature'), 401
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return jsonify(ok=False, error='invalid_json'), 400
        if not isinstance(payload, dict):
            return jsonify(ok=False, error='invalid_payload'), 400
        # Store before acknowledgement so database failures cause Uber to retry.
        # A stable event identifier avoids duplicate delivery across workers.
        event_id = payload.get('event_id')
        key = str(event_id) if isinstance(event_id, (str, int)) else hashlib.sha256(body).hexdigest()
        try:
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute('''CREATE TABLE IF NOT EXISTS uber_webhook_inbox (
                        event_key TEXT PRIMARY KEY,
                        received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        event_type TEXT,
                        payload JSONB NOT NULL,
                        processing_status TEXT NOT NULL DEFAULT 'pending'
                    )''')
                    cur.execute('''INSERT INTO uber_webhook_inbox
                        (event_key, event_type, payload) VALUES (%s, %s, %s::jsonb)
                        ON CONFLICT (event_key) DO NOTHING''',
                        (key, str(payload.get('event_type', ''))[:200], json.dumps(payload)))
                conn.commit()
        except Exception:
            app.logger.error('Uber webhook inbox persistence failed')
            return jsonify(ok=False, error='storage_unavailable'), 503
        return Response('', status=200)

    @app.get('/api/uber/status-phase6')
    def uber_status_phase6():
        return jsonify(
            configured=bool(os.environ.get('BECHEFAA_UBER_CLIENT_SECRET')),
            authentication='HMAC-SHA256 / X-Uber-Signature',
            webhook_path='/api/uber/webhook',
            order_processing_enabled=False,
        )
