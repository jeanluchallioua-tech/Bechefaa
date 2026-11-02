import ast
import hashlib
import hmac
import json
import os
import sys
import unittest
from contextlib import nullcontext
from datetime import datetime,timezone,timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from clean_caisse.deliveroo_production_phase6 import (PRODUCTION_APP,API_HOST,AUTH_HOST,readiness,
    signature_valid,validate_order_context,validate_paid_order,missing_plu_paths,
    production_enabled,production_line_amounts,requires_confirmation,delivery_details,register_deliveroo_production_phase6)

ENV={'CC_APP_ID':PRODUCTION_APP,'BECHEFAA_DELIVEROO_PRODUCTION_ENABLED':'1',
 'BECHEFAA_DELIVEROO_API_URL':API_HOST,'BECHEFAA_DELIVEROO_AUTH_URL':AUTH_HOST,
 'BECHEFAA_DELIVEROO_CLIENT_ID':'fake-client','BECHEFAA_DELIVEROO_CLIENT_SECRET':'fake-secret',
 'BECHEFAA_DELIVEROO_WEBHOOK_SECRET':'webhook-secret','BECHEFAA_DELIVEROO_PRODUCTION_SITE_ID':'real-site',
 'BECHEFAA_DELIVEROO_PRODUCTION_BRAND_ID':'real-brand','BECHEFAA_DELIVEROO_ACCEPTANCE_MODE':'deliveroo_tablet'}

def event(status='accepted',asap=True):
 return {'event':'order.status_update','body':{'order':{'id':'fr:production-test','brand_id':'real-brand',
  'location_id':'real-site','is_tabletless':False,'status':status,'asap':asap,
  'start_preparing_at':(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),
  'status_log':[{'status':'placed'},{'status':'accepted'},{'status':status}],
  'total_price':{'fractional':1100,'currency_code':'EUR'},'cash_due':{'fractional':0,'currency_code':'EUR'},
  'items':[{'name':'Burger BÉCHÉFAA','pos_item_id':'real-plu','quantity':1,
   'total_price':{'fractional':1200,'currency_code':'EUR'},'discount_amount':{'fractional':100,'currency_code':'EUR'},'modifiers':[]} ]}}}

class Response:
 def __init__(self,status=200):self.status_code=status

