"""Deliveroo Sandbox connectivity check for BÉCHÉFAA.

Reads credentials from Clever Cloud environment variables and exchanges them for
an OAuth2 client_credentials token. Secrets/tokens are never returned.
"""
import os
import urllib.parse
import urllib.request
import json
import hmac
import hashlib
from flask import jsonify, request, Response

_last_webhooks = {"orders": None, "menu": None, "last_error": None}

def register_deliveroo_sandbox_phase6(app, db):
    def _ensure_diag_table():
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS deliveroo_webhook_diag (
                        kind TEXT PRIMARY KEY,
                        received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        accepted BOOLEAN,
                        error TEXT,
                        event TEXT,
                        sequence_guid TEXT,
                        payload_type TEXT,
                        webhook_version TEXT
                    )
                ''')
            conn.commit()

    def _persist_diag(kind, accepted=None, error=None, event=None, guid=None, payload_type=None, version=None):
        try:
            _ensure_diag_table()
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute('''
                        INSERT INTO deliveroo_webhook_diag
                            (kind, received_at, accepted, error, event, sequence_guid, payload_type, webhook_version)
                        VALUES (%s, NOW(), %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (kind) DO UPDATE SET
                            received_at=EXCLUDED.received_at,
                            accepted=EXCLUDED.accepted,
                            error=EXCLUDED.error,
                            event=EXCLUDED.event,
                            sequence_guid=EXCLUDED.sequence_guid,
                            payload_type=EXCLUDED.payload_type,
                            webhook_version=EXCLUDED.webhook_version
                    ''',(kind,accepted,error,event,guid,payload_type,version))
                conn.commit()
        except Exception as exc:
            app.logger.exception('Deliveroo webhook diagnostic persistence failed: %s', exc)

    def _capture_webhook(kind):
        secret=(os.environ.get("BECHEFAA_DELIVEROO_WEBHOOK_SECRET") or "").strip()
        guid=(request.headers.get("X-Deliveroo-Sequence-Guid") or "").strip()
        supplied=(request.headers.get("X-Deliveroo-Hmac-Sha256") or "").strip().lower()
        payload_type=(request.headers.get("X-Deliveroo-Payload-Type") or "").strip()
        version=(request.headers.get("X-Deliveroo-Webhook-Version") or "").strip()
        raw=request.get_data(cache=True)
        _persist_diag(kind, accepted=None, error="received", guid=guid, payload_type=payload_type, version=version)

        if not secret:
            _last_webhooks["last_error"]={"kind":kind,"error":"webhook_secret_missing"}
            _persist_diag(kind, accepted=False, error="webhook_secret_missing", guid=guid, payload_type=payload_type, version=version)
            app.logger.error("Deliveroo webhook secret is not configured")
            return Response(status=503)
        if not guid or not supplied:
            _last_webhooks["last_error"]={"kind":kind,"error":"signature_headers_missing"}
            _persist_diag(kind, accepted=False, error="signature_headers_missing", guid=guid, payload_type=payload_type, version=version)
            app.logger.warning("Deliveroo webhook rejected: missing signature headers")
            return Response(status=401)

        # Current Order/Menu webhooks use: GUID + single blank space + raw body.
        # Deliveroo requires the exact raw bytes, before JSON parsing.
        signed=guid.encode("utf-8")+b" "+raw
        calculated=hmac.new(secret.encode("utf-8"),signed,hashlib.sha256).hexdigest().lower()
        if not hmac.compare_digest(calculated,supplied):
            _last_webhooks["last_error"]={"kind":kind,"error":"invalid_signature","sequence_guid":guid}
            _persist_diag(kind, accepted=False, error="invalid_signature", guid=guid, payload_type=payload_type, version=version)
            app.logger.warning("Deliveroo webhook rejected: invalid HMAC kind=%s guid=%s",kind,guid)
            return Response(status=401)

        payload=request.get_json(silent=True) or {}
        event=str(payload.get("event") or "")
        _last_webhooks["last_error"]=None
        _persist_diag(kind, accepted=True, error=None, event=event, guid=guid, payload_type=payload_type, version=version)
        _last_webhooks[kind]={
            "received":True,
            "signature_valid":True,
            "event":event,
            "sequence_guid":guid,
            "payload_type":payload_type,
            "webhook_version":version,
        }
        app.logger.info(
            "Deliveroo sandbox webhook verified kind=%s event=%s guid=%s payload_type=%s version=%s",
            kind,event,guid,payload_type,version
        )
        return Response(status=200)

    @app.post("/api/deliveroo/webhooks/orders")
    def deliveroo_orders_webhook_phase6():
        # Phase 1: acknowledge only. No POS order is created until the Sandbox
        # payload has been observed and HMAC verification has been configured.
        return _capture_webhook("orders")

    @app.post("/api/deliveroo/webhooks/menu")
    def deliveroo_menu_webhook_phase6():
        return _capture_webhook("menu")

    @app.get("/api/deliveroo/webhooks/status-phase6")
    def deliveroo_webhooks_status_phase6():
        persisted={}
        try:
            _ensure_diag_table()
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT kind, received_at, accepted, error, event, sequence_guid, payload_type, webhook_version FROM deliveroo_webhook_diag")
                    for row in cur.fetchall():
                        persisted[row["kind"]]={
                            "received_at": row["received_at"].isoformat() if row.get("received_at") else None,
                            "accepted": row.get("accepted"),
                            "error": row.get("error"),
                            "event": row.get("event"),
                            "sequence_guid": row.get("sequence_guid"),
                            "payload_type": row.get("payload_type"),
                            "webhook_version": row.get("webhook_version"),
                        }
        except Exception as exc:
            persisted={"diagnostic_error":str(exc)[:200]}
        return jsonify({
            "ok": True,
            "orders_url": "https://caisse.bechefaa.fr/api/deliveroo/webhooks/orders",
            "menu_url": "https://caisse.bechefaa.fr/api/deliveroo/webhooks/menu",
            "persisted": persisted,
            "last_orders": _last_webhooks["orders"],
            "last_menu": _last_webhooks["menu"],
            "last_error": _last_webhooks["last_error"],
        })

    @app.get("/api/deliveroo/status-phase6")
    def deliveroo_status_phase6():
        client_id=(os.environ.get("BECHEFAA_DELIVEROO_CLIENT_ID") or "").strip()
        client_secret=(os.environ.get("BECHEFAA_DELIVEROO_CLIENT_SECRET") or "").strip()
        auth_url=(os.environ.get("BECHEFAA_DELIVEROO_AUTH_URL") or "https://auth-sandbox.developers.deliveroo.com").rstrip("/")
        api_url=(os.environ.get("BECHEFAA_DELIVEROO_API_URL") or "https://api-sandbox.developers.deliveroo.com").rstrip("/")
        result={
            "ok":False,
            "environment":"sandbox",
            "client_id_present":bool(client_id),
            "client_secret_present":bool(client_secret),
            "webhook_secret_present":bool((os.environ.get("BECHEFAA_DELIVEROO_WEBHOOK_SECRET") or "").strip()),
            "auth_url":auth_url,
            "api_url":api_url,
        }
        if not client_id or not client_secret:
            result["error"]="missing_credentials"
            return jsonify(result), 503
        body=urllib.parse.urlencode({
            "client_id":client_id,
            "client_secret":client_secret,
            "grant_type":"client_credentials",
        }).encode("utf-8")
        req=urllib.request.Request(
            auth_url+"/oauth2/token",
            data=body,
            headers={"Content-Type":"application/x-www-form-urlencoded; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req,timeout=12) as resp:
                data=json.loads(resp.read().decode("utf-8"))
            token=data.get("access_token")
            result.update({
                "ok":bool(token),
                "token_received":bool(token),
                "token_type":data.get("token_type"),
                "expires_in":data.get("expires_in"),
            })
            return jsonify(result), 200 if token else 502
        except Exception as exc:
            code=getattr(exc,"code",None)
            detail=""
            try:
                detail=exc.read().decode("utf-8","replace")[:300]
            except Exception:
                detail=str(exc)[:300]
            result.update({"error":"oauth_failed","status_code":code,"detail":detail})
            return jsonify(result), 502
