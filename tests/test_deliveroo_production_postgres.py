"""Real Flask + PostgreSQL contract tests; only a local disposable deliveroo_ci DB.

Production schema/order serializer are loaded from their actual function definitions
without booting the full restaurant app or reading customer/catalog fixtures.
No real Deliveroo, Clever Cloud, payment or printing endpoint is contacted.
"""
import ast
import copy
import hashlib
import hmac
import json
import os
import sys
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone,timedelta
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

URL=os.environ.get('DELIVEROO_TEST_DATABASE_URL')

@unittest.skipUnless(URL, 'Set DELIVEROO_TEST_DATABASE_URL to an isolated local deliveroo_ci database')
class ProductionPostgresTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  import psycopg
  from psycopg.rows import dict_row
  from psycopg.conninfo import conninfo_to_dict
  info=conninfo_to_dict(URL)
  if info.get('host') not in ('localhost','127.0.0.1') or info.get('dbname')!='deliveroo_ci':
   raise RuntimeError('Refusing a database other than local deliveroo_ci')
  cls.connect=lambda self:psycopg.connect(URL,row_factory=dict_row)
  source=ast.parse(Path('clean_caisse/app.py').read_text())
  names={'ensure_order_schema','ticket_type','order_payload'}
  definitions=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in names]
  cls.app_module=ModuleType('clean_caisse.app');cls.app_module.__dict__['json']=json
  exec(compile(ast.Module(body=definitions,type_ignores=[]),'<actual-production-schema>','exec'),cls.app_module.__dict__)

 def setUp(self):
  from flask import Flask,jsonify,Response
  from test_deliveroo_production import ENV
  self.env=patch.dict(os.environ,ENV,clear=False);self.env.start();self.addCleanup(self.env.stop)
  self.module_patch=patch.dict(sys.modules,{'clean_caisse.app':self.app_module});self.module_patch.start();self.addCleanup(self.module_patch.stop)
  # Only schemas created by this test are cleared. URL guard in setUpClass is mandatory.
  with self.connect() as conn:
   conn.execute('DROP SCHEMA public CASCADE');conn.execute('CREATE SCHEMA public')
   self.app_module.ensure_order_schema(conn)
   conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS sales_channel TEXT NOT NULL DEFAULT 'RESTO'")
   conn.execute('ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS cancellation_hidden BOOLEAN NOT NULL DEFAULT FALSE')
  self.app=Flask(__name__);self.app.config['TESTING']=True
  @self.app.post('/api/deliveroo/webhooks/orders')
  def deliveroo_orders_webhook_phase6():return Response(status=200)
  @self.app.post('/api/deliveroo/webhooks/menu')
  def deliveroo_menu_webhook_phase6():return Response(status=200)
  @self.app.get('/api/kitchen/orders')
  def kitchen_orders():
   with self.connect() as conn:
    rows=conn.execute("SELECT * FROM caisse_orders WHERE status IN ('À préparer','En préparation')").fetchall()
    return jsonify(ok=True,orders=[self.app_module.order_payload(conn,r) for r in rows])
  @self.app.get('/api/orders/history')
  def history():
   with self.connect() as conn:
    rows=conn.execute('SELECT * FROM caisse_orders').fetchall()
    return jsonify(ok=True,orders=[self.app_module.order_payload(conn,r) for r in rows])
  @self.app.get('/pos')
  def pos():return '<html><body>POS test shell</body></html>'
  from clean_caisse.deliveroo_production_phase6 import register_deliveroo_production_phase6
  register_deliveroo_production_phase6(self.app,lambda:self.connect())
  self.http=[];self.sync_failures=0
  class HTTPResponse:
   def __init__(self,status,body):self.status=status;self.body=body
   def __enter__(self):return self
   def __exit__(self,*args):return False
   def read(self):return self.body
  outer=self
  class Opener:
   def open(self,req,**kwargs):
    outer.http.append(req)
    if req.full_url=='https://auth.developers.deliveroo.com/oauth2/token':
     return HTTPResponse(200,b'{"access_token":"test-only-token"}')
    if req.full_url.startswith('https://api.developers.deliveroo.com/order/v1/orders/') and req.full_url.endswith('/sync_status'):
     if outer.sync_failures:
      outer.sync_failures-=1
      from urllib.error import HTTPError
      from io import BytesIO
      raise HTTPError(req.full_url,503,'synthetic service unavailable',{},BytesIO(b'{}'))
     return HTTPResponse(200,b'{}')
    raise AssertionError('Unexpected outbound endpoint in isolated test')
  self.network=patch('urllib.request.build_opener',return_value=Opener());self.network.start();self.addCleanup(self.network.stop)

 def payload(self,status='accepted',asap=True):
  from test_deliveroo_production import event
  value=event(status,asap);value['body']['order']['display_id']='1234'
  return value

 def post(self,payload,guid=None):
  guid=guid or uuid.uuid4().hex
  raw=json.dumps(payload,ensure_ascii=False).encode()
  signature=hmac.new(b'webhook-secret',guid.encode()+b' '+raw,hashlib.sha256).hexdigest()
  with self.app.test_client() as client:
   return client.post('/api/deliveroo/webhooks/orders',data=raw,content_type='application/json',headers={
    'X-Deliveroo-Sequence-Guid':guid,'X-Deliveroo-Hmac-Sha256':signature})

 def rows(self,sql,*args):
  with self.connect() as conn:return conn.execute(sql,args or None).fetchall()

 def test_acceptance_discount_external_payment_fiscal_and_json(self):
  payload=self.payload();order=payload['body']['order']
  order.update(customer={'first_name':'Test','contact_number':'0100000000'},delivery={
    'line1':'1 rue de test','line2':'Bâtiment B','city':'Testville','postcode':'00000',
    'floor':'2','delivery_notes':'Test uniquement'},order_notes='Sans sauce')
  self.assertEqual(self.post(payload).status_code,200)
  row=self.rows('SELECT * FROM caisse_orders')[0]
  self.assertEqual(str(row['total']),'11.00');self.assertEqual(row['payment'],'PAYÉ DELIVEROO')
  self.assertEqual(row['payment_status'],'PAYÉE');self.assertEqual(row['payment_method'],'DELIVEROO')
  self.assertEqual(str(row['paid_amount']),'11.00');self.assertIsNotNone(row['fiscal_ticket_number'])
  self.assertEqual(row['address'],'1 rue de test Bâtiment B');self.assertEqual(row['delivery_details']['floor'],'2')
  self.assertEqual(str(row['total_ttc']),'11.00');self.assertEqual(row['total_ht']+row['tax_amount'],row['total'])
  payment=self.rows('SELECT * FROM caisse_payment_transactions')[0]
  self.assertEqual(payment['provider'],'DELIVEROO');self.assertEqual(payment['method'],'DELIVEROO')
  with self.app.test_client() as client:
   history=client.get('/api/orders/history');self.assertEqual(history.status_code,200)
   view=history.json['orders'][0];self.assertEqual(view['payment_label'],'PAYÉ DELIVEROO')
   self.assertEqual(view['phone'],'0100000000');self.assertEqual(view['sales_channel'],'DELIVEROO')
   self.assertEqual(len(client.get('/api/kitchen/orders').json['orders']),1)

 def test_duplicate_guid_and_duplicate_order_never_duplicate_ticket_or_payment(self):
  payload=self.payload()
  self.assertEqual(self.post(payload,'fixed-guid').status_code,200)
  self.assertEqual(self.post(payload,'fixed-guid').status_code,200)
  self.assertEqual(self.post(payload).status_code,200)
  self.assertEqual(len(self.rows('SELECT id FROM caisse_orders')),1)
  self.assertEqual(len(self.rows('SELECT id FROM caisse_payment_transactions')),1)
  self.assertEqual(len([req for req in self.http if req.full_url.endswith('/sync_status')]),1)

 def test_sync_failure_keeps_import_idempotent_and_retries_event(self):
  self.sync_failures=1;payload=self.payload()
  self.assertEqual(self.post(payload,'retry-guid').status_code,503)
  self.assertEqual(self.post(payload,'retry-guid').status_code,200)
  self.assertEqual(len(self.rows('SELECT id FROM caisse_orders')),1)
  self.assertEqual(len(self.rows('SELECT id FROM caisse_payment_transactions')),1)

 def test_placed_then_cancelled_never_creates_order_or_payment(self):
  self.assertEqual(self.post(self.payload('placed')).status_code,200)
  self.assertEqual(self.post(self.payload('canceled')).status_code,200)
  self.assertEqual(self.rows('SELECT id FROM caisse_orders'),[])
  self.assertEqual(self.http,[])

 def test_cancellation_then_late_acceptance_cannot_resurrect_ticket(self):
  self.assertEqual(self.post(self.payload('canceled')).status_code,200)
  self.assertEqual(self.post(self.payload()).status_code,200)
  self.assertEqual(self.rows('SELECT id FROM caisse_orders'),[])
  self.assertEqual(self.http,[])

 def test_accepted_then_cancelled_leaves_kitchen_and_preserves_external_payment(self):
  self.assertEqual(self.post(self.payload()).status_code,200)
  with self.connect() as conn:conn.execute("UPDATE deliveroo_production_meta SET sync_at=NOW()-INTERVAL '11 seconds'")
  self.assertEqual(self.post(self.payload('canceled')).status_code,200)
  self.assertEqual(self.rows('SELECT status FROM caisse_orders')[0]['status'],'Annulée')
  self.assertEqual(len(self.rows('SELECT id FROM caisse_payment_transactions')),1)
  with self.app.test_client() as client:self.assertEqual(client.get('/api/kitchen/orders').json['orders'],[])

 def test_scheduled_order_requires_confirmation_and_due_time(self):
  payload=self.payload(asap=False)
  self.assertEqual(self.post(payload).status_code,200)
  with self.app.test_client() as client:
   self.assertEqual(client.get('/api/kitchen/orders').json['orders'],[])
   self.assertEqual(client.get('/api/orders/history').json['orders'][0]['status'],'Programmée')
  confirmed=copy.deepcopy(payload);confirmed['body']['order']['status']='confirmed'
  confirmed['body']['order']['status_log'].append({'status':'confirmed'})
  with self.connect() as conn:conn.execute("UPDATE deliveroo_production_meta SET sync_at=NOW()-INTERVAL '11 seconds'")
  self.assertEqual(self.post(confirmed).status_code,200)
  with self.app.test_client() as client:self.assertEqual(client.get('/api/kitchen/orders').json['orders'],[])
  with self.connect() as conn:conn.execute('UPDATE deliveroo_production_meta SET prepare_at_ms=0')
  with self.app.test_client() as client:self.assertEqual(len(client.get('/api/kitchen/orders').json['orders']),1)

 def test_wrong_signature_context_or_disabled_has_no_caisse_side_effect(self):
  with self.app.test_client() as client:
   self.assertEqual(client.post('/api/deliveroo/webhooks/orders',json=self.payload()).status_code,401)
  payload=self.payload();payload['body']['order']['location_id']='101'
  self.assertEqual(self.post(payload).status_code,503)
  with patch.dict(os.environ,{'BECHEFAA_DELIVEROO_PRODUCTION_ENABLED':'0'}):self.assertEqual(self.post(self.payload()).status_code,503)
  self.assertEqual(self.rows('SELECT id FROM caisse_orders'),[])
  self.assertEqual(self.http,[])

 def test_nonzero_cash_due_is_not_marked_paid(self):
  payload=self.payload();payload['body']['order']['cash_due']['fractional']=100
  self.assertEqual(self.post(payload).status_code,503)
  self.assertEqual(self.rows('SELECT id FROM caisse_orders'),[])
  self.assertEqual(self.http,[])

 def test_missing_plu_reports_failure_without_a_ticket(self):
  payload=self.payload();payload['body']['order']['items'][0]['pos_item_id']=''
  self.assertEqual(self.post(payload).status_code,200)
  self.assertEqual(self.rows('SELECT id FROM caisse_orders'),[])
  sync=[req for req in self.http if req.full_url.endswith('/sync_status')]
  self.assertEqual(json.loads(sync[0].data)['reason'],'pos_item_id_not_found')

 def test_remake_suppresses_parent_in_kitchen_only_after_replacement_import(self):
  payload=self.payload();self.assertEqual(self.post(payload).status_code,200)
  remake=copy.deepcopy(payload);remake['body']['order']['id']='fr:remake-test'
  remake['body']['order']['remake_details']={'parent_order_id':'fr:production-test'}
  self.assertEqual(self.post(remake).status_code,200)
  self.assertEqual(len(self.rows('SELECT id FROM caisse_orders')),2)
  with self.app.test_client() as client:self.assertEqual(len(client.get('/api/kitchen/orders').json['orders']),1)

 def test_meal_card_metadata_does_not_create_extra_local_collection(self):
  payload=self.payload();payload['body']['order']['meal_cards']=[{'provider':'EDENRED','amount':500}]
  self.assertEqual(self.post(payload).status_code,200)
  payments=self.rows('SELECT provider,method,amount,metadata FROM caisse_payment_transactions')
  self.assertEqual(len(payments),1);self.assertEqual(payments[0]['provider'],'DELIVEROO')
  self.assertEqual(payments[0]['metadata']['meal_cards'][0]['amount'],500)

if __name__=='__main__':unittest.main()
