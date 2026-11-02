"""Shared live-hours/calendar engine, exercised only on the disposable CI database."""
import ast
import copy
import json
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import test_deliveroo_production_postgres as fixture

@unittest.skipUnless(fixture.URL,'Requires local disposable deliveroo_ci')
class SharedHoursPostgresTests(unittest.TestCase):
 setUpClass=classmethod(fixture.ProductionPostgresTests.setUpClass.__func__)
 rows=fixture.ProductionPostgresTests.rows
 def setUp(self):
  fixture.ProductionPostgresTests.setUp(self)
  from clean_caisse.religious_calendar_phase6 import register_religious_calendar_phase6
  from clean_caisse.site_order_hours_phase6 import register_site_order_hours_phase6,DEFAULT_CONFIG
  register_religious_calendar_phase6(self.app,lambda:self.connect())
  register_site_order_hours_phase6(self.app,lambda:self.connect())
  tree=ast.parse(Path('clean_caisse/religious_calendar_phase6.py').read_text())
  register=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='register_religious_calendar_phase6')
  ensure=next(n for n in register.body if isinstance(n,ast.FunctionDef) and n.name=='ensure_tables')
  namespace={};exec(compile(ast.Module(body=[ensure],type_ignores=[]),'<actual-calendar-schema>','exec'),namespace)
  self.tz=ZoneInfo('Europe/Paris');self.now=datetime(2099,3,2,12,tzinfo=self.tz)
  self.cfg=copy.deepcopy(DEFAULT_CONFIG)
  with self.connect() as conn:
   namespace['ensure_tables'](conn)
   conn.execute('CREATE TABLE caisse_site_order_hours(id SMALLINT PRIMARY KEY,config_json JSONB NOT NULL,updated_at TIMESTAMPTZ DEFAULT NOW())')
   conn.execute('INSERT INTO caisse_site_order_hours(id,config_json) VALUES(1,%s::jsonb)',(json.dumps(self.cfg),))
   for label,day,kind,hour in [('past-candle',-3,'candles',17),('past-exit',-2,'havdalah',18),('future-candle',4,'candles',17),('future-exit',5,'havdalah',18),('following-candle',11,'candles',17),('following-exit',12,'havdalah',18)]:
    stamp=(self.now+timedelta(days=day)).replace(hour=hour)
    conn.execute('INSERT INTO caisse_hebrew_calendar_events(event_key,hebrew_year,title,category,starts_at,raw_json) VALUES(%s,5859,%s,%s,%s,%s::jsonb)',(label,kind,kind,stamp,'{}'))
  self.engine=self.app.config['BECHEFAA_ORDER_HOURS_STATE']
 def state(self,now=None,**kwargs):return self.engine(now=now or self.now,channel='deliveroo',strict=True,**kwargs)

 def test_weekday_open_and_cutoff_follow_saved_site_configuration(self):
  self.assertTrue(self.state()['open'])
  self.assertTrue(self.state(self.now.replace(hour=14,minute=59))['open'])
  self.assertTrue(self.state(self.now.replace(hour=15,minute=0))['open'])
  self.assertFalse(self.state(self.now.replace(hour=15,minute=30))['open'])

 def test_manual_deliveroo_closure_does_not_close_site_when_site_flag_false(self):
  with self.connect() as conn:
   conn.execute('INSERT INTO caisse_exceptional_closures(name,starts_at,ends_at,site_enabled,deliveroo_enabled) VALUES(%s,%s,%s,FALSE,TRUE)',('Fixture closure',self.now-timedelta(hours=1),self.now+timedelta(hours=1)))
  self.assertFalse(self.state()['open'])
  self.assertTrue(self.engine(now=self.now,channel='site',strict=True)['open'])

 def test_shabbat_closure_overrides_a_weekly_open_slot(self):
  self.cfg['days']['saturday']={'enabled':True,'slots':[['00:00','23:59']]}
  with self.connect() as conn:conn.execute('UPDATE caisse_site_order_hours SET config_json=%s::jsonb',(json.dumps(self.cfg),))
  state=self.state(self.now+timedelta(days=5))
  self.assertFalse(state['open']);self.assertEqual(state['calendar_override']['source'],'RELIGIOUS_CALENDAR')

 def test_custom_calendar_last_order_is_respected(self):
  with self.connect() as conn:
   conn.execute('INSERT INTO caisse_religious_hours_overrides(event_key,hours_json) VALUES(%s,%s::jsonb)',('future-candle',json.dumps({'last_order':'12:00','closure_time':'12:30'})))
  self.assertFalse(self.state((self.now+timedelta(days=4)).replace(hour=12,minute=1))['open'])

 def test_missing_calendar_fails_closed_for_deliveroo_without_changing_site_default(self):
  with self.connect() as conn:conn.execute('DELETE FROM caisse_hebrew_calendar_events')
  with self.assertRaises(ValueError):self.state()
  self.assertTrue(self.engine(now=self.now)['open'])

 def test_missing_config_is_not_recreated_by_strict_read(self):
  with self.connect() as conn:conn.execute('DELETE FROM caisse_site_order_hours')
  with self.assertRaises(ValueError):self.state()
  self.assertEqual(self.rows('SELECT id FROM caisse_site_order_hours'),[])

 def test_missing_override_table_is_not_recreated_by_strict_read(self):
  with self.connect() as conn:conn.execute('DROP TABLE caisse_religious_hours_overrides')
  with self.assertRaises(Exception):self.state()
  self.assertIsNone(self.rows("SELECT to_regclass('caisse_religious_hours_overrides') AS table_name")[0]['table_name'])

 def test_non_weekend_holiday_closes_an_otherwise_open_service(self):
  with self.connect() as conn:
   for key,kind,day,hour,title in [('holiday-candle','candles',1,17,'Fixture candles'),('holiday-day','holiday',2,0,'Yom Kippur'),('holiday-exit','havdalah',3,18,'Fixture havdalah')]:
    conn.execute('INSERT INTO caisse_hebrew_calendar_events(event_key,hebrew_year,title,category,starts_at,raw_json) VALUES(%s,5859,%s,%s,%s,%s::jsonb)',(key,title,kind,(self.now+timedelta(days=day)).replace(hour=hour),'{}'))
  result=self.state(self.now+timedelta(days=2))
  self.assertFalse(result['open']);self.assertEqual(result['calendar_override']['type'],'holiday')

 def test_utc_input_uses_paris_service_time(self):
  self.assertTrue(self.state(self.now.astimezone(timezone.utc))['open'])
  cutoff=self.now.replace(hour=15,minute=30).astimezone(timezone.utc)
  self.assertFalse(self.state(cutoff)['open'])

 def test_deliveroo_hours_save_and_reset_preserve_site_settings(self):
  client=self.app.test_client()
  endpoint='/api/admin/religious-calendar/hours/future-candle'
  site={'last_order':'13:00','closure_time':'13:30'}
  specific={'last_order':'12:00','closure_time':'12:30'}
  self.assertEqual(client.put(endpoint,json=site).status_code,200)
  self.assertEqual(client.put(endpoint+'?channel=deliveroo',json=specific).status_code,200)
  when=(self.now+timedelta(days=4)).replace(hour=12,minute=15)
  self.assertFalse(self.state(when)['open'])
  self.assertTrue(self.engine(now=when,channel='site',strict=True)['open'])
  with self.connect() as conn:
   rows=conn.execute('SELECT event_key,hours_json FROM caisse_religious_hours_overrides ORDER BY event_key').fetchall()
  self.assertEqual({r['event_key']:r['hours_json'] for r in rows},{'future-candle':site,'deliveroo:future-candle':specific})
  self.assertEqual(client.put(endpoint+'?channel=deliveroo',json={}).status_code,200)
  self.assertTrue(self.state(when)['open'])
  self.assertEqual(self.rows('SELECT event_key,hours_json FROM caisse_religious_hours_overrides')[0]['hours_json'],site)

 def test_deliveroo_hours_refuse_reopening_before_religious_exit(self):
  client=self.app.test_client()
  before=(self.now+timedelta(days=5)).replace(hour=17).isoformat()
  response=client.put('/api/admin/religious-calendar/hours/future-candle?channel=deliveroo',json={'resume_at':before})
  self.assertEqual(response.status_code,400)
  self.assertEqual(self.rows('SELECT event_key FROM caisse_religious_hours_overrides'),[])

 def test_unknown_hours_channel_is_rejected(self):
  response=self.app.test_client().put('/api/admin/religious-calendar/hours/future-candle?channel=unknown',json={})
  self.assertEqual(response.status_code,400)

 def test_weekday_delivery_cutoff_differs_from_pickup_and_marketplaces(self):
  for hour,minute in [(15,0),(15,29),(22,0),(22,29)]:
   when=self.now.replace(hour=hour,minute=minute,second=59)
   self.assertFalse(self.engine(now=when,channel='site',service_mode='delivery',strict=True)['open'])
   self.assertTrue(self.engine(now=when,channel='site',service_mode='pickup',strict=True)['open'])
   for channel in ('deliveroo','uber'):
    result=self.engine(now=when,channel=channel,strict=True)
    self.assertTrue(result['open']);self.assertEqual(result['cutoff_minutes'],0)
  for hour,minute in [(15,30),(22,30)]:
   when=self.now.replace(hour=hour,minute=minute)
   for channel,mode in [('site','delivery'),('site','pickup'),('deliveroo','delivery'),('uber','delivery')]:
    self.assertFalse(self.engine(now=when,channel=channel,service_mode=mode,strict=True)['open'])

 def test_checkout_guard_reads_authoritative_mode_on_all_payment_routes(self):
  from unittest.mock import patch
  class Frozen(datetime):
   @classmethod
   def now(cls,tz=None):return self.now.replace(hour=15,minute=15)
  from clean_caisse.site_order_hours_phase6 import ORDER_PATHS
  with patch('clean_caisse.site_order_hours_phase6.datetime',Frozen):
   for path in ORDER_PATHS:
    for mode,closed in [('LIVRAISON',True),('DELIVERY',True),('À EMPORTER',False)]:
     with self.app.test_request_context(path,method='POST',json={'mode':mode}):
      result=self.app.preprocess_request()
      self.assertEqual(result is not None,closed,(path,mode))
      if closed:self.assertEqual(result[1],409)

 def test_holiday_closure_still_blocks_pickup_and_marketplaces(self):
  when=self.now+timedelta(days=5)
  for channel,mode in [('site','pickup'),('deliveroo','delivery'),('uber','delivery')]:
   result=self.engine(now=when,channel=channel,service_mode=mode,strict=True)
   self.assertFalse(result['open']);self.assertEqual(result['calendar_override']['source'],'RELIGIOUS_CALENDAR')

 def test_calendar_pickup_uses_restaurant_closure_not_delivery_last_order(self):
  with self.connect() as conn:
   conn.execute('INSERT INTO caisse_religious_hours_overrides(event_key,hours_json) VALUES(%s,%s::jsonb)',('future-candle',json.dumps({'last_order':'12:00','closure_time':'12:30'})))
  when=(self.now+timedelta(days=4)).replace(hour=12,minute=15)
  self.assertFalse(self.engine(now=when,service_mode='delivery',strict=True)['open'])
  self.assertTrue(self.engine(now=when,service_mode='pickup',strict=True)['open'])
  self.assertFalse(self.engine(now=when.replace(minute=30),service_mode='pickup',strict=True)['open'])

if __name__=='__main__':unittest.main()

