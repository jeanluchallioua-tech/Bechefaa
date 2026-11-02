"""Production transfer draft. Off by default; no sandbox fixture mapping or test actions.

Acceptance remains on the Deliveroo tablet. Tabletless auto-acceptance is intentionally
not enabled until the restaurant's opening/calendar policy is specified.
"""
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from .deliveroo_order_pricing_phase6 import cents, net_item_cents
from .deliveroo_order_status_phase6 import cancellation_ready, order_status_and_log

PRODUCTION_APP = 'app_5361da4b-062c-4185-99a5-0fbccc1c4cd4'
REVISION = 'deliveroo-production-draft-v1-20261102'
API_HOST = 'https://api.developers.deliveroo.com'
AUTH_HOST = 'https://auth.developers.deliveroo.com'


def readiness():
    """Local configuration only. Never exchanges tokens or writes a database."""
    checks = {
        'production_app': os.environ.get('CC_APP_ID') == PRODUCTION_APP,
        'enabled': os.environ.get('BECHEFAA_DELIVEROO_PRODUCTION_ENABLED') == '1',
        'api_host': os.environ.get('BECHEFAA_DELIVEROO_API_URL', '').rstrip('/') == API_HOST,
        'auth_host': os.environ.get('BECHEFAA_DELIVEROO_AUTH_URL', '').rstrip('/') == AUTH_HOST,
        'client_id_present': bool(os.environ.get('BECHEFAA_DELIVEROO_CLIENT_ID', '').strip()),
        'client_secret_present': bool(os.environ.get('BECHEFAA_DELIVEROO_CLIENT_SECRET', '').strip()),
        'webhook_secret_present': bool(os.environ.get('BECHEFAA_DELIVEROO_WEBHOOK_SECRET', '').strip()),
        'production_site_set': bool(os.environ.get('BECHEFAA_DELIVEROO_PRODUCTION_SITE_ID', '').strip()) and os.environ.get('BECHEFAA_DELIVEROO_PRODUCTION_SITE_ID', '').strip() != '101',
        'production_brand_set': bool(os.environ.get('BECHEFAA_DELIVEROO_PRODUCTION_BRAND_ID', '').strip()) and os.environ.get('BECHEFAA_DELIVEROO_PRODUCTION_BRAND_ID', '').strip() != 'bceaa87a-74db-434e-b548-6da7e7de67a6',
        'tablet_acceptance_configured': os.environ.get('BECHEFAA_DELIVEROO_ACCEPTANCE_MODE') == 'deliveroo_tablet',
    }
    return {'ok': all(checks.values()), 'revision': REVISION, 'checks': checks,
            'calls_deliveroo': False, 'writes_database': False,
            'note': 'Checks presence only; does not verify credentials or secret against Deliveroo'}


def production_enabled():
    return readiness()['ok']


def signature_valid(secret, guid, raw, supplied):
    return bool(secret and guid and isinstance(supplied,str) and len(supplied)==64
        and all(c in '0123456789abcdefABCDEF' for c in supplied) and hmac.compare_digest(
        hmac.new(secret.encode(), guid.encode()+b' '+raw, hashlib.sha256).hexdigest(), supplied.lower()))


def validate_order_context(payload):
    order = ((payload.get('body') or {}).get('order') or {})
    if str(order.get('location_id') or '') != os.environ.get('BECHEFAA_DELIVEROO_PRODUCTION_SITE_ID', '').strip():
        raise ValueError('Unexpected production site')
    if str(order.get('brand_id') or '') != os.environ.get('BECHEFAA_DELIVEROO_PRODUCTION_BRAND_ID', '').strip():
        raise ValueError('Unexpected production brand')
    if not str(order.get('id') or '').startswith('fr:'):
        raise ValueError('Invalid French order ID')
    if order.get('is_tabletless') is not False:
        raise ValueError('Tabletless acceptance policy has not been configured')
    return order


def validate_paid_order(order):
    # Never turn a missing/unknown payment value into a paid order.
    if cents(order.get('cash_due')) != 0:
        raise ValueError('Only explicitly prepaid orders are supported by this draft')
    if order.get('asap') not in (True, False) or not isinstance(order.get('asap'), bool):
        raise ValueError('Missing ASAP/scheduled flag')
    expected = cents(order.get('total_price'))
    if expected is None:
        raise ValueError('Missing order total')
    if sum(net_item_cents(order)) != expected:
        raise ValueError('Line totals do not reconcile')
    for item in order['items']:
        if not isinstance(item.get('quantity'), int) or isinstance(item['quantity'], bool) or item['quantity'] <= 0:
            raise ValueError('Invalid item quantity')


