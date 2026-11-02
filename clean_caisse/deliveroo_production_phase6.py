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
from .deliveroo_production_catalog_phase6 import load_plu_map,check_order_plus,normalized_modifiers
from .deliveroo_production_auto_phase6 import AutoProcessor,ensure_jobs

PRODUCTION_APP = 'app_5361da4b-062c-4185-99a5-0fbccc1c4cd4'
REVISION = 'deliveroo-production-review-v2-20261102'
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
        'acceptance_mode_configured': os.environ.get('BECHEFAA_DELIVEROO_ACCEPTANCE_MODE') in ('deliveroo_tablet','auto_hours'),
        'automatic_worker_enabled': os.environ.get('BECHEFAA_DELIVEROO_ACCEPTANCE_MODE') != 'auto_hours' or os.environ.get('BECHEFAA_DELIVEROO_CONFIRM_WORKER_ENABLED') == '1',
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
    if not isinstance(order.get('is_tabletless'),bool):
        raise ValueError('Tablet mode is missing')
    if os.environ.get('BECHEFAA_DELIVEROO_ACCEPTANCE_MODE')=='deliveroo_tablet' and order['is_tabletless']:
        raise ValueError('Tabletless site requires automatic acceptance mode')
    return order


def production_line_amounts(order):
    """Reconcile only explicit fees, without adding fees already included in line totals."""
    try:
        return net_item_cents(order), []
    except ValueError as original:
        delivery=order.get('delivery') if isinstance(order.get('delivery'),dict) else {}
        fees=[]
        for key,value,label in (
            ('delivery',delivery.get('delivery_fee'),'Frais de livraison Deliveroo'),
            ('bag',order.get('bag_fee'),'Frais de sac Deliveroo')):
            amount=cents(value,default=0)
            if amount: fees.append((key,label,amount))
        expected=cents(order.get('total_price'))
        fee_total=sum(fee[2] for fee in fees)
        if not fees or expected is None or fee_total>expected: raise original
        adjusted=dict(order,total_price={'fractional':expected-fee_total,'currency_code':'EUR'})
        return net_item_cents(adjusted), fees


def validate_paid_order(order):
    # Never turn a missing/unknown payment value into a paid order.
    if cents(order.get('cash_due')) != 0:
        raise ValueError('Only explicitly prepaid orders are supported by this draft')
    if order.get('asap') not in (True, False) or not isinstance(order.get('asap'), bool):
        raise ValueError('Missing ASAP/scheduled flag')
    expected = cents(order.get('total_price'))
    if expected is None:
        raise ValueError('Missing order total')
    amounts,fees=production_line_amounts(order)
    if sum(amounts)+sum(fee[2] for fee in fees) != expected:
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


def requires_confirmation(order):
    if order.get('asap') is True or order.get('status')=='confirmed': return False
    # A scheduled-in-the-past order is treated as ASAP only when the payload
    # proves it was already due when it was placed, not merely received late.
    try:
        start=datetime.fromisoformat(str(order.get('start_preparing_at') or '').replace('Z','+00:00'))
        if start.tzinfo is None: return True
        for entry in order.get('status_log') or []:
            if isinstance(entry,dict) and entry.get('status')=='placed':
                placed=datetime.fromisoformat(str(entry.get('at') or '').replace('Z','+00:00'))
                if placed.tzinfo is not None and start<=placed: return False
    except (ValueError,TypeError):
        pass
    return True


