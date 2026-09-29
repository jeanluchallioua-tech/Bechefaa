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
from datetime import datetime, timezone
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
                        webhook_version TEXT,
                        order_id TEXT,
                        accepted_in_status_log BOOLEAN,
                        sync_status TEXT,
                        sync_http_status INTEGER,
                        sync_error TEXT
                    )
                ''')
                cur.execute("ALTER TABLE deliveroo_webhook_diag ADD COLUMN IF NOT EXISTS order_id TEXT")
                cur.execute("ALTER TABLE deliveroo_webhook_diag ADD COLUMN IF NOT EXISTS accepted_in_status_log BOOLEAN")
                cur.execute("ALTER TABLE deliveroo_webhook_diag ADD COLUMN IF NOT EXISTS sync_status TEXT")
                cur.execute("ALTER TABLE deliveroo_webhook_diag ADD COLUMN IF NOT EXISTS sync_http_status INTEGER")
                cur.execute("ALTER TABLE deliveroo_webhook_diag ADD COLUMN IF NOT EXISTS sync_error TEXT")
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

    def _oauth_token():
        client_id=(os.environ.get("BECHEFAA_DELIVEROO_CLIENT_ID") or "").strip()
        client_secret=(os.environ.get("BECHEFAA_DELIVEROO_CLIENT_SECRET") or "").strip()
        auth_url=(os.environ.get("BECHEFAA_DELIVEROO_AUTH_URL") or "https://auth-sandbox.developers.deliveroo.com").rstrip("/")
        if not client_id or not client_secret:
            raise RuntimeError("Deliveroo credentials missing")
        body=urllib.parse.urlencode({
            "client_id":client_id,
            "client_secret":client_secret,
            "grant_type":"client_credentials",
        }).encode("utf-8")
        req=urllib.request.Request(
            auth_url+"/oauth2/token",
            data=body,
            headers={
                "Content-Type":"application/x-www-form-urlencoded; charset=utf-8",
                "Accept":"application/json",
                "User-Agent":"Bechefaa-Deliveroo-Integration/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req,timeout=12) as resp:
            data=json.loads(resp.read().decode("utf-8"))
        token=str(data.get("access_token") or "").strip()
        if not token:
            raise RuntimeError("Deliveroo token missing")
        return token

    def _extract_order_id(payload):
        body=payload.get("body") if isinstance(payload,dict) else {}
        body=body if isinstance(body,dict) else {}
        candidates=[
            body.get("order_id"), body.get("id"),
            (body.get("order") or {}).get("id") if isinstance(body.get("order"),dict) else None,
            payload.get("order_id") if isinstance(payload,dict) else None,
        ]
        for value in candidates:
            value=str(value or "").strip()
            if value:
                return value
        return ""

    def _accepted_in_status_log(payload):
        # Deliveroo may nest the status log differently between sandbox event
        # payloads. Only consider an accepted status on a status-update event.
        if not isinstance(payload,dict) or str(payload.get("event") or "").strip().lower()!="order.status_update":
            return False

        def _walk(value):
            if isinstance(value,dict):
                for key,item in value.items():
                    k=str(key or "").strip().lower()
                    if k in {"status","order_status","state"} and str(item or "").strip().lower()=="accepted":
                        return True
                    if _walk(item):
                        return True
            elif isinstance(value,list):
                for item in value:
                    if _walk(item):
                        return True
            elif isinstance(value,str) and value.strip().lower()=="accepted":
                return True
            return False

        return _walk(payload)

    def _persist_order_event(payload):
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("""CREATE TABLE IF NOT EXISTS deliveroo_sandbox_events (
                    sequence_guid TEXT PRIMARY KEY,
                    event TEXT,
                    order_id TEXT,
                    accepted_in_status_log BOOLEAN NOT NULL DEFAULT FALSE,
                    payload JSONB NOT NULL,
                    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )""")
                cur.execute("""
                    INSERT INTO deliveroo_sandbox_events
                        (sequence_guid,event,order_id,accepted_in_status_log,payload)
                    VALUES (%s,%s,%s,%s,%s::jsonb)
                    ON CONFLICT (sequence_guid) DO UPDATE SET
                        event=EXCLUDED.event,
                        order_id=EXCLUDED.order_id,
                        accepted_in_status_log=EXCLUDED.accepted_in_status_log,
                        payload=EXCLUDED.payload,
                        received_at=NOW()
                """,(
                    str(request.headers.get("X-Deliveroo-Sequence-Guid") or ""),
                    str(payload.get("event") or ""),
                    _extract_order_id(payload),
                    _accepted_in_status_log(payload),
                    json.dumps(payload,ensure_ascii=False),
                ))
            conn.commit()

    def _send_sync_status(order_id):
        token=_oauth_token()
        api_url=(os.environ.get("BECHEFAA_DELIVEROO_API_URL") or "https://api-sandbox.developers.deliveroo.com").rstrip("/")
        url=api_url+"/order/v1/orders/"+urllib.parse.quote(order_id,safe=":")+"/sync_status"
        payload=json.dumps({
            "status":"succeeded",
            "reason":None,
            "notes":"BÉCHÉFAA sandbox order event ingested successfully",
            "occurred_at":datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z"),
        }).encode("utf-8")
        req=urllib.request.Request(
            url,data=payload,
            headers={
                "Authorization":"Bearer "+token,
                "Content-Type":"application/json",
                "Accept":"application/json",
                "User-Agent":"Bechefaa-Deliveroo-Integration/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req,timeout=12) as resp:
            return int(resp.status), resp.read().decode("utf-8","replace")[:300]

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
        order_id=_extract_order_id(payload) if kind=="orders" else ""
        accepted_log=_accepted_in_status_log(payload) if kind=="orders" else False
        sync_status=None
        sync_http_status=None
        sync_error=None

        if kind=="orders":
            try:
                _persist_order_event(payload)
            except Exception as exc:
                app.logger.exception("Deliveroo event persistence failed: %s", exc)
                return Response(status=500)

            # Deliveroo Sandbox expects sync_status only after a webhook
            # confirms that the order has reached accepted in its status log.
            should_sync=(event.strip().lower()=="order.status_update" and accepted_log and bool(order_id))
            if should_sync:
                try:
                    sync_http_status,_sync_body=_send_sync_status(order_id)
                    sync_status="succeeded" if 200 <= sync_http_status < 300 else "unexpected_response"
                except Exception as exc:
                    sync_status="failed"
                    sync_http_status=getattr(exc,"code",None)
                    try:
                        sync_error=exc.read().decode("utf-8","replace")[:300]
                    except Exception:
                        sync_error=str(exc)[:300]
                    app.logger.exception("Deliveroo sync status failed order=%s: %s", order_id, exc)

        _last_webhooks["last_error"]=None
        _persist_diag(kind, accepted=True, error=None, event=event, guid=guid, payload_type=payload_type, version=version)
        if kind=="orders":
            try:
                with db() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""UPDATE deliveroo_webhook_diag
                            SET order_id=%s,
                                accepted_in_status_log=%s,
                                sync_status=COALESCE(%s,sync_status),
                                sync_http_status=COALESCE(%s,sync_http_status),
                                sync_error=COALESCE(%s,sync_error)
                            WHERE kind='orders'""",
                            (order_id or None,accepted_log,sync_status,sync_http_status,sync_error))
                    conn.commit()
            except Exception as exc:
                app.logger.exception("Deliveroo sync diagnostic persistence failed: %s", exc)

        _last_webhooks[kind]={
            "received":True,
            "signature_valid":True,
            "event":event,
            "sequence_guid":guid,
            "payload_type":payload_type,
            "webhook_version":version,
            "order_id":order_id or None,
            "accepted_in_status_log":accepted_log,
            "sync_status":sync_status,
            "sync_http_status":sync_http_status,
            "sync_error":sync_error,
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
                    cur.execute("SELECT kind, received_at, accepted, error, event, sequence_guid, payload_type, webhook_version, order_id, accepted_in_status_log, sync_status, sync_http_status, sync_error FROM deliveroo_webhook_diag")
                    for row in cur.fetchall():
                        persisted[row["kind"]]={
                            "received_at": row["received_at"].isoformat() if row.get("received_at") else None,
                            "accepted": row.get("accepted"),
                            "error": row.get("error"),
                            "event": row.get("event"),
                            "sequence_guid": row.get("sequence_guid"),
                            "payload_type": row.get("payload_type"),
                            "webhook_version": row.get("webhook_version"),
                            "order_id": row.get("order_id"),
                            "accepted_in_status_log": row.get("accepted_in_status_log"),
                            "sync_status": row.get("sync_status"),
                            "sync_http_status": row.get("sync_http_status"),
                            "sync_error": row.get("sync_error"),
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
