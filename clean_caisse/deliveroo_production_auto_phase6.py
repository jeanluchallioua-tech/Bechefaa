"""Durable automatic acceptance/confirmation, driven by BÉCHÉFAA's shared hours.

One explicit PATCH per recorded attempt. Ambiguous network outcomes pause until a
signed webhook resolves them. The receiver stores authentic events separately.
"""
import copy
import json
import threading
from datetime import datetime, timezone
from urllib.error import HTTPError
import urllib.parse
import urllib.request


def ensure_jobs(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS deliveroo_production_jobs (
        order_id TEXT NOT NULL,kind TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'pending',
        target_status TEXT,attempted_at TIMESTAMPTZ,retry_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        http_status INTEGER,error_type TEXT,updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY(order_id,kind))''')


def decision_for_order(order,state_fn,now=None):
    """Future preorders are allowed when their preparation slot is open."""
    if not callable(state_fn): raise ValueError('Shared opening-hours engine unavailable')
    now=now or datetime.now(timezone.utc)
    target=now
    if order.get('asap') is False:
        target=datetime.fromisoformat(str(order.get('start_preparing_at') or '').replace('Z','+00:00'))
        if target.tzinfo is None: raise ValueError('Scheduled time must include a timezone')
        target=max(target,now)
    state=state_fn(now=target,channel='deliveroo',strict=True)
    if not isinstance(state,dict) or not isinstance(state.get('open'),bool):
        raise ValueError('Unusable opening-hours decision')
    return {'status':'accepted'} if state['open'] else {
        'status':'rejected','reject_reason':'closing_early',
        'notes':'Restaurant fermé selon les horaires et le calendrier BÉCHÉFAA'}


class AutoProcessor:
    def __init__(self,app,db,enabled,validate,apply,oauth,api_host,no_redirect,validate_context=None):
        self.app,self.db,self.enabled=app,db,enabled
        self.validate,self.apply,self.oauth=validate,apply,oauth
        self.api_host,self.no_redirect=api_host,no_redirect
        self.validate_context=validate_context or (lambda order:None)
        self.wake=threading.Event();self.lock=threading.Lock();self.thread=None

    def start(self):
        if getattr(self.app,'testing',False) or not self.enabled(): return
        with self.lock:
            if self.thread and self.thread.is_alive(): return
            self.thread=threading.Thread(target=self._loop,name='deliveroo-auto',daemon=True)
            self.thread.start()

    def _loop(self):
        while True:
            try:
                with self.app.app_context(): self.tick()
            except Exception:
                self.app.logger.error('Deliveroo automatic worker requires investigation')
            self.wake.wait(5);self.wake.clear()

    def enqueue(self,order_id,kind='decision'):
        with self.db() as conn:
            with conn.transaction():
                ensure_jobs(conn)
                created=conn.execute('INSERT INTO deliveroo_production_jobs(order_id,kind) VALUES(%s,%s) ON CONFLICT DO NOTHING RETURNING order_id',(order_id,kind)).fetchone()
        if created:self.wake.set()

    def observe(self,order):
        status=str(order.get('status') or '').lower()
        if status not in ('accepted','confirmed','rejected','canceled','cancelled'): return
        with self.db() as conn:
            exists=conn.execute("SELECT to_regclass('deliveroo_production_jobs') AS table_name").fetchone()
            if not exists or not exists['table_name']:return
            if status in ('canceled','cancelled','rejected'):
                conn.execute("UPDATE deliveroo_production_jobs SET state='terminal',updated_at=NOW() WHERE order_id=%s",(order['id'],))
            else:
                kinds=['decision']+(['confirmation'] if status=='confirmed' else [])
                conn.execute("UPDATE deliveroo_production_jobs SET state='applied',error_type=NULL,updated_at=NOW() WHERE order_id=%s AND kind=ANY(%s)",(order['id'],kinds))

    def _order(self,order_id):
        with self.db() as conn:
            rows=conn.execute('SELECT payload FROM deliveroo_production_events WHERE order_id=%s ORDER BY received_at DESC',(order_id,)).fetchall()
        orders=[row['payload']['body']['order'] for row in rows]
        for statuses in [('canceled','cancelled','rejected'),('confirmed',),('accepted',),('placed',)]:
            match=next((order for order in orders if str(order.get('status') or '').lower() in statuses),None)
            if match:return match
        raise ValueError('Authentic source order not available')

    def _mark(self,job,state,target=None,http_status=None,error=None,delay=0):
        with self.db() as conn:
            conn.execute('''UPDATE deliveroo_production_jobs SET state=%s,
                target_status=COALESCE(%s,target_status),http_status=COALESCE(%s,http_status),
                error_type=%s,retry_at=NOW()+%s*INTERVAL '1 second',updated_at=NOW()
                WHERE order_id=%s AND kind=%s''',(state,target,http_status,error,delay,job['order_id'],job['kind']))

    def _run(self,job):
        order=self._order(job['order_id'])
        self.validate_context(order)
        current=str(order.get('status') or '').lower()
        if current in ('canceled','cancelled','rejected'):
            self._mark(job,'terminal');return
        if job['kind']=='decision' and current in ('accepted','confirmed'):
            self.apply(order,current,'WEBHOOK');self._mark(job,'applied',current);return
        if job['kind']=='confirmation' and current=='confirmed':
            self.apply(order,current,'WEBHOOK');self._mark(job,'applied','confirmed');return
        if job['state']=='sent':
            self.apply(order,job['target_status'],'PATCH_204');self._mark(job,'applied');return
        state_fn=self.app.config.get('BECHEFAA_ORDER_HOURS_STATE')
        decision=decision_for_order(order,state_fn)
        if job['kind']=='confirmation':
            with self.db() as conn:
                meta=conn.execute('SELECT confirm_at,acceptance_confirmed FROM deliveroo_production_meta WHERE order_id=%s',(order['id'],)).fetchone()
            if not meta or not meta['acceptance_confirmed'] or meta['confirm_at'] is None:
                self._mark(job,'blocked',error='confirmation_prerequisite_missing');return
            remaining=(meta['confirm_at']-datetime.now(timezone.utc)).total_seconds()
            if remaining>0:
                self._mark(job,'pending',error='confirmation_not_due',delay=int(remaining)+1);return
            if decision['status']!='accepted':
                self._mark(job,'blocked',error='preparation_slot_closed');return
            decision={'status':'confirmed'}
        else:
            invalid=self.validate(order)
            if decision['status']=='accepted' and invalid:decision=invalid
        try:
            token=self.oauth()
        except Exception as exc:
            self._mark(job,'pending',error='oauth_'+type(exc).__name__,delay=30);return
        # Recheck after OAuth, so waiting for a token cannot cross a cutoff unnoticed.
        refreshed=decision_for_order(order,state_fn)
        if job['kind']=='decision':decision=invalid if refreshed['status']=='accepted' and invalid else refreshed
        elif refreshed['status']!='accepted':
            self._mark(job,'blocked',error='preparation_slot_closed');return
        if not self.enabled():return
        latest=self._order(job['order_id'])
        latest_status=str(latest.get('status') or '').lower()
        if latest_status in ('canceled','cancelled','rejected'):
            self._mark(job,'terminal');return
        if (job['kind']=='decision' and latest_status in ('accepted','confirmed')) or (job['kind']=='confirmation' and latest_status=='confirmed'):
            self.apply(latest,latest_status,'WEBHOOK');self._mark(job,'applied',latest_status);return
        with self.db() as conn:
            # Persist before the external action. A process crash cannot erase the attempt.
            conn.execute("UPDATE deliveroo_production_jobs SET state='sending',target_status=%s,attempted_at=NOW(),updated_at=NOW() WHERE order_id=%s AND kind=%s",(decision['status'],job['order_id'],job['kind']))
        req=urllib.request.Request(self.api_host+'/order/v1/orders/'+urllib.parse.quote(order['id'],safe=':'),
            data=json.dumps(decision,ensure_ascii=False).encode(),method='PATCH',headers={
                'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'application/json',
                'User-Agent':'Bechefaa-Deliveroo-Integration/1.0'})
        try:
            with urllib.request.build_opener(self.no_redirect()).open(req,timeout=12) as response:
                status=int(response.status);response.read()
            if status!=204:
                self._mark(job,'uncertain',decision['status'],status,'unexpected_http_status');return
        except HTTPError as exc:
            if exc.code in (429,503):
                retry=(exc.headers or {}).get('Retry-After','30')
                delay=max(30,min(300,int(retry))) if str(retry).isdigit() else 30
                self._mark(job,'pending',decision['status'],exc.code,'http_retryable',delay);return
            self._mark(job,'uncertain' if exc.code==409 else 'failed',decision['status'],exc.code,'http_error');return
        except Exception as exc:
            self._mark(job,'uncertain',decision['status'],error=type(exc).__name__);return
        self._mark(job,'sent',decision['status'],204)
        self.apply(order,decision['status'],'PATCH_204')
        self._mark(job,'applied')

    def tick(self):
        if not self.enabled():return 0
        with self.db() as leader:
            acquired=leader.execute("SELECT pg_try_advisory_lock(hashtext('deliveroo-production-worker')) AS acquired").fetchone()['acquired']
            leader.commit()
            if not acquired:return 0
            try:
                exists=leader.execute("SELECT to_regclass('deliveroo_production_jobs') AS table_name").fetchone()
                leader.commit()
                if not exists or not exists['table_name']:return 0
                with self.db() as conn:
                    due=conn.execute('''SELECT order_id FROM deliveroo_production_meta
                        WHERE acceptance_confirmed AND NOT confirmed AND confirm_at IS NOT NULL AND confirm_at<=NOW()''').fetchall()
                for row in due:self.enqueue(row['order_id'],'confirmation')
                with self.db() as conn:
                    jobs=conn.execute("SELECT * FROM deliveroo_production_jobs WHERE state IN ('pending','sent') AND retry_at<=NOW() ORDER BY updated_at LIMIT 20").fetchall()
                processed=0
                for job in jobs:
                    if not self.enabled():break
                    try:self._run(job);processed+=1
                    except Exception as exc:
                        # Validation/data errors never become an automatic accept/reject.
                        with self.db() as conn:
                            current=conn.execute('SELECT state FROM deliveroo_production_jobs WHERE order_id=%s AND kind=%s',(job['order_id'],job['kind'])).fetchone()
                        next_state='sent' if current and current['state']=='sent' else 'uncertain' if current and current['state']=='sending' else 'pending'
                        self._mark(job,next_state,error=type(exc).__name__,delay=30)
                return processed
            finally:
                leader.execute("SELECT pg_advisory_unlock(hashtext('deliveroo-production-worker'))");leader.commit()