def delivery_details(order):
    delivery=order.get('delivery') if isinstance(order.get('delivery'),dict) else {}
    address=delivery.get('address') if isinstance(delivery.get('address'),dict) else {}
    details={}
    for key in ('door_intercom','door_code','intercom','building','entrance','floor','apartment'):
        value=delivery.get(key) or address.get(key)
        if isinstance(value,(str,int)) and not isinstance(value,bool): details[key]=str(value).strip()
    instructions=delivery.get('delivery_notes') or delivery.get('instructions') or delivery.get('note')
    if isinstance(instructions,str) and instructions.strip(): details['instructions']=instructions.strip()
    notes=[order.get('order_notes'),order.get('cutlery_notes')]
    details['notes']=' • '.join(value.strip() for value in notes if isinstance(value,str) and value.strip())
    customer=order.get('customer') if isinstance(order.get('customer'),dict) else {}
    code=delivery.get('contact_access_code') or customer.get('contact_access_code')
    if isinstance(code,str) and code.strip():
        details['notes']=' • '.join(filter(None,[details['notes'],"Code d’accès téléphone Deliveroo : "+code.strip()]))
    return details


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

    @app.get('/api/deliveroo/production-catalog-readiness-phase6')
    def deliveroo_production_catalog_readiness():
        try:
            mapping=load_plu_map(db)
            return jsonify({'ok':True,'read_only':True,'products':sum(1 for value in mapping.values() if value['parent'] is None),'options':sum(1 for value in mapping.values() if value['parent'] is not None),'calls_deliveroo':False})
        except Exception:
            return jsonify({'ok':False,'read_only':True,'error':'Catalogue de production absent ou ambigu'}),409

    @app.get('/api/deliveroo/production-events-phase6')
    def deliveroo_production_events_status():
        with db() as conn:
            exists=conn.execute("SELECT to_regclass('deliveroo_production_events') AS table_name").fetchone()
            if not exists or not exists['table_name']:
                return jsonify({'ok':True,'read_only':True,'revision':REVISION,'events':[]})
            rows=conn.execute('SELECT event,received_at FROM deliveroo_production_events ORDER BY received_at DESC LIMIT 10').fetchall()
        return jsonify({'ok':True,'read_only':True,'revision':REVISION,'events':[{'event':row['event'],'received_at':row['received_at'].isoformat()} for row in rows]})

    @app.before_request
    def protect_external_order_edits():
        if not production_enabled(): return None
        order_id=str((request.view_args or {}).get('order_id') or '')
        if not order_id.startswith('deliveroo-'): return None
        basket_edit=request.method=='PUT' and request.path.rstrip('/')=='/api/orders/'+order_id
        local_cancel=request.method=='POST' and request.path.rstrip('/')=='/api/orders/'+order_id+'/cancel'
        kitchen_write=request.method=='POST' and (request.path.startswith('/api/kitchen/') or 'send-kitchen' in request.path)
        if not (basket_edit or local_cancel or kitchen_write): return None
        with db() as conn:
            row=conn.execute("SELECT sales_channel FROM caisse_orders WHERE id=%s",(order_id,)).fetchone()
        if row and row['sales_channel']=='DELIVEROO' and kitchen_write:
            with db() as conn:
                meta=conn.execute('SELECT confirmed,prepare_at_ms FROM deliveroo_production_meta WHERE pos_id=%s',(order_id,)).fetchone()
            if not meta or not meta['confirmed'] or (meta['prepare_at_ms'] is not None and meta['prepare_at_ms']>int(time.time()*1000)):
                return jsonify({'ok':False,'error':'Commande programmée : attendre sa confirmation et son heure de préparation.'}),409
            return None
        if row and row['sales_channel']=='DELIVEROO':
            return jsonify({'ok':False,'error':'Cette commande est gérée et payée sur Deliveroo. Effectuez sa modification ou son annulation dans Deliveroo.'}),409
        return None

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
            sync_status TEXT, sync_at TIMESTAMPTZ, sync_http_status INTEGER,ack_state TEXT,parent_pos_id TEXT,
            confirm_at TIMESTAMPTZ,acceptance_confirmed BOOLEAN NOT NULL DEFAULT FALSE,accepted_via TEXT)''')
        ensure_jobs(conn)

    def _store_metadata(payload,proof='WEBHOOK'):
        order=payload['body']['order']
        import uuid
        pos_id='deliveroo-'+uuid.uuid5(uuid.NAMESPACE_URL,order['id']).hex
        prepare=None
        if order.get('asap') is False:
            stamp=datetime.fromisoformat(str(order.get('start_preparing_at') or '').replace('Z','+00:00'))
            if stamp.tzinfo is None: raise ValueError('Scheduled timestamp must have a timezone')
            prepare=int(stamp.timestamp()*1000)
        status=str(order.get('status') or '').lower()
        confirm_at=None
        if order.get('confirm_at'):
            confirm_at=datetime.fromisoformat(str(order['confirm_at']).replace('Z','+00:00'))
            if confirm_at.tzinfo is None:raise ValueError('confirm_at must include a timezone')
        if order.get('asap') is False and requires_confirmation(order) and os.environ.get('BECHEFAA_DELIVEROO_ACCEPTANCE_MODE')=='auto_hours' and confirm_at is None:
            raise ValueError('Scheduled automatic confirmation requires confirm_at')
        parent=(order.get('remake_details') or {}).get('parent_order_id')
        parent_pos='deliveroo-'+uuid.uuid5(uuid.NAMESPACE_URL,str(parent)).hex if parent and parent!=order['id'] else None
        with db() as conn:
            with conn.transaction():
                _ensure_metadata(conn)
                conn.execute('''INSERT INTO deliveroo_production_meta(pos_id,order_id,display_id,prepare_at_ms,confirmed,parent_pos_id,confirm_at,acceptance_confirmed,accepted_via)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(pos_id) DO UPDATE SET
                    display_id=EXCLUDED.display_id,prepare_at_ms=CASE WHEN deliveroo_production_meta.confirmed AND NOT EXCLUDED.confirmed THEN deliveroo_production_meta.prepare_at_ms ELSE EXCLUDED.prepare_at_ms END,
                    parent_pos_id=COALESCE(EXCLUDED.parent_pos_id,deliveroo_production_meta.parent_pos_id),
                    confirmed=deliveroo_production_meta.confirmed OR EXCLUDED.confirmed,
                    confirm_at=COALESCE(EXCLUDED.confirm_at,deliveroo_production_meta.confirm_at),
                    acceptance_confirmed=deliveroo_production_meta.acceptance_confirmed OR EXCLUDED.acceptance_confirmed,
                    accepted_via=COALESCE(EXCLUDED.accepted_via,deliveroo_production_meta.accepted_via)''',
                    (pos_id,order['id'],str(order.get('display_id') or ''),prepare,not requires_confirmation(order),parent_pos,confirm_at,status in ('accepted','confirmed'),proof if status in ('accepted','confirmed') else None))

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
        if not isinstance(payload,dict): return False
        order=(payload.get('body') or {}).get('order') or {}
        log=order.get('status_log') or (payload.get('body') or {}).get('status_log') or []
        return isinstance(log,list) and any(isinstance(entry,dict) and entry.get('status')=='accepted' for entry in log)

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
                        sequence_guid=EXCLUDED.sequence_guid
                    WHERE deliveroo_production_events.order_id=EXCLUDED.order_id
                      AND deliveroo_production_events.event=EXCLUDED.event
                      AND deliveroo_production_events.payload=EXCLUDED.payload
                    RETURNING sequence_guid
                """,(
                    str(request.headers.get("X-Deliveroo-Sequence-Guid") or ""),
                    str(payload.get("event") or ""),
                    _extract_order_id(payload),
                    _accepted_in_status_log(payload),
                    json.dumps(payload,ensure_ascii=False),
                ))
                if not cur.fetchone():
                    raise ValueError("Sequence GUID already belongs to a different event")
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
        net_amounts,fees = production_line_amounts(order)
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
            options = normalized_modifiers(modifiers)
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
        for fee_key,fee_label,fee_amount in fees:
            normalized.append(('deliveroo:fee:'+fee_key,fee_label,1,Decimal(fee_amount)/100,[],len(normalized)))
            total+=Decimal(fee_amount)/100
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
                conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS delivery_details JSONB NULL")
                from clean_caisse.order_tax_snapshot_phase31 import _ensure_tax_columns, _fiscal_from_ttc, TAX_RATE
                _ensure_tax_columns(conn)
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
                address = " ".join(str(value).strip() for value in (
                    delivery.get("line1") or address_data.get("address_line_1") or address_data.get("line_1") or address_data.get("street_address"),
                    delivery.get("line2") or address_data.get("line_2")) if isinstance(value,str) and value.strip())
                postal_code = str(delivery.get("postcode") or address_data.get("postcode")
                                  or address_data.get("postal_code") or "").strip()
                city = str(delivery.get("city") or address_data.get("city") or "").strip()
                conn.execute("""INSERT INTO caisse_orders
                    (id,num,customer_name,phone,address,postal_code,city,source,sales_channel,payment,status,total,created_at,updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'DELIVEROO','PAYÉ DELIVEROO','À préparer',%s,%s,%s)""",
                    (pos_id,num,customer_name,phone,address,postal_code,city,pos_source,total,now,now))
                # Use existing tax/fiscal conventions and keep delivery instructions for unchanged receipt renderers.
                details=delivery_details(order)
                conn.execute("UPDATE caisse_orders SET delivery_details=%s::jsonb WHERE id=%s",(json.dumps(details,ensure_ascii=False),pos_id))
                ht,tax,ttc=_fiscal_from_ttc(total)
                conn.execute("UPDATE caisse_orders SET total_ht=%s,tax_rate=%s,tax_amount=%s,total_ttc=%s WHERE id=%s",(ht,TAX_RATE,tax,ttc,pos_id))
                from clean_caisse.fiscal_ticket_phase44 import allocate_fiscal_ticket_number
                allocate_fiscal_ticket_number(conn,ensure_order_schema,pos_id,now)
                # External payment is recorded as DELIVEROO, never as local cash/CB.
                conn.execute("UPDATE caisse_orders SET payment_status='PAYÉE',payment_method='DELIVEROO',paid_amount=%s,paid_at=%s WHERE id=%s", (total,now,pos_id))
                if total > 0:
                    from clean_caisse.payment_transactions_phase44 import record_payment_transaction
                    tx_id=record_payment_transaction(conn,pos_id,'DELIVEROO',total,provider='DELIVEROO',external_reference=external_id,created_by='deliveroo-production-webhook')
                    conn.execute("UPDATE caisse_payment_transactions SET metadata=%s::jsonb WHERE id=%s",(json.dumps({'meal_cards':order.get('meal_cards') or [],'partner_order_total':order.get('partner_order_total'),'source':'DELIVEROO'},ensure_ascii=False),tx_id))
                if scheduled_start_ms is not None:
                    conn.execute(
                        "INSERT INTO deliveroo_kitchen_schedule (order_id, start_preparing_at_ms) VALUES (%s, %s)",
                        (pos_id, scheduled_start_ms))
                for position, (plu,name,qty,unit,options,_) in enumerate(normalized):
                    conn.execute("""INSERT INTO caisse_order_items
                        (order_id,line_id,product_id,name,qty,unit_price,options_json,options_text,prepared,position)
                        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)""",
                        (pos_id,str(position),plu or None,name,qty,unit,
                         json.dumps(options,ensure_ascii=False),
                         " • ".join(o["name"] for o in options),plu.startswith("deliveroo:fee:"),position))
        return "created"
    def validate_automatic_order(order):
        validate_order_context({'body':{'order':order}})
        validate_paid_order(order)
        reason,invalid=check_order_plus(order,load_plu_map(db))
        if invalid:
            return {'status':'rejected','reject_reason':'other','notes':'Articles non reconnus dans la caisse BÉCHÉFAA'}
        return None

    def apply_authoritative_status(order,target,proof):
        if target=='rejected':return
        # Internal business state after PATCH 204. Never save this as a signed webhook
        # and never invent an accepted status-log entry.
        normalized=json.loads(json.dumps(order))
        normalized['status']=target
        business={'event':'order.status_update','body':{'order':normalized}}
        _store_metadata(business,proof=proof)
        result=_bridge_order_new(business)
        if result=='terminal_event_received':return
        if result not in ('created','duplicate'):raise ValueError('Order import not confirmed')
        if proof=='WEBHOOK' and _accepted_in_status_log(business):_sync_status(order['id'],state=target)

    automatic=AutoProcessor(app,db,
        lambda:production_enabled() and os.environ.get('BECHEFAA_DELIVEROO_ACCEPTANCE_MODE')=='auto_hours',
        validate_automatic_order,apply_authoritative_status,_oauth_token,API_HOST,NoRedirect,
        validate_context=lambda order:validate_order_context({'body':{'order':order}}))
    app.config['BECHEFAA_DELIVEROO_AUTO_PROCESSOR']=automatic

    @app.before_request
    def start_deliveroo_automatic_worker():
        automatic.start()

    @app.get('/api/deliveroo/production-jobs-phase6')
    def deliveroo_production_jobs_status():
        with db() as conn:
            exists=conn.execute("SELECT to_regclass('deliveroo_production_jobs') AS table_name").fetchone()
            if not exists or not exists['table_name']:return jsonify({'ok':True,'read_only':True,'jobs':[]})
            rows=conn.execute('SELECT kind,state,COUNT(*) AS count FROM deliveroo_production_jobs GROUP BY kind,state').fetchall()
        return jsonify({'ok':True,'read_only':True,'jobs':[dict(row) for row in rows]})

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
                if os.environ.get('BECHEFAA_DELIVEROO_ACCEPTANCE_MODE')=='auto_hours':automatic.enqueue(order['id'])
                return Response(status=200)
            if cancellation_ready(payload):
                result=_bridge_order_cancelled(payload)
                if result in ('cancelled','already_terminal'):
                    _sync_status(order['id'],state='canceled')
                automatic.observe(order)
                return Response(status=200)
            if status in ('rejected','reject','declined'):
                _bridge_order_rejected(payload)
                automatic.observe(order)
                return Response(status=200)
            if status not in ('accepted','confirmed'): return Response(status=200)
            if not _accepted_in_status_log(payload): return Response(status=503)
            # Metadata precedes the POS insert: scheduled orders cannot leak to kitchen.
            _store_metadata(payload)
            import uuid
            pos_id='deliveroo-'+uuid.uuid5(uuid.NAMESPACE_URL,order['id']).hex
            with db() as conn:
                prior=conn.execute('SELECT payload FROM deliveroo_production_events WHERE order_id=%s',(order['id'],)).fetchall()
                if any(order_status_and_log(row['payload'])[0] in ('canceled','cancelled','rejected') for row in prior):
                    return Response(status=200)
                rejected=conn.execute("SELECT order_id FROM deliveroo_production_jobs WHERE order_id=%s AND kind='decision' AND target_status='rejected' AND http_status=204 AND state IN ('sent','applied')",(order['id'],)).fetchone()
                if rejected:return Response(status=200)
                existing=conn.execute("SELECT id FROM caisse_orders WHERE id=%s AND sales_channel='DELIVEROO'",(pos_id,)).fetchone()
            if not existing:
                fail_reason,invalid_plus=check_order_plus(order,load_plu_map(db))
                if invalid_plus:
                    _sync_status(order['id'],'failed',fail_reason)
                    return Response(status=200)
                result=_bridge_order_new(payload)
                if result == 'terminal_event_received': return Response(status=200)
                if result not in ('created','duplicate'): return Response(status=503)
            _sync_status(order['id'],state=status)
            automatic.observe(order)
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
                rows=conn.execute('''SELECT m.*,o.phone,o.address,o.postal_code,o.city,o.delivery_details,o.payment_status,o.paid_amount
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
                        phone=row['phone'],address=row['address'],postal_code=row['postal_code'],city=row['city'],delivery_details=row['delivery_details'] or {})
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
