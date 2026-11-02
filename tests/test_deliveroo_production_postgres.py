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
   conn.execute('CREATE TABLE catalog_admin_v2(id INTEGER PRIMARY KEY,data_json JSONB)')
   catalog={'products':[{'id':'real-plu','name':'Burger BÉCHÉFAA','options':[{'name':'Extras','options':[['Boisson',0]]}]}]}
   conn.execute('INSERT INTO catalog_admin_v2(id,data_json) VALUES(1,%s::jsonb)',(json.dumps(catalog),))
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
  @self.app.put('/api/orders/<order_id>')
  def update_order(order_id):return jsonify(ok=True)
  @self.app.post('/api/orders/<order_id>/cancel')
  def cancel_order(order_id):return jsonify(ok=True)
  @self.app.post('/api/kitchen/orders/<order_id>/finish')
  def finish_kitchen_order(order_id):return jsonify(ok=True)
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

 def test_parallel_webhooks_import_one_order_and_one_external_payment(self):
  # Prime event/metadata schema, as the readiness deployment will do before enabling.
  self.assertEqual(self.post(self.payload('placed')).status_code,200)
  payload=self.payload()
  with ThreadPoolExecutor(max_workers=2) as pool:
   statuses=list(pool.map(lambda _:self.post(payload).status_code,range(2)))
  self.assertTrue(all(status in (200,503) for status in statuses),statuses)
  # A retry repairs a transient DB/sync conflict without duplicate accounting.
  self.assertEqual(self.post(payload).status_code,200)
  self.assertEqual(len(self.rows('SELECT id FROM caisse_orders')),1)
  self.assertEqual(len(self.rows('SELECT id FROM caisse_payment_transactions')),1)
  self.assertEqual(len([req for req in self.http if req.full_url.endswith('/sync_status')]),1)

 def test_sequence_guid_cannot_rewrite_a_different_order(self):
  self.assertEqual(self.post(self.payload(),'same-sequence').status_code,200)
  other=self.payload();other['body']['order']['id']='fr:different-order'
  self.assertEqual(self.post(other,'same-sequence').status_code,503)
  self.assertEqual(len(self.rows('SELECT id FROM caisse_orders')),1)

 def test_local_edits_and_cancellations_are_blocked_for_deliveroo_only(self):
  self.assertEqual(self.post(self.payload()).status_code,200)
  order_id=self.rows('SELECT id FROM caisse_orders')[0]['id']
  with self.app.test_client() as client:
   self.assertEqual(client.put('/api/orders/'+order_id,json={'items':[]}).status_code,409)
   self.assertEqual(client.post('/api/orders/'+order_id+'/cancel').status_code,409)
   self.assertEqual(client.put('/api/orders/local-caisse-test',json={}).status_code,200)

 def test_delivery_fee_is_recorded_once_as_nonpreparation_line(self):
  payload=self.payload();order=payload['body']['order'];order['total_price']['fractional']=1300
  order['delivery']={'delivery_fee':{'currency_code':'EUR','fractional':200}}
  self.assertEqual(self.post(payload).status_code,200)
  row=self.rows('SELECT total FROM caisse_orders')[0];self.assertEqual(str(row['total']),'13.00')
  rows=self.rows('SELECT name,qty,unit_price,prepared FROM caisse_order_items ORDER BY position')
  self.assertEqual(len(rows),2);self.assertTrue(rows[1]['prepared'])
  self.assertEqual(sum(r['qty']*r['unit_price'] for r in rows),row['total'])

 def test_missing_acceptance_log_does_not_import(self):
  payload=self.payload();payload['body']['order']['status_log']=[{'status':'placed'}]
  self.assertEqual(self.post(payload).status_code,503)
  self.assertEqual(self.rows('SELECT id FROM caisse_orders'),[])

 def test_menu_signature_and_notice_are_gated_by_production_settings(self):
  raw=b'{"event":"menu.upload_result"}';guid='menu-guid'
  signature=hmac.new(b'webhook-secret',guid.encode()+b' '+raw,hashlib.sha256).hexdigest()
  with self.app.test_client() as client:
   self.assertEqual(client.post('/api/deliveroo/webhooks/menu',data=raw,content_type='application/json').status_code,401)
   self.assertEqual(client.post('/api/deliveroo/webhooks/menu',data=raw,content_type='application/json',headers={'X-Deliveroo-Sequence-Guid':guid,'X-Deliveroo-Hmac-Sha256':signature}).status_code,200)
   self.assertIn('deliveroo-alert',client.get('/pos').get_data(as_text=True))
   with patch.dict(os.environ,{'BECHEFAA_DELIVEROO_PRODUCTION_ENABLED':'0'}):
    self.assertNotIn('deliveroo-alert',client.get('/pos').get_data(as_text=True))

 def test_past_scheduled_order_is_released_like_asap(self):
  payload=self.payload(asap=False);order=payload['body']['order'];now=datetime.now(timezone.utc)
  order['start_preparing_at']=(now-timedelta(minutes=10)).isoformat()
  order['status_log']=[{'status':'placed','at':now.isoformat()},{'status':'accepted'}]
  self.assertEqual(self.post(payload).status_code,200)
  with self.app.test_client() as client:self.assertEqual(len(client.get('/api/kitchen/orders').json['orders']),1)

 def test_future_preparation_cannot_be_forced_from_pos_or_kitchen(self):
  self.assertEqual(self.post(self.payload(asap=False)).status_code,200)
  order_id=self.rows('SELECT id FROM caisse_orders')[0]['id']
  with self.app.test_client() as client:self.assertEqual(client.post('/api/kitchen/orders/'+order_id+'/finish').status_code,409)
  with self.connect() as conn:conn.execute('UPDATE deliveroo_production_meta SET confirmed=TRUE,prepare_at_ms=0')
  with self.app.test_client() as client:self.assertEqual(client.post('/api/kitchen/orders/'+order_id+'/finish').status_code,200)

 def test_mismatched_production_plu_name_reports_failure_without_ticket(self):
  payload=self.payload();payload['body']['order']['items'][0]['name']='Un autre produit'
  self.assertEqual(self.post(payload).status_code,200)
  self.assertEqual(self.rows('SELECT id FROM caisse_orders'),[])
  sync=[req for req in self.http if req.full_url.endswith('/sync_status')]
  self.assertEqual(json.loads(sync[0].data)['reason'],'pos_item_id_mismatched')

 def test_modifier_quantity_is_preserved_without_double_charging(self):
  payload=self.payload();payload['body']['order']['items'][0]['modifiers']=[{
    'pos_item_id':'opt:real-plu:0:0','name':'Boisson','quantity':2}]
  self.assertEqual(self.post(payload).status_code,200)
  item=self.rows('SELECT options_json FROM caisse_order_items')[0]
  self.assertEqual(item['options_json'][0]['quantity'],2)
  self.assertEqual(item['options_json'][0]['name'],'2× Boisson')
  self.assertEqual(str(self.rows('SELECT total FROM caisse_orders')[0]['total']),'11.00')

 def test_catalogue_rename_cannot_reject_an_order_already_imported(self):
  payload=self.payload();self.assertEqual(self.post(payload).status_code,200)
  with self.connect() as conn:
   conn.execute("UPDATE catalog_admin_v2 SET data_json='{\"products\":[]}'::jsonb")
  self.assertEqual(self.post(payload).status_code,200)
  self.assertEqual(len(self.rows('SELECT id FROM caisse_orders')),1)
  self.assertEqual(len(self.rows('SELECT id FROM caisse_payment_transactions')),1)

 def test_readiness_does_not_request_oauth_or_write_orders(self):
  with self.app.test_client() as client:
   readiness=client.get('/api/deliveroo/production-readiness-phase6')
   self.assertTrue(readiness.json['ok'])
   self.assertNotIn('fake-secret',readiness.get_data(as_text=True))
   self.assertTrue(client.get('/api/deliveroo/production-catalog-readiness-phase6').json['read_only'])
   self.assertEqual(client.get('/api/deliveroo/production-events-phase6').json['events'],[])
  self.assertEqual(self.rows('SELECT id FROM caisse_orders'),[])
  self.assertEqual(self.http,[])

if __name__=='__main__':unittest.main()