class ProductionTests(unittest.TestCase):
 def setUp(self):
  self.env=patch.dict(os.environ,ENV,clear=True);self.env.start();self.addCleanup(self.env.stop)

 def test_readiness_is_local_and_off_by_default(self):
  with patch('urllib.request.urlopen') as network:
   self.assertTrue(readiness()['ok'])
   self.assertNotIn('fake-secret',json.dumps(readiness()));network.assert_not_called()
  del os.environ['BECHEFAA_DELIVEROO_PRODUCTION_ENABLED'];self.assertFalse(readiness()['ok'])

 def test_every_required_setting_blocks_activation_when_absent(self):
  for key in ENV:
   with self.subTest(key=key):
    with patch.dict(os.environ,{key:''}):self.assertFalse(readiness()['ok'])

 def test_sandbox_urls_app_and_identifiers_are_blocked(self):
  for key,value in [('CC_APP_ID','app_fad0809f-954d-47e7-983d-afb7c3867cd0'),
    ('BECHEFAA_DELIVEROO_API_URL','https://api-sandbox.developers.deliveroo.com'),
    ('BECHEFAA_DELIVEROO_AUTH_URL','https://auth-sandbox.developers.deliveroo.com'),
    ('BECHEFAA_DELIVEROO_PRODUCTION_SITE_ID','101'),
    ('BECHEFAA_DELIVEROO_PRODUCTION_BRAND_ID','bceaa87a-74db-434e-b548-6da7e7de67a6')]:
   with patch.dict(os.environ,{key:value}):self.assertFalse(readiness()['ok'])

 def test_hmac_requires_exact_raw_bytes_and_guid(self):
  raw=b'{"event":"order.new"}';sig=hmac.new(b'secret',b'guid '+raw,hashlib.sha256).hexdigest()
  self.assertTrue(signature_valid('secret','guid',raw,sig))
  for secret,guid,body,supplied in [('', 'guid',raw,sig),('secret','other',raw,sig),('secret','guid',raw+b' ',sig),('secret','guid',raw,'bad')]:
   self.assertFalse(signature_valid(secret,guid,body,supplied))

 def test_wrong_brand_site_or_tabletless_never_import(self):
  for key,value in [('location_id','101'),('brand_id','sandbox'),('is_tabletless',True),('id','gb:other')]:
   payload=event();payload['body']['order'][key]=value
   with self.assertRaises(ValueError):validate_order_context(payload)

 def test_prepaid_discount_and_real_french_plu_are_valid(self):
  payload=event();validate_order_context(payload);validate_paid_order(payload['body']['order'])
  self.assertEqual(missing_plu_paths(payload),[])

 def test_missing_cash_due_or_nonzero_cash_cannot_be_marked_paid(self):
  for cash in (None,{'fractional':100,'currency_code':'EUR'}):
   order=event()['body']['order'];order['cash_due']=cash
   with self.assertRaises(ValueError):validate_paid_order(order)

 def test_inconsistent_total_or_invalid_quantity_are_rejected(self):
  for key,value in [('total_price',{'fractional':99,'currency_code':'EUR'}),('asap',None)]:
   order=event()['body']['order'];order[key]=value
   with self.assertRaises(ValueError):validate_paid_order(order)
  for qty in (True,0,-1,1.5):
   order=event()['body']['order'];order['items'][0]['quantity']=qty
   with self.assertRaises(ValueError):validate_paid_order(order)

 def test_explicit_delivery_fee_reconciles_without_double_count(self):
  order=event()['body']['order'];order['delivery']={'delivery_fee':{'fractional':200,'currency_code':'EUR'}}
  order['total_price']['fractional']=1300
  amounts,fees=production_line_amounts(order)
  self.assertEqual(sum(amounts),1100);self.assertEqual(sum(fee[2] for fee in fees),200)
  validate_paid_order(order)
  order['total_price']['fractional']=1100
  amounts,fees=production_line_amounts(order)
  self.assertEqual(sum(amounts),1100);self.assertEqual(fees,[])

 def test_past_scheduled_is_asap_only_when_proved_due_at_placement(self):
  order=event(asap=False)['body']['order']
  now=datetime.now(timezone.utc)
  order['start_preparing_at']=(now-timedelta(minutes=10)).isoformat()
  order['status_log']=[{'status':'placed','at':now.isoformat()},{'status':'accepted'}]
  self.assertFalse(requires_confirmation(order))
  order['status_log'][0]['at']=(now-timedelta(hours=2)).isoformat()
  self.assertTrue(requires_confirmation(order))
  order['status_log'][0].pop('at');self.assertTrue(requires_confirmation(order))

 def bridge(self):
  tree=ast.parse(Path('clean_caisse/deliveroo_production_phase6.py').read_text())
  register=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='register_deliveroo_production_phase6')
  function=next(n for n in register.body if isinstance(n,ast.FunctionDef) and n.name=='_bridge_order_new')
  self.conn=Mock();self.conn.transaction.return_value=nullcontext()
  def execute(sql,params=None):
   if 'SELECT id FROM caisse_orders' in sql:return SimpleNamespace(fetchone=lambda:({'id':'existing'} if getattr(self,'existing',False) else None))
   if 'SELECT payload FROM deliveroo_production_events' in sql:return SimpleNamespace(fetchall=lambda:getattr(self,'prior',[]))
   if 'MAX(num)' in sql:return SimpleNamespace(fetchone=lambda:{'n':3})
   return Mock()
  self.conn.execute.side_effect=execute
  self.record=Mock()
  self.modules=patch.dict(sys.modules,{'clean_caisse.app':SimpleNamespace(ensure_order_schema=Mock()),
   'clean_caisse.payment_core_phase41':SimpleNamespace(_ensure_payment_schema=Mock()),
   'clean_caisse.payment_transactions_phase44':SimpleNamespace(record_payment_transaction=self.record),
   'clean_caisse.order_tax_snapshot_phase31':SimpleNamespace(_ensure_tax_columns=Mock(),_fiscal_from_ttc=lambda total:(total,total*0,total),TAX_RATE=10),
   'clean_caisse.fiscal_ticket_phase44':SimpleNamespace(allocate_fiscal_ticket_number=Mock())})
  self.modules.start();self.addCleanup(self.modules.stop)
  namespace={'os':os,'json':json,'db':lambda:nullcontext(self.conn),'production_enabled':production_enabled,
    'validate_paid_order':validate_paid_order,'missing_plu_paths':missing_plu_paths,'delivery_details':delivery_details,'production_line_amounts':production_line_amounts,
    'normalized_modifiers':__import__('clean_caisse.deliveroo_production_catalog_phase6',fromlist=['normalized_modifiers']).normalized_modifiers,
    'net_item_cents':__import__('clean_caisse.deliveroo_order_pricing_phase6',fromlist=['net_item_cents']).net_item_cents,
    'datetime':datetime,'timezone':timezone,
    'order_status_and_log':__import__('clean_caisse.deliveroo_order_status_phase6',fromlist=['order_status_and_log']).order_status_and_log}
  exec(compile(ast.Module(body=[function],type_ignores=[]),'<production-bridge>','exec'),namespace)
  return namespace['_bridge_order_new']

 def test_real_accepted_order_imports_discount_and_paye_deliveroo(self):
  bridge=self.bridge();self.assertEqual(bridge(event()),'created')
  inserts=[c.args for c in self.conn.execute.call_args_list if 'INSERT INTO caisse_orders' in c.args[0]]
  self.assertEqual(len(inserts),1);self.assertIn('PAYÉ DELIVEROO',inserts[0][0]);self.assertEqual(inserts[0][1][-3],11)
  self.assertEqual(inserts[0][1][7],'LIVRAISON')
  self.record.assert_called_once();self.assertEqual(self.record.call_args.kwargs['provider'],'DELIVEROO')
  self.assertTrue(any("payment_status='PAYÉE'" in c.args[0] for c in self.conn.execute.call_args_list))

 def test_duplicate_never_inserts_or_records_a_second_payment(self):
  bridge=self.bridge();self.existing=True;self.assertEqual(bridge(event()),'duplicate')
  self.record.assert_not_called()
  self.assertFalse(any('INSERT INTO caisse_orders' in c.args[0] for c in self.conn.execute.call_args_list))

 def test_terminal_event_prevents_resurrection(self):
  bridge=self.bridge();self.prior=[{'payload':event('canceled')}]
  self.assertEqual(bridge(event()),'terminal_event_received');self.record.assert_not_called()

 def test_placed_never_reaches_caisse(self):
  bridge=self.bridge();self.assertEqual(bridge(event('placed')),'awaiting_acceptance')
  self.conn.execute.assert_not_called()

 def test_scheduled_time_is_saved_not_treated_as_asap(self):
  bridge=self.bridge();self.assertEqual(bridge(event(asap=False)),'created')
  self.assertTrue(any('INSERT INTO deliveroo_kitchen_schedule' in c.args[0] for c in self.conn.execute.call_args_list))

 def test_disabled_bridge_never_writes(self):
  bridge=self.bridge()
  with patch.dict(os.environ,{'BECHEFAA_DELIVEROO_PRODUCTION_ENABLED':'0'}):
   with self.assertRaises(ValueError):bridge(event())
  self.conn.execute.assert_not_called()

 def test_receiver_disabled_or_bad_signature_never_touches_db(self):
  app=SimpleNamespace(view_functions={'deliveroo_orders_webhook_phase6':Mock(),
   'deliveroo_menu_webhook_phase6':Mock(),'kitchen_orders':Mock()},logger=Mock(),config={})
  app.get=lambda path:(lambda f:f);app.after_request=lambda f:f;app.before_request=lambda f:f
  request=SimpleNamespace(headers={},get_data=lambda **kw:b'{}',get_json=lambda **kw:{})
  db=Mock()
  with patch.dict(sys.modules,{'flask':SimpleNamespace(jsonify=lambda x:x,request=request,Response=Response)}):
   register_deliveroo_production_phase6(app,db)
  receiver=app.view_functions['deliveroo_orders_webhook_phase6']
  self.assertEqual(receiver().status_code,401)
  with patch.dict(os.environ,{'BECHEFAA_DELIVEROO_PRODUCTION_ENABLED':'0'}):self.assertEqual(receiver().status_code,503)
  db.assert_not_called()