def missing_plu_paths(payload):
    """Only missing identifiers; sandbox English names are never production rules."""
    order = (payload.get('body') or {}).get('order') or {}
    paths = []
    for i, item in enumerate(order.get('items') or []):
        if not isinstance(item, dict) or not str(item.get('pos_item_id') or '').strip(): paths.append('items[%s]' % i)
        if isinstance(item, dict):
            for j, modifier in enumerate(item.get('modifiers') or []):
                if not isinstance(modifier, dict) or not str(modifier.get('pos_item_id') or '').strip(): paths.append('items[%s].modifiers[%s]' % (i,j))
    return paths


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def register_deliveroo_production_phase6(app, db):
    from flask import jsonify, request, Response
    if os.environ.get('CC_APP_ID') != PRODUCTION_APP:
        return

    @app.get('/api/deliveroo/production-readiness-phase6')
    def deliveroo_production_readiness():
        # The existing production PIN middleware protects this route.
        return jsonify(readiness())

    def _oauth_token():
        if not production_enabled(): raise ValueError('Production disabled')
        body=urllib.parse.urlencode({'client_id':os.environ['BECHEFAA_DELIVEROO_CLIENT_ID'],
            'client_secret':os.environ['BECHEFAA_DELIVEROO_CLIENT_SECRET'],'grant_type':'client_credentials'}).encode()
        req=urllib.request.Request(AUTH_HOST+'/oauth2/token',data=body,method='POST',headers={
            'Content-Type':'application/x-www-form-urlencoded; charset=utf-8','Accept':'application/json',
            'User-Agent':'Bechefaa-Deliveroo-Integration/1.0'})
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=12) as response:
            token=json.loads(response.read()).get('access_token')
        if not token: raise ValueError('OAuth token missing')
        return str(token)

    def _ensure_metadata(conn):
        conn.execute('''CREATE TABLE IF NOT EXISTS deliveroo_production_meta (
            pos_id TEXT PRIMARY KEY, order_id TEXT NOT NULL UNIQUE, display_id TEXT NOT NULL,
            prepare_at_ms BIGINT, confirmed BOOLEAN NOT NULL DEFAULT FALSE,
            sync_status TEXT, sync_at TIMESTAMPTZ, sync_http_status INTEGER,ack_state TEXT,parent_pos_id TEXT)''')

    def _store_metadata(payload):
        order=payload['body']['order']
        import uuid
        pos_id='deliveroo-'+uuid.uuid5(uuid.NAMESPACE_URL,order['id']).hex
        prepare=None
        if order.get('asap') is False:
            stamp=datetime.fromisoformat(str(order.get('start_preparing_at') or '').replace('Z','+00:00'))
            if stamp.tzinfo is None: raise ValueError('Scheduled timestamp must have a timezone')
            prepare=int(stamp.timestamp()*1000)
        status=str(order.get('status') or '').lower()
        parent=(order.get('remake_details') or {}).get('parent_order_id')
        parent_pos='deliveroo-'+uuid.uuid5(uuid.NAMESPACE_URL,str(parent)).hex if parent and parent!=order['id'] else None
        with db() as conn:
            with conn.transaction():
                _ensure_metadata(conn)
                conn.execute('''INSERT INTO deliveroo_production_meta(pos_id,order_id,display_id,prepare_at_ms,confirmed,parent_pos_id)
                    VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(pos_id) DO UPDATE SET
                    display_id=EXCLUDED.display_id,prepare_at_ms=EXCLUDED.prepare_at_ms,
                    parent_pos_id=COALESCE(EXCLUDED.parent_pos_id,deliveroo_production_meta.parent_pos_id),
                    confirmed=deliveroo_production_meta.confirmed OR EXCLUDED.confirmed''',
                    (pos_id,order['id'],str(order.get('display_id') or ''),prepare,status=='confirmed' or order.get('asap') is True,parent_pos))

    def _sync_status(order_id, status='succeeded', reason=None, state='accepted'):
        # Serialize final acknowledgements and throttle per order. No blind retries.
        with db() as conn:
            with conn.transaction():
                _ensure_metadata(conn)
                conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('deliveroo-sync:'+order_id,))
                row=conn.execute('SELECT sync_status,sync_at,ack_state FROM deliveroo_production_meta WHERE order_id=%s FOR UPDATE',(order_id,)).fetchone()
                if row and row['sync_status']==status and row['ack_state']==state: return
                if row and row['sync_at'] and (datetime.now(timezone.utc)-row['sync_at']).total_seconds()<10:
                    raise ValueError('Wait for the per-order sync interval')
                data={'status':status,'reason':reason,'notes':'BÉCHÉFAA production',
                      'occurred_at':datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')}
                req=urllib.request.Request(API_HOST+'/order/v1/orders/'+urllib.parse.quote(order_id,safe=':')+'/sync_status',
                    data=json.dumps(data).encode(),method='POST',headers={'Authorization':'Bearer '+_oauth_token(),
                    'Content-Type':'application/json','Accept':'application/json','User-Agent':'Bechefaa-Deliveroo-Integration/1.0'})
                with urllib.request.build_opener(NoRedirect()).open(req,timeout=12) as response:
                    if not 200<=response.status<300: raise ValueError('Sync not confirmed')
                    conn.execute('UPDATE deliveroo_production_meta SET sync_status=%s,sync_at=NOW(),sync_http_status=%s,ack_state=%s WHERE order_id=%s',(status,response.status,state,order_id))

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
                cur.execute("""CREATE TABLE IF NOT EXISTS deliveroo_production_events (
                    sequence_guid TEXT PRIMARY KEY,
                    event TEXT,
                    order_id TEXT,
                    accepted_in_status_log BOOLEAN NOT NULL DEFAULT FALSE,
                    payload JSONB NOT NULL,
                    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )""")
                cur.execute("""
                    INSERT INTO deliveroo_production_events
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
        if not production_enabled():
            raise ValueError("Production bridge disabled or unconfigured")
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

    def _bridge_order_cancelled(payload):
        """Apply a confirmed cancellation only to the opt-in preproduction POS."""
        if not production_enabled():
            raise ValueError("Production bridge disabled or unconfigured")
        if not cancellation_ready(payload):
            return "not_cancelled"
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
                    ("Annulée", int(time.time() * 1000), pos_id),
                )
        return "cancelled"

    def _bridge_order_new(payload):
        """Import an order.new into the isolated preproduction POS, once per Deliveroo ID.

        Opt-in only: no production writes and no kitchen printing until validated.
        """
        if not production_enabled():
            raise ValueError("Production bridge disabled or unconfigured")
        body = payload.get("body") if isinstance(payload, dict) else None
        order = body.get("order") if isinstance(body, dict) else None
        if not isinstance(order, dict):
            raise ValueError("order.new missing body.order")
        external_id = str(order.get("id") or order.get("order_id") or "").strip()
        if not external_id:
            raise ValueError("order.new missing order id")
        # A placed order must not reach preparation before Deliveroo acceptance.
        if str(order.get("status") or "").strip().lower() == "placed":
            return "awaiting_acceptance"
        validate_paid_order(order)
        items = order.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("order.new missing items")
        if missing_plu_paths(payload):
            return "missing_plu"
        from decimal import Decimal
        import time
        import uuid
        from clean_caisse.app import ensure_order_schema
        normalized = []
        total = Decimal("0")
        net_amounts = net_item_cents(order)
        for position, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError("invalid order item")
            name = str(item.get("name") or "").strip()
            qty = int(item.get("quantity") or 0)
            price = item.get("total_price")
            fractional = price.get("fractional") if isinstance(price, dict) else None
            if not name or qty <= 0 or fractional is None:
                raise ValueError("order item missing name/quantity/total_price")
            amount = Decimal(net_amounts[position]) / Decimal("100")
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
            # unit_price has two decimal places in the POS schema. Split only
            # the rounding remainder so that qty * unit_price stays exact.
            unit_cents, extra_units = divmod(net_amounts[position], qty)
            if qty - extra_units:
                normalized.append((str(item.get("pos_item_id") or ""), name, qty - extra_units,
                                   Decimal(unit_cents) / 100, options, position))
            if extra_units:
                normalized.append((str(item.get("pos_item_id") or ""), name, extra_units,
                                   Decimal(unit_cents + 1) / 100, options, position))
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
                from clean_caisse.payment_core_phase41 import _ensure_payment_schema
                _ensure_payment_schema(conn, ensure_order_schema)
                conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS sales_channel TEXT NOT NULL DEFAULT 'RESTO'")
                conn.execute("""CREATE TABLE IF NOT EXISTS deliveroo_kitchen_schedule (
                    order_id TEXT PRIMARY KEY,
                    start_preparing_at_ms BIGINT NOT NULL
                )""")
                conn.execute("LOCK TABLE caisse_orders IN EXCLUSIVE MODE")
                existing = conn.execute("SELECT id FROM caisse_orders WHERE id=%s", (pos_id,)).fetchone()
                if existing:
                    return "duplicate"
                # Never resurrect a terminal order if its updates arrived out of order.
                prior_events = conn.execute(
                    "SELECT payload FROM deliveroo_production_events WHERE order_id=%s",
                    (external_id,),
                ).fetchall()
                for prior in prior_events:
                    prior_payload = prior.get("payload") or {}
                    if isinstance(prior_payload, str):
                        prior_payload = json.loads(prior_payload)
                    prior_status, _ = order_status_and_log(prior_payload)
                    if prior_status in {"canceled", "cancelled", "rejected", "reject", "declined"}:
                        return "terminal_event_received"
                num = int(conn.execute("SELECT COALESCE(MAX(num),0)+1 AS n FROM caisse_orders").fetchone()["n"])
                # Preserve delivery and customer contact data for POS history/preview.
                # Customer Collect is collected at the restaurant, not delivered.
                fulfillment_type = str(order.get("fulfillment_type") or "").strip().lower()
                pos_source = "LIVRAISON"
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
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'DELIVEROO','PAYÉ DELIVEROO','À préparer',%s,%s,%s)""",
                    (pos_id,num,customer_name,phone,address,postal_code,city,pos_source,total,now,now))
                # External payment is recorded as DELIVEROO, never as local cash/CB.
                conn.execute("UPDATE caisse_orders SET payment_status='PAYÉE',payment_method='DELIVEROO',paid_amount=%s,paid_at=%s WHERE id=%s", (total,now,pos_id))
                if total > 0:
                    from clean_caisse.payment_transactions_phase44 import record_payment_transaction
                    record_payment_transaction(conn,pos_id,'DELIVEROO',total,provider='DELIVEROO',external_reference=external_id,created_by='deliveroo-production-webhook')
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
    def receive(kind):
        if not production_enabled(): return Response(status=503)
        raw=request.get_data(cache=True)
        guid=request.headers.get('X-Deliveroo-Sequence-Guid','').strip()
        signature=request.headers.get('X-Deliveroo-Hmac-Sha256','').strip()
        if not signature_valid(os.environ['BECHEFAA_DELIVEROO_WEBHOOK_SECRET'].strip(),guid,raw,signature):
            return Response(status=401)
        payload=request.get_json(silent=True)
        if not isinstance(payload,dict): return Response(status=400)
        if kind=='menu':
            # Existing menu receiver verifies and records the signed menu event.
            return old_menu()
        try:
            order=validate_order_context(payload)
            if payload.get('event') not in ('order.new','order.status_update'):
                return Response(status=400)
            _persist_order_event(payload)
            status=str(order.get('status') or '').lower()
            if status=='placed':
                _store_metadata(payload)
                return Response(status=200)
            if cancellation_ready(payload):
                result=_bridge_order_cancelled(payload)
                if result in ('cancelled','already_terminal'):
                    _sync_status(order['id'],state='canceled')
                return Response(status=200)
            if status in ('rejected','reject','declined'):
                _bridge_order_rejected(payload)
                return Response(status=200)
            if status not in ('accepted','confirmed'): return Response(status=200)
            if not _accepted_in_status_log(payload): return Response(status=503)
            # Metadata precedes the POS insert: scheduled orders cannot leak to kitchen.
            _store_metadata(payload)
            if missing_plu_paths(payload):
                _sync_status(order['id'],'failed','pos_item_id_not_found')
                return Response(status=200)
            result=_bridge_order_new(payload)
            if result == 'terminal_event_received': return Response(status=200)
            if result not in ('created','duplicate'): return Response(status=503)
            _sync_status(order['id'],state=status)
            return Response(status=200)
        except Exception:
            # Do not print payloads, phone numbers, credentials or response bodies.
            app.logger.error('Deliveroo production webhook failed; event remains retryable')
            return Response(status=503)

    old_menu=app.view_functions['deliveroo_menu_webhook_phase6']
    app.view_functions['deliveroo_orders_webhook_phase6']=lambda:receive('orders')
    app.view_functions['deliveroo_menu_webhook_phase6']=lambda:receive('menu')

    original_kitchen=app.view_functions['kitchen_orders']
    def production_kitchen():
        if not production_enabled(): return original_kitchen()
        try:
            from clean_caisse.app import order_payload
            with db() as conn:
                exists=conn.execute("SELECT to_regclass('deliveroo_production_meta') AS table_name").fetchone()
                if not exists or not exists['table_name']: return original_kitchen()
                rows=conn.execute('''SELECT o.*,
                    CASE WHEN m.prepare_at_ms IS NOT NULL THEN GREATEST(o.updated_at,m.prepare_at_ms)
                         ELSE o.updated_at END AS updated_at
                    FROM caisse_orders o LEFT JOIN deliveroo_production_meta m ON m.pos_id=o.id
                    WHERE o.status IN ('À préparer','En préparation')
                      AND NOT EXISTS(SELECT 1 FROM deliveroo_production_meta child JOIN caisse_orders replacement ON replacement.id=child.pos_id WHERE child.parent_pos_id=o.id)
                      AND (m.pos_id IS NULL OR (m.confirmed AND (m.prepare_at_ms IS NULL OR m.prepare_at_ms <= %s)))
                    ORDER BY o.updated_at ASC,o.num ASC LIMIT 100''',(int(time.time()*1000),)).fetchall()
                orders=[order_payload(conn,row) for row in rows]
            return jsonify({'ok':True,'orders':orders,'count':len(orders)})
        except Exception:
            app.logger.error('Deliveroo production kitchen read failed')
            return jsonify({'ok':False,'error':'Lecture cuisine indisponible'}),503
    app.view_functions['kitchen_orders']=production_kitchen

    @app.after_request
    def production_order_labels(response):
        if not production_enabled() or response.status_code!=200 or not response.is_json:
            return response
        if not request.path.startswith(('/api/orders','/api/kitchen','/api/history','/api/order/')):
            return response
        data=response.get_json(silent=True)
        if not isinstance(data,dict): return response
        orders=data.get('orders')
        if not isinstance(orders,list): orders=[data['order']] if isinstance(data.get('order'),dict) else []
        ids=[str(o.get('id') or '') for o in orders if isinstance(o,dict) and str(o.get('id') or '').startswith('deliveroo-')]
        if not ids: return response
        try:
            with db() as conn:
                rows=conn.execute('''SELECT m.*,o.phone,o.address,o.postal_code,o.city,o.payment_status,o.paid_amount
                    FROM deliveroo_production_meta m JOIN caisse_orders o ON o.id=m.pos_id
                    WHERE m.pos_id=ANY(%s)''',(ids,)).fetchall()
            by_id={r['pos_id']:r for r in rows}
            now=int(time.time()*1000)
            visible=[]
            for order in orders:
                row=by_id.get(str(order.get('id') or ''))
                if row:
                    waiting=not row['confirmed'] or (row['prepare_at_ms'] is not None and row['prepare_at_ms']>now)
                    if waiting and request.path.startswith('/api/kitchen'): continue
                    order.update(sales_channel='DELIVEROO',platform='Deliveroo',source='LIVRAISON',ticket_type='Livraison',
                        service_mode='Livraison',platform_reference=row['display_id'],payment='PAYÉ DELIVEROO',
                        payment_label='PAYÉ DELIVEROO',payment_status=row['payment_status'],paid_amount=float(row['paid_amount']),
                        phone=row['phone'],address=row['address'],postal_code=row['postal_code'],city=row['city'])
                    if waiting and order.get('status') in ('À préparer','En préparation'):
                        order['status']='Programmée'
                visible.append(order)
            if isinstance(data.get('orders'),list): data.update(orders=visible,count=len(visible))
            response.set_data(json.dumps(data,ensure_ascii=False))
            return response
        except Exception:
            app.logger.error('Deliveroo production order enrichment failed')
            response=jsonify({'ok':False,'error':'Lecture Deliveroo indisponible'}); response.status_code=503; return response

    @app.after_request
    def production_pos_notice(response):
        if (not production_enabled() or request.path!='/pos' or response.status_code!=200
                or response.mimetype!='text/html'): return response
        from pathlib import Path
        script=Path(__file__).with_name('static').joinpath('deliveroo-notice-production.js').read_text()
        html=response.get_data(as_text=True)
        addon='''<style>#deliveroo-alert{display:none;background:#00CCBC;color:#002F2C;padding:15px;font-weight:700;border-radius:8px}#deliveroo-alert.visible{display:block}</style><div id="deliveroo-alert" role="status" aria-live="polite"></div><script>'''+script+'</script>'
        if 'id="deliveroo-alert"' not in html:
            response.set_data(html.replace('</body>',addon+'</body>',1))
        return response
