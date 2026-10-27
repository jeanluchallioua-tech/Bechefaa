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
                cur.execute("ALTER TABLE deliveroo_webhook_diag ADD COLUMN IF NOT EXISTS safe_summary JSONB")
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

    def _rejected_in_latest_status(payload):
        """Only the latest explicit status is authoritative; old status_log entries are not."""
        if not isinstance(payload, dict) or str(payload.get("event") or "").lower() != "order.status_update":
            return False
        body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
        order = body.get("order") if isinstance(body.get("order"), dict) else {}
        for node in (order, body):
            for key in ("status", "order_status", "state"):
                value = node.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip().lower() in {"rejected", "reject", "declined"}
        log = order.get("status_log") or body.get("status_log")
        if isinstance(log, list) and log:
            latest = log[-1]
            if isinstance(latest, dict):
                value = latest.get("status") or latest.get("order_status") or latest.get("state")
                return str(value or "").strip().lower() in {"rejected", "reject", "declined"}
        return False

    def _bridge_order_rejected(payload):
        """Mark an existing sandbox order rejected without touching other channels."""
        if os.environ.get("CC_APP_ID", "").strip() != "app_fad0809f-954d-47e7-983d-afb7c3867cd0":
            return "not_preproduction"
        if os.environ.get("BECHEFAA_DELIVEROO_ORDER_BRIDGE_ENABLED", "").strip() != "1":
            return "disabled"
        if not _rejected_in_latest_status(payload):
            return "not_rejected"
        external_id = _extract_order_id(payload)
        if not external_id:
            return "missing_order_id"
        import uuid
        import time
        pos_id = "deliveroo-" + uuid.uuid5(uuid.NAMESPACE_URL, external_id).hex
        with db() as conn:
            with conn.transaction():
                from clean_caisse.app import ensure_order_schema
                ensure_order_schema(conn)
                row = conn.execute(
                    "SELECT id,status FROM caisse_orders WHERE id=%s AND sales_channel='DELIVEROO' FOR UPDATE",
                    (pos_id,),
                ).fetchone()
                if not row:
                    return "not_imported"
                if str(row["status"] or "").lower() in {"terminée", "annulée", "rejetée"}:
                    return "already_terminal"
                conn.execute(
                    "UPDATE caisse_orders SET status=%s, updated_at=%s WHERE id=%s AND sales_channel='DELIVEROO'",
                    ("Rejetée", int(time.time() * 1000), pos_id),
                )
        return "rejected"

    def _bridge_order_new(payload):
        """Import an order.new into the isolated preproduction POS, once per Deliveroo ID.

        Opt-in only: no production writes and no kitchen printing until validated.
        """
        if os.environ.get("CC_APP_ID", "").strip() != "app_fad0809f-954d-47e7-983d-afb7c3867cd0":
            return "not_preproduction"
        if os.environ.get("BECHEFAA_DELIVEROO_ORDER_BRIDGE_ENABLED", "").strip() != "1":
            return "disabled"
        body = payload.get("body") if isinstance(payload, dict) else None
        order = body.get("order") if isinstance(body, dict) else None
        if not isinstance(order, dict):
            raise ValueError("order.new missing body.order")
        external_id = str(order.get("id") or order.get("order_id") or "").strip()
        if not external_id:
            raise ValueError("order.new missing order id")
        items = order.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("order.new missing items")
        from decimal import Decimal
        import time
        import uuid
        from clean_caisse.app import ensure_order_schema
        normalized = []
        total = Decimal("0")
        for position, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError("invalid order item")
            name = str(item.get("name") or "").strip()
            qty = int(item.get("quantity") or 0)
            price = item.get("total_price")
            fractional = price.get("fractional") if isinstance(price, dict) else None
            if not name or qty <= 0 or fractional is None:
                raise ValueError("order item missing name/quantity/total_price")
            amount = Decimal(str(fractional)) / Decimal("100")
            if amount < 0:
                raise ValueError("negative item price")
            modifiers = item.get("modifiers") or []
            if not isinstance(modifiers, list):
                raise ValueError("invalid modifiers")
            options = []
            for modifier in modifiers:
                if isinstance(modifier, dict):
                    label = str(modifier.get("name") or "").strip()
                    if label:
                        options.append({"name": label, "plu": str(modifier.get("pos_item_id") or "")})
            unit = amount / qty
            normalized.append((str(item.get("pos_item_id") or ""), name, qty, unit, options, position))
            total += amount
        # Deliveroo schedules are UTC timestamps. Invalid scheduled data must not
        # silently turn a scheduled order into an immediate kitchen ticket.
        asap = order.get("asap")
        scheduled_start_ms = None
        if asap is False:
            raw_start = order.get("start_preparing_at")
            if not isinstance(raw_start, str):
                raise ValueError("scheduled order missing start_preparing_at")
            try:
                start_dt = datetime.fromisoformat(raw_start.replace("Z", "+00:00"))
                if start_dt.tzinfo is None:
                    raise ValueError("scheduled start has no timezone")
                scheduled_start_ms = int(start_dt.timestamp() * 1000)
            except (ValueError, OverflowError) as exc:
                raise ValueError("invalid scheduled start_preparing_at") from exc
        now = int(time.time() * 1000)
        pos_id = "deliveroo-" + uuid.uuid5(uuid.NAMESPACE_URL, external_id).hex
        with db() as conn:
            with conn.transaction():
                ensure_order_schema(conn)
                conn.execute("""CREATE TABLE IF NOT EXISTS deliveroo_kitchen_schedule (
                    order_id TEXT PRIMARY KEY,
                    start_preparing_at_ms BIGINT NOT NULL
                )""")
                conn.execute("LOCK TABLE caisse_orders IN EXCLUSIVE MODE")
                existing = conn.execute("SELECT id FROM caisse_orders WHERE id=%s", (pos_id,)).fetchone()
                if existing:
                    return "duplicate"
                num = int(conn.execute("SELECT COALESCE(MAX(num),0)+1 AS n FROM caisse_orders").fetchone()["n"])
                # Preserve delivery and customer contact data for POS history/preview.
                # Customer Collect is collected at the restaurant, not delivered.
                fulfillment_type = str(order.get("fulfillment_type") or "").strip().lower()
                pos_source = "EMPORTER" if fulfillment_type == "customer" else "LIVRAISON"
                customer = order.get("customer") if isinstance(order.get("customer"), dict) else {}
                delivery = order.get("delivery") if isinstance(order.get("delivery"), dict) else {}
                address_data = delivery.get("address")
                if not isinstance(address_data, dict):
                    address_data = {}
                first = str(customer.get("first_name") or customer.get("firstName") or "").strip()
                last = str(customer.get("last_name") or customer.get("lastName") or "").strip()
                customer_name = (str(delivery.get("customer_name") or "").strip()
                                 or str(customer.get("name") or "").strip()
                                 or " ".join(x for x in (first, last) if x)
                                 or "Client Deliveroo")
                phone = str(delivery.get("contact_number") or customer.get("contact_number")
                            or customer.get("phone") or delivery.get("phone") or "").strip()
                # A geolocation object is not a postal address: never stringify it.
                address = str(address_data.get("address_line_1") or address_data.get("line_1")
                              or address_data.get("street_address") or "").strip()
                postal_code = str(delivery.get("postcode") or address_data.get("postcode")
                                  or address_data.get("postal_code") or "").strip()
                city = str(delivery.get("city") or address_data.get("city") or "").strip()
                conn.execute("""INSERT INTO caisse_orders
                    (id,num,customer_name,phone,address,postal_code,city,source,sales_channel,payment,status,total,created_at,updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'DELIVEROO','PAYÉ EN LIGNE','À préparer',%s,%s,%s)""",
                    (pos_id,num,customer_name,phone,address,postal_code,city,pos_source,total,now,now))
                if scheduled_start_ms is not None:
                    conn.execute(
                        "INSERT INTO deliveroo_kitchen_schedule (order_id, start_preparing_at_ms) VALUES (%s, %s)",
                        (pos_id, scheduled_start_ms))
                for position, (plu,name,qty,unit,options,_) in enumerate(normalized):
                    conn.execute("""INSERT INTO caisse_order_items
                        (order_id,line_id,product_id,name,qty,unit_price,options_json,options_text,prepared,position)
                        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,FALSE,%s)""",
                        (pos_id,str(position),plu or None,name,qty,unit,
                         json.dumps(options,ensure_ascii=False),
                         " • ".join(o["name"] for o in options),position))
        return "created"

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

        if kind=="orders" and event.strip().lower()=="order.status_update":
            try:
                rejection_result=_bridge_order_rejected(payload)
                app.logger.info("Deliveroo preproduction rejection result=%s order=%s", rejection_result, order_id)
            except Exception as exc:
                app.logger.exception("Deliveroo preproduction rejection handling failed: %s", exc)
                return Response(status=500)

        if kind=="orders" and event.strip().lower()=="order.new":
            try:
                bridge_result=_bridge_order_new(payload)
                app.logger.info("Deliveroo preproduction bridge result=%s order=%s",bridge_result,order_id)
            except Exception as exc:
                app.logger.exception("Deliveroo preproduction order bridge failed: %s",exc)
                return Response(status=500)

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
                                sync_error=CASE
                                    WHEN %s::text IS NOT NULL THEN %s::text
                                    WHEN %s::text='succeeded' THEN NULL
                                    ELSE sync_error
                                END
                            WHERE kind='orders'""",
                            (order_id or None,accepted_log,sync_status,sync_http_status,sync_error,sync_error,sync_status))
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

        if kind=="orders" and event.strip().lower()=="order.new":
            try:
                body=payload.get("body") if isinstance(payload,dict) else {}
                body=body if isinstance(body,dict) else {}
                safe_summary={
                    "top_keys": sorted(list(payload.keys())) if isinstance(payload,dict) else [],
                    "body_keys": sorted(list(body.keys())),
                }

                def _collect(node, path="body", depth=0):
                    found=[]
                    if depth>5:
                        return found
                    if isinstance(node,list):
                        if node and all(isinstance(x,dict) for x in node[:5]):
                            sample=[]
                            for x in node[:5]:
                                sample.append({
                                    k:x.get(k) for k in x.keys()
                                    if str(k).lower() in {
                                        "id","item_id","product_id","pos_item_id","menu_item_id","plu","name","item_name","product_name",
                                        "quantity","qty","price","unit_price","total_price","options",
                                        "modifiers","extras","sub_items"
                                    }
                                })
                            if sample:
                                found.append({"path":path,"sample":sample})
                        for i,x in enumerate(node[:3]):
                            found.extend(_collect(x,path+"["+str(i)+"]",depth+1))
                    elif isinstance(node,dict):
                        for k,v in node.items():
                            found.extend(_collect(v,path+"."+str(k),depth+1))
                    return found

                safe_summary["item_like_nodes"]=_collect(body)
                app.logger.info(
                    "DELIVEROO_ORDER_NEW_SAFE %s",
                    json.dumps(safe_summary,ensure_ascii=False)[:12000]
                )
                try:
                    with db() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                "UPDATE deliveroo_webhook_diag SET safe_summary=%s::jsonb WHERE kind='orders'",
                                (json.dumps(safe_summary,ensure_ascii=False),)
                            )
                        conn.commit()
                except Exception as exc:
                    app.logger.exception("Deliveroo safe summary persistence failed: %s",exc)
            except Exception as exc:
                app.logger.exception("Deliveroo safe payload summary failed: %s",exc)

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
                    cur.execute("SELECT kind, received_at, accepted, error, event, sequence_guid, payload_type, webhook_version, order_id, accepted_in_status_log, sync_status, sync_http_status, sync_error, safe_summary FROM deliveroo_webhook_diag")
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
                            "safe_summary": row.get("safe_summary"),
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

    @app.get("/api/deliveroo/diagnostic-doublons-page")
    def deliveroo_diagnostic_page():
        """Small preproduction-only UI; PIN stays in the browser."""
        if os.environ.get("BECHEFAA_DELIVEROO_ORDER_BRIDGE_ENABLED") != "1":
            return Response(status=404)
        from flask import render_template_string
        return render_template_string("""