class TerminalAndSyncTests(unittest.TestCase):
 setUp=ProductionTests.setUp
 def nested(self,name,namespace):
  source=ast.parse(Path('clean_caisse/deliveroo_production_phase6.py').read_text())
  register=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='register_deliveroo_production_phase6')
  fn=next(n for n in register.body if isinstance(n,ast.FunctionDef) and n.name==name)
  exec(compile(ast.Module(body=[fn],type_ignores=[]),'<production-test>','exec'),namespace)
  return namespace[name]

 def test_cancellation_updates_only_deliveroo_and_does_not_touch_payments(self):
  from clean_caisse.deliveroo_order_status_phase6 import cancellation_ready
  conn=Mock();conn.transaction.return_value=nullcontext()
  conn.execute.return_value.fetchone.return_value={'status':'À préparer'}
  namespace={'os':os,'db':lambda:nullcontext(conn),'production_enabled':production_enabled,
    'cancellation_ready':cancellation_ready,'_extract_order_id':lambda p:p['body']['order']['id']}
  with patch.dict(sys.modules,{'clean_caisse.app':SimpleNamespace(ensure_order_schema=Mock())}):
   cancel=self.nested('_bridge_order_cancelled',namespace)
   self.assertEqual(cancel(event('canceled')),'cancelled')
  sql,params=conn.execute.call_args.args
  self.assertIn("sales_channel='DELIVEROO'",sql);self.assertEqual(params[0],'Annulée')
  self.assertNotIn('payment',sql)

 def test_sync_duplicate_same_state_is_not_sent_again(self):
  conn=Mock();conn.transaction.return_value=nullcontext()
  conn.execute.return_value.fetchone.return_value={'sync_status':'succeeded','ack_state':'accepted',
     'sync_at':datetime.now(timezone.utc)}
  oauth=Mock()
  sync=self.nested('_sync_status',{'db':lambda:nullcontext(conn),'_ensure_metadata':Mock(),
    'datetime':datetime,'timezone':timezone,'_oauth_token':oauth})
  sync('fr:production-test');oauth.assert_not_called()

 def test_cancellation_sync_waits_for_per_order_interval(self):
  conn=Mock();conn.transaction.return_value=nullcontext()
  conn.execute.return_value.fetchone.return_value={'sync_status':'succeeded','ack_state':'accepted',
     'sync_at':datetime.now(timezone.utc)}
  oauth=Mock()
  sync=self.nested('_sync_status',{'db':lambda:nullcontext(conn),'_ensure_metadata':Mock(),
    'datetime':datetime,'timezone':timezone,'_oauth_token':oauth})
  with self.assertRaises(ValueError):sync('fr:production-test',state='canceled')
  oauth.assert_not_called()

if __name__=='__main__':unittest.main()
