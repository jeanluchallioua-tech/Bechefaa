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
        # Only order-level status fields and explicit status-log entries are
        # evidence of acceptance. Nested customer/item metadata may also have
        # a "status" field and must never trigger order-level sync.
        if (not isinstance(payload, dict)
                or str(payload.get("event") or "").strip().lower() != "order.status_update"):
            return False
        body = payload.get("body")
        if not isinstance(body, dict):
            return False

        def _accepted(value):
            return isinstance(value, str) and value.strip().lower() == "accepted"

        def _accepted_log(value, depth=0):
            if depth > 16:
                return False
            if isinstance(value, dict):
                for key, item in value.items():
                    if (str(key).strip().lower() in {"status", "order_status", "state"}
                            and _accepted(item)):
                        return True
                    if isinstance(item, (dict, list)) and _accepted_log(item, depth + 1):
                        return True
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, (dict, list)) and _accepted_log(item, depth + 1):
                        return True
            return False

        for record in (body, body.get("order")):
            if not isinstance(record, dict):
                continue
            if any(_accepted(record.get(key))
                   for key in ("status", "order_status", "state")):
                return True
            if any(_accepted_log(record.get(key))
                   for key in ("status_log", "status_history")):
                return True
        return False

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
                # Sequence GUID is an immutable delivery-event identity. A replay
                # with the same body is harmless; a different body under that
                # GUID must not overwrite audit evidence or reach the POS bridge.
                guid = str(request.headers.get("X-Deliveroo-Sequence-Guid") or "")
                body_json = json.dumps(payload, ensure_ascii=False)
                cur.execute("""
                    INSERT INTO deliveroo_sandbox_events
                        (sequence_guid,event,order_id,accepted_in_status_log,payload)
                    VALUES (%s,%s,%s,%s,%s::jsonb)
                    ON CONFLICT (sequence_guid) DO NOTHING
                    RETURNING sequence_guid
                """, (
                    guid,
                    str(payload.get("event") or ""),
                    _extract_order_id(payload),
                    _accepted_in_status_log(payload),
                    body_json,
                ))
                if cur.fetchone() is None:
                    # PostgreSQL JSONB equality ignores object key ordering.
                    # This SELECT runs after the unique-index conflict wait.
                    cur.execute("""
                        SELECT payload = %s::jsonb AS same_payload
                        FROM deliveroo_sandbox_events WHERE sequence_guid=%s
                    """, (body_json, guid))
                    existing = cur.fetchone()
                    if not existing or existing["same_payload"] is not True:
                        raise ValueError("Deliveroo sequence GUID replay payload conflict")
            conn.commit()

    def _bridge_order_new(payload):
        """Import an order.new into the isolated preproduction POS, once per Deliveroo ID.

        Opt-in only: no production writes and no kitchen printing until validated.
        """
        if os.environ.get("CC_APP_ID", "").strip() != "app_fad0809f-954d-47e7-983d-afb7c3867cd0":
            return "not_preproduction"
        if os.environ.get("BECHEFAA_DELIVEROO_ORDER_BRIDGE_ENABLED", "").strip() != "1":
            return "disabled"
        if not isinstance(payload, dict) or payload.get("event") != "order.new":
            raise ValueError("Deliveroo bridge only accepts order.new events")
        body = payload.get("body")
        order = body.get("order") if isinstance(body, dict) else None
        if not isinstance(order, dict):
            raise ValueError("order.new missing body.order")
        # Reject silently normalized IDs: a replay must always derive the
        # same POS key from the exact identifier accepted by the read-only parser.
        from clean_caisse.deliveroo_order_mapping_phase6 import _canonical_id
        external_id = _canonical_id(
            order.get("id") or order.get("order_id"), "Deliveroo order ID"
        )
        items = order.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("order.new missing items")
        # Customer instructions have not yet been mapped to the POS/kitchen
        # ticket. Never acknowledge an opt-in bridge import that drops them.
        from clean_caisse.deliveroo_instruction_audit_phase6 import audit_instruction_fields
        instruction_audit = audit_instruction_fields(payload)
        if not instruction_audit["scan_complete"]:
            raise ValueError("Deliveroo instruction audit incomplete; manual review required")
        if any(not isinstance(entry["value"], str) or entry["value"].strip()
               for entry in instruction_audit["candidate_values"]):
            raise ValueError("Deliveroo customer instructions require approved kitchen mapping")
        from decimal import Decimal
        import time
        import uuid
        from clean_caisse.app import ensure_order_schema
        def _required_eur_cents(value, label):
            if not isinstance(value, dict) or value.get("currency_code") != "EUR":
                raise ValueError("Deliveroo " + label + " must be EUR")
            cents = value.get("fractional")
            if type(cents) is not int or cents < 0:
                raise ValueError("invalid Deliveroo " + label + " cents")
            return cents

        # A declared order total may include fees/discounts. Until their
        # accounting policy is approved, reject rather than silently drop them.
        reported_order_cents = (_required_eur_cents(order["total_price"], "order total")
                                if "total_price" in order else None)
        normalized = []
        total = Decimal("0")
        for position, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError("invalid order item")
            raw_name = item.get("name")
            if not isinstance(raw_name, str):
                raise ValueError("invalid Deliveroo item name type")
            name = raw_name.strip()
            qty = item.get("quantity")
            if type(qty) is not int or qty < 1:
                raise ValueError("invalid Deliveroo item quantity")
            plu = _canonical_id(item.get("pos_item_id"), "POS item ID")
            fractional = _required_eur_cents(item.get("total_price"), "item total")
            # The reported unit price is evidence even when modifiers mean
            # that it cannot safely be used as the POS accounting unit.
            reported_unit_cents = (_required_eur_cents(item["unit_price"], "item unit price")
                                   if "unit_price" in item else None)
            if not name or any(ord(ch) < 32 or 127 <= ord(ch) <= 159 for ch in name):
                raise ValueError("invalid Deliveroo item name")
            # The POS persists a single unit price for every quantity. A line
            # amount that cannot be divided into whole euro cents would be
            # rounded when re-totalled or printed. Do not invent a discount
            # allocation or silently lose cents without an approved policy.
            if fractional % qty:
                raise ValueError("Deliveroo line total has no exact cent unit price; financial review required")
            amount = Decimal(fractional) / Decimal("100")
            modifiers = item.get("modifiers")
            if modifiers is None:
                modifiers = []
            if not isinstance(modifiers, list):
                raise ValueError("invalid modifiers")
            # With no modifiers, the declared unit and line totals must agree
            # exactly in cents. Discounts or fees need explicit review rather
            # than silently importing a different POS unit price.
            if (reported_unit_cents is not None and not modifiers
                    and reported_unit_cents * qty != fractional):
                raise ValueError("Deliveroo unit and line prices differ; financial review required")
            options = []
            modifier_unit_prices = []
            for modifier in modifiers:
                if not isinstance(modifier, dict):
                    raise ValueError("invalid Deliveroo modifier")
                modifier_plu = _canonical_id(
                    modifier.get("pos_item_id"), "modifier POS item ID"
                )
                # A generated option PLU encodes its parent product and the
                # zero-based group/choice indices. Reject mismatched parents
                # and noncanonical indices before writing a kitchen order.
                # Legacy unprefixed PLUs still require separate catalog review.
                if modifier_plu.startswith("opt:"):
                    parts = modifier_plu.split(":")
                    if (len(parts) != 4 or parts[1] != plu
                            or any(not index.isascii() or not index.isdecimal()
                                   or len(index) > 9
                                   or (len(index) > 1 and index.startswith("0"))
                                   for index in parts[2:])):
                        raise ValueError("Deliveroo modifier PLU requires catalog reconciliation")
                modifier_qty = modifier.get("quantity", 1)
                if type(modifier_qty) is not int or modifier_qty < 1:
                    raise ValueError("invalid Deliveroo modifier quantity")
                # Modifier prices are part of the immutable financial evidence.
                # Keep the established POS options_json format unchanged.
                modifier_unit_cents = (_required_eur_cents(modifier["unit_price"], "modifier unit price")
                                       if "unit_price" in modifier else None)
                raw_label = modifier.get("name")
                if not isinstance(raw_label, str):
                    raise ValueError("invalid Deliveroo modifier name type")
                label = raw_label.strip()
                if not label or any(ord(ch) < 32 or 127 <= ord(ch) <= 159 for ch in label):
                    raise ValueError("invalid Deliveroo modifier name")
                # Keep the established one-unit JSON contract; record higher
                # quantities explicitly instead of silently losing them.
                option = {"name": label, "plu": modifier_plu}
                if modifier_qty != 1:
                    option["quantity"] = modifier_qty
                options.append(option)
                modifier_unit_prices.append(modifier_unit_cents)
            unit = amount / qty
            normalized.append((plu, name, qty, unit, options, position,
                               reported_unit_cents, modifier_unit_prices))
            total += amount
        if (reported_order_cents is not None
                and Decimal(reported_order_cents) / Decimal("100") != total):
            raise ValueError("Deliveroo order total differs from item totals; financial review required")
        # The external order ID is not sufficient to prove that a redelivery
        # contains the same products, prices and modifiers. Store a fingerprint
        # transactionally with the POS order, not merely with the webhook GUID.
        import hashlib
        # Deliveroo is the sales channel, not the POS fulfillment mode.
        # Customer Collect is pickup; do not label it as a delivery.
        # Unknown nonempty modes require review rather than guessing.
        fulfillment_type = str(order.get("fulfillment_type") or "").strip().casefold()
        if fulfillment_type not in ("", "customer", "deliveroo", "restaurant"):
            raise ValueError("Unrecognized Deliveroo fulfillment type; manual review required")
        fulfillment_source = "EMPORTER" if fulfillment_type == "customer" else "LIVRAISON"
        # Preserve customer details when Deliveroo supplies them; never
        # invent a name, address or telephone number.
        customer = order.get("customer") if isinstance(order.get("customer"), dict) else {}
        delivery = order.get("delivery") if isinstance(order.get("delivery"), dict) else {}
        address_data = delivery.get("address")
        if not isinstance(address_data, dict):
            address_data = {}
        first = str(customer.get("first_name") or customer.get("firstName") or "").strip()
        last = str(customer.get("last_name") or customer.get("lastName") or "").strip()
        # Deliveroo's observed delivery fields are not necessarily
        # nested under customer or delivery.address. Keep legacy
        # fallbacks for older webhook fixtures and omit absent values.
        customer_name = (str(delivery.get("customer_name") or "").strip()
                         or str(customer.get("name") or "").strip()
                         or " ".join(x for x in (first, last) if x)
                         or "Client Deliveroo")
        phone = str(delivery.get("contact_number") or customer.get("phone")
                    or delivery.get("phone") or "").strip()
        # delivery.location may be coordinates, not a postal address.
        # Do not turn its JSON into a fictitious street address.
        address = str(address_data.get("address_line_1") or address_data.get("line_1")
                      or address_data.get("street_address") or "").strip()
        postal_code = str(delivery.get("postcode") or address_data.get("postcode")
                          or address_data.get("postal_code") or "").strip()
        city = str(delivery.get("city") or address_data.get("city") or "").strip()
        # A replay with altered delivery contact must not silently reuse an
        # already-created POS ticket with stale customer details.
        fingerprint_body = {
            "total": str(total),
            "reported_order_cents": reported_order_cents,
            "fulfillment_source": fulfillment_source,
            "delivery_contact": [customer_name, phone, address, postal_code, city],
            "lines": [
                {"plu": plu, "name": name, "qty": qty, "unit": str(unit),
                 "reported_unit_cents": reported_unit_cents,
                 "options": [
                     dict(option, **({"reported_modifier_unit_cents": cents}
                                     if cents is not None else {}))
                     for option, cents in zip(options, modifier_unit_prices)
                 ]}
                for plu, name, qty, unit, options, _, reported_unit_cents,
                    modifier_unit_prices in normalized
            ],
        }
        fingerprint = hashlib.sha256(json.dumps(
            fingerprint_body, sort_keys=True, ensure_ascii=False,
            separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        now = int(time.time() * 1000)
        pos_id = "deliveroo-" + uuid.uuid5(uuid.NAMESPACE_URL, external_id).hex
        with db() as conn:
            with conn.transaction():
                ensure_order_schema(conn)
                conn.execute("LOCK TABLE caisse_orders IN EXCLUSIVE MODE")
                # Preproduction-only metadata: do not rewrite existing orders.
                conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS deliveroo_import_fingerprint TEXT")
                existing = conn.execute(
                    "SELECT id, deliveroo_import_fingerprint FROM caisse_orders WHERE id=%s",
                    (pos_id,)
                ).fetchone()
                if existing:
                    if existing["deliveroo_import_fingerprint"] != fingerprint:
                        # Includes legacy rows without a fingerprint: fail closed.
                        raise ValueError("Deliveroo order ID replay content conflict")
                    return "duplicate"
                num = int(conn.execute("SELECT COALESCE(MAX(num),0)+1 AS n FROM caisse_orders").fetchone()["n"])
                conn.execute("""INSERT INTO caisse_orders
                    (id,num,customer_name,phone,address,postal_code,city,source,sales_channel,payment,status,total,created_at,updated_at,deliveroo_import_fingerprint)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'DELIVEROO','PAYÉ EN LIGNE','À préparer',%s,%s,%s,%s)""",
                    (pos_id,num,customer_name,phone,address,postal_code,city,fulfillment_source,total,now,now,fingerprint))
                for position, (plu,name,qty,unit,options,_,reported_unit_cents,
                               modifier_unit_prices) in enumerate(normalized):
                    conn.execute("""INSERT INTO caisse_order_items
                        (order_id,line_id,product_id,name,qty,unit_price,options_json,options_text,prepared,position)
                        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,FALSE,%s)""",
                        (pos_id,str(position),plu or None,name,qty,unit,
                         json.dumps(options,ensure_ascii=False),
                         " • ".join(o["name"] + (" ×" + str(o["quantity"])
                             if o.get("quantity", 1) != 1 else "") for o in options),position))
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
<p id="state" role="status"></p><div id="result"></div>
<script>
const form=document.getElementById('form'),state=document.getElementById('state'),out=document.getElementById('result');
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
table('Événements order.new',data.events||[],[['Commande Deliveroo','deliveroo_order_id'],['Événement','sequence_guid'],['Reçu (UTC)','received_at_utc'],['Ticket','ticket'],['Articles','item_count'],['Empreinte panier','item_signature'],['Remake présent','remake_details_present'],['Remake type','remake_details_type'],['Champs remake','remake_details_keys'],['Référence Deliveroo','display_id'],['Brand ID','brand_id'],['Création source','order_created_at'],['Statut','order_status'],['Type','order_type'],['Champs commande','order_fields'],['Champs enveloppe','body_fields'],['Champs client (présence)','customer_field_paths'],['Champs livraison (présence)','delivery_field_paths']]);
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
                        FROM caisse_orders WHERE source = 'DELIVEROO'
                        ORDER BY created_at DESC LIMIT 40""")
                    orders = cur.fetchall()
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