<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Diagnostic Deliveroo — Préproduction</title>
<style>body{font-family:system-ui,sans-serif;max-width:850px;margin:35px auto;padding:0 18px;color:#193342}
input,button{font:inherit;padding:12px;border-radius:8px}button{background:#143d53;color:white;border:0;cursor:pointer}
input{border:1px solid #aaa}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f8;padding:16px;border-radius:8px}
table{border-collapse:collapse;width:100%}td,th{padding:9px;border-bottom:1px solid #ddd;text-align:left}
small{color:#53636c}</style></head><body>
<h1>Diagnostic Deliveroo</h1><p>Préproduction uniquement — consultation en lecture seule.</p>
<form id="form"><label for="pin">PIN de la caisse</label>
<input id="pin" type="password" autocomplete="off" required>
<button type="submit">Afficher le diagnostic</button></form>
<hr><h2>Correction du ticket 43</h2><p>Commande Deliveroo 3541 — uniquement en préproduction.</p>
<form id="repair-form"><label for="repair-pin">PIN de la caisse</label>
<input id="repair-pin" type="password" autocomplete="off" required>
<button type="submit">Corriger le ticket 43 en À emporter Deliveroo</button></form>
<p id="repair-state" role="status"></p>
<p id="state" role="status"></p><div id="result"></div>
<script>
const form=document.getElementById('form'),state=document.getElementById('state'),out=document.getElementById('result');
document.getElementById('repair-form').addEventListener('submit',async e=>{e.preventDefault();const status=document.getElementById('repair-state');const field=document.getElementById('repair-pin');const pin=field.value;field.value='';if(!confirm('Corriger uniquement le ticket Deliveroo 43 en À emporter ?'))return;status.textContent='Correction en cours…';try{const res=await fetch('/api/deliveroo/repair-customer-collect-43',{method:'POST',headers:{'X-Diagnostic-Pin':pin},cache:'no-store'});const data=await res.json().catch(()=>({}));status.textContent=res.ok&&data.ok?(data.result==='already_correct'?'Ticket 43 déjà corrigé.':'Ticket 43 corrigé en À emporter Deliveroo.'):('Correction non effectuée : '+(data.error||'HTTP '+res.status));}catch(err){status.textContent='Correction non effectuée : '+err.message;}});
function cell(row,value){const td=document.createElement('td');td.textContent=value==null?'—':String(value);row.appendChild(td)}
function table(title,rows,columns){const h=document.createElement('h2');h.textContent=title;out.appendChild(h);
const t=document.createElement('table'),head=document.createElement('tr');
columns.forEach(c=>{const th=document.createElement('th');th.textContent=c[0];head.appendChild(th)});t.appendChild(head);
rows.forEach(item=>{const tr=document.createElement('tr');columns.forEach(c=>cell(tr,item[c[1]]));t.appendChild(tr)});out.appendChild(t)}
form.addEventListener('submit',async e=>{e.preventDefault();out.replaceChildren();state.textContent='Chargement…';
const pin=document.getElementById('pin').value;document.getElementById('pin').value='';
try{const res=await fetch('/api/deliveroo/diagnostic-doublons',{headers:{'X-Diagnostic-Pin':pin},cache:'no-store'});
const data=await res.json();if(!res.ok||!data.ok){state.textContent=data.error||'Erreur '+res.status;return}
state.textContent='Diagnostic chargé. Ne partagez pas le PIN.';
table('Événements order.new',data.events||[],[['Commande Deliveroo','deliveroo_order_id'],['Événement','sequence_guid'],['Reçu (UTC)','received_at_utc'],['Ticket','ticket'],['Articles','item_count'],['Empreinte panier','item_signature'],['Remake présent','remake_details_present'],['Remake type','remake_details_type'],['Champs remake','remake_details_keys'],['Référence Deliveroo','display_id'],['Brand ID','brand_id'],['Création source','order_created_at'],['Statut','order_status'],['Type','order_type'],['Champs commande','order_fields'],['Champs enveloppe','body_fields'],['Champs horaires (présence)','schedule_field_paths'],['ASAP','asap_value'],['Début préparation UTC','start_preparing_at_value'],['Programmation enregistrée','stored_schedule'],['Cuisine devrait afficher','kitchen_should_show'],['Cuisine SQL: ticket visible','kitchen_sql_visible'],['Statut ticket','ticket_status'],['Filtre préprod actif','preprod_filter_active'],['Ticket POS','ticket'],['Préparer pour UTC','prepare_for_value'],['Téléphone renseigné','contact_number_filled'],['Champs client (présence)','customer_field_paths'],['Champs livraison (présence)','delivery_field_paths']]);
table('Tickets Deliveroo',data.tickets||[],[['Numéro','num'],['Identifiant POS','id'],['Créé','created_at']]);
}catch(err){state.textContent='Erreur de chargement : '+err.message}});
</script></body></html>
""")

    def _diagnostic_field_paths(root, keywords):
        """Field names only: never return values or customer-identifying data."""
        found = set()
        def visit(value, prefix="", depth=0):
            if depth > 4 or len(found) >= 80:
                return
            if isinstance(value, dict):
                for key, child in value.items():
                    key = str(key)
                    path = (prefix + "." + key) if prefix else key
                    if any(term in key.lower() for term in keywords):
                        found.add(path[:120])
                    if isinstance(child, (dict, list)):
                        visit(child, path, depth + 1)
            elif isinstance(value, list):
                for child in value[:2]:
                    if isinstance(child, (dict, list)):
                        visit(child, prefix + "[]", depth + 1)
        visit(root)
        return found

    def _safe_schedule_time(value):
        if not isinstance(value, str) or len(value) > 45:
            return "absent ou format non reconnu"
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return "sans fuseau horaire"
            return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
        except (ValueError, OverflowError):
            return "format non reconnu"

    @app.post("/api/deliveroo/repair-customer-collect-43")
    def repair_customer_collect_43():
        """One-ticket, PIN-protected preproduction correction; no production writes."""
        if os.environ.get("CC_APP_ID", "").strip() != "app_fad0809f-954d-47e7-983d-afb7c3867cd0":
            return Response(status=404)
        if os.environ.get("BECHEFAA_DELIVEROO_ORDER_BRIDGE_ENABLED", "").strip() != "1":
            return Response(status=404)
        expected = (os.environ.get("BECHEFAA_CAISSE_PIN") or "").strip()
        supplied = (request.headers.get("X-Diagnostic-Pin") or "").strip()
        if not expected or not hmac.compare_digest(expected, supplied):
            return jsonify({"ok": False, "error": "PIN incorrect"}), 403
        import uuid
        external_id = "fr:21ab80b2-ad94-4f82-8fee-6250e34b409d"
        pos_id = "deliveroo-" + uuid.uuid5(uuid.NAMESPACE_URL, external_id).hex
        with db() as conn:
            with conn.transaction():
                event = conn.execute(
                    """SELECT payload FROM deliveroo_sandbox_events
                       WHERE event='order.new' AND order_id=%s
                       ORDER BY received_at DESC LIMIT 1""",
                    (external_id,),
                ).fetchone()
                if not event:
                    return jsonify({"ok": False, "error": "Événement Deliveroo introuvable"}), 404
                payload = event["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                order = ((payload or {}).get("body") or {}).get("order") or {}
                if str(order.get("fulfillment_type") or "").lower() != "customer":
                    return jsonify({"ok": False, "error": "Commande non confirmée comme customer collect"}), 409
                row = conn.execute(
                    """SELECT id,num,source,sales_channel FROM caisse_orders
                       WHERE id=%s FOR UPDATE""", (pos_id,)
                ).fetchone()
                if not row or int(row["num"]) != 43 or row["sales_channel"] != "DELIVEROO":
                    return jsonify({"ok": False, "error": "Ticket 43 non identifié de façon certaine"}), 409
                if row["source"] == "EMPORTER":
                    return jsonify({"ok": True, "result": "already_correct", "ticket": 43})
                if row["source"] != "LIVRAISON":
                    return jsonify({"ok": False, "error": "Type de commande inattendu"}), 409
                conn.execute(
                    "UPDATE caisse_orders SET source='EMPORTER' WHERE id=%s AND source='LIVRAISON'",
                    (pos_id,),
                )
        return jsonify({"ok": True, "result": "corrected", "ticket": 43, "source": "EMPORTER"})

    @app.get("/api/deliveroo/diagnostic-doublons")
    def deliveroo_diagnostic_doublons():
        """Read-only sandbox webhook/order correlation; preproduction only."""
        if os.environ.get("BECHEFAA_DELIVEROO_ORDER_BRIDGE_ENABLED") != "1":
            return Response(status=404)
        expected = (os.environ.get("BECHEFAA_CAISSE_PIN") or "").strip()
        supplied = (request.headers.get("X-Diagnostic-Pin") or "").strip()
        if not expected or not hmac.compare_digest(expected, supplied):
            return jsonify({"ok": False, "error": "PIN incorrect"}), 403
        import uuid
        try:
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""SELECT sequence_guid, order_id, received_at, payload
                        FROM deliveroo_sandbox_events
                        WHERE event = 'order.new'
                        ORDER BY received_at DESC LIMIT 40""")
                    events = cur.fetchall()
                    cur.execute("""SELECT id, num, created_at
                        FROM caisse_orders WHERE sales_channel = 'DELIVEROO'
                        ORDER BY created_at DESC LIMIT 40""")
                    orders = cur.fetchall()
                    cur.execute("""SELECT id, num, status FROM caisse_orders
                        WHERE sales_channel = 'DELIVEROO'
                        ORDER BY created_at DESC LIMIT 100""")
                    order_states = {str(r["id"]): r for r in cur.fetchall()}
                    cur.execute("SELECT to_regclass('deliveroo_kitchen_schedule') AS table_name")
                    schedule_exists = bool(cur.fetchone()["table_name"])
                    if schedule_exists:
                        cur.execute("""SELECT order_id, start_preparing_at_ms
                            FROM deliveroo_kitchen_schedule ORDER BY start_preparing_at_ms DESC LIMIT 100""")
                        schedules = {str(r["order_id"]): int(r["start_preparing_at_ms"]) for r in cur.fetchall()}
                    else:
                        schedules = {}
            index = {str(o["id"]): o for o in orders}
            rows = []
            for e in events:
                external = str(e["order_id"] or "")
                pos_id = "deliveroo-" + uuid.uuid5(uuid.NAMESPACE_URL, external).hex if external else None
                matched = index.get(pos_id)
                payload = e.get("payload") or {}
                if isinstance(payload, str):
                    payload = json.loads(payload)
                body = payload.get("body") if isinstance(payload, dict) else {}
                order = body.get("order") if isinstance(body, dict) else {}
                if not isinstance(order, dict):
                    order = {}
                items = order.get("items") or []
                if not isinstance(items, list):
                    items = []
                # Hash of item structure only, never expose names, addresses or payload.
                signature_items = []
                for item in items:
                    if isinstance(item, dict):
                        modifiers = item.get("modifiers") or []
                        signature_items.append({
                            "quantity": item.get("quantity"),
                            "total_price": item.get("total_price"),
                            "modifier_count": len(modifiers) if isinstance(modifiers, list) else 0,
                        })
                signature = hashlib.sha256(json.dumps(signature_items,sort_keys=True,default=str).encode()).hexdigest()[:12]
                rows.append({
                    "order_fields": ", ".join(sorted(k for k in order.keys() if k in {
                        "id", "order_id", "created_at", "placed_at", "scheduled_at",
                        "status", "type", "fulfilment_type", "restaurant_id",
                        "site_id", "brand_id", "reference", "display_id",
                    })),
                    "ticket_status": str(order_states[pos_id]["status"]) if pos_id in order_states else "ABSENT",
                    "kitchen_sql_visible": (
                        "OUI" if pos_id in order_states
                        and order_states[pos_id]["status"] in ("À préparer", "En préparation")
                        and (pos_id not in schedules or schedules[pos_id] <= int(datetime.now(timezone.utc).timestamp() * 1000))
                        else "NON"
                    ),
                    "preprod_filter_active": "OUI" if os.environ.get("CC_APP_ID", "").strip() == "app_fad0809f-954d-47e7-983d-afb7c3867cd0" else "NON",
                    "kitchen_should_show": (
                        "NON" if pos_id in schedules and schedules[pos_id] > int(datetime.now(timezone.utc).timestamp() * 1000)
                        else "OUI" if pos_id in schedules else "INCONNU (programmation absente)"
                    ),
                    "stored_schedule": (
                        datetime.fromtimestamp(schedules[pos_id] / 1000, tz=timezone.utc).isoformat(timespec="seconds")
                        if pos_id in schedules else "ABSENTE"
                    ),
                    "asap_value": str(order.get("asap")) if isinstance(order.get("asap"), bool) else "non renseigné",
                    "start_preparing_at_value": _safe_schedule_time(order.get("start_preparing_at")),
                    "prepare_for_value": _safe_schedule_time(order.get("prepare_for")),
                    "schedule_field_paths": ", ".join(sorted(_diagnostic_field_paths(order, ("schedul", "time", "date", "ready", "deliver", "collect", "pickup", "prepar", "fulfil", "asap", "slot", "window", "promise", "due", "target", "deadline")))),
                    "body_fields": ", ".join(sorted(k for k in body.keys() if k in {
                        "order", "order_id", "id", "event_id", "timestamp",
                        "scenario", "scenario_id", "test_id", "site_id",
                    })),
                    "remake_details_present": "remake_details" in order,
                    "remake_details_type": type(order.get("remake_details")).__name__ if "remake_details" in order else "",
                    "remake_details_keys": ", ".join(sorted(str(k) for k in order.get("remake_details", {}).keys())) if isinstance(order.get("remake_details"), dict) else "",
                    "display_id": str(order.get("display_id") or "")[:80],
                    "brand_id": str(order.get("brand_id") or "")[:80],
                    "order_status": str(order.get("status") or "")[:40],
                    "order_type": str(order.get("type") or order.get("fulfilment_type") or "")[:40],
                    "order_created_at": str(order.get("created_at") or order.get("placed_at") or "")[:50],
                    "contact_number_filled": "OUI" if bool(str((order.get("delivery") if isinstance(order.get("delivery"), dict) else {}).get("contact_number") or (order.get("customer") if isinstance(order.get("customer"), dict) else {}).get("contact_number") or "").strip()) else "NON",
                    "customer_field_paths": ", ".join(sorted(_diagnostic_field_paths(order, ("customer", "consumer", "recipient", "contact", "name", "phone", "first_name", "last_name", "telephone", "mobile", "email")))),
                    "delivery_field_paths": ", ".join(sorted(_diagnostic_field_paths(order, ("delivery", "address", "postcode", "postal_code", "city", "instructions", "notes", "fulfilment", "location", "street", "building", "apartment")))),
                    "item_count": len(items),
                    "item_signature": signature,
                    "event_type": str(payload.get("event") or "") if isinstance(payload, dict) else "",
                    "deliveroo_order_id": external,
                    "sequence_guid": e["sequence_guid"],
                    "received_at_utc": e["received_at"].isoformat() if e["received_at"] else None,
                    "ticket": matched["num"] if matched else None
                })
            return jsonify({"ok": True, "events": rows,
                "tickets": [{"num": o["num"], "id": o["id"], "created_at": o["created_at"]} for o in orders]})
        except Exception:
            app.logger.exception("Deliveroo diagnostic read failed")
            return jsonify({"ok": False, "error": "Lecture impossible"}), 500

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
