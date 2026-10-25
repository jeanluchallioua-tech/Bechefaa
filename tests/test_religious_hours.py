import importlib.util
import json
import unittest
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from flask import Flask
spec=importlib.util.spec_from_file_location('calendar',Path(__file__).parents[1]/'clean_caisse/religious_calendar_phase6.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Result:
    def __init__(self, rows=()):self.rows=rows
    def fetchall(self):return self.rows
    def fetchone(self):return next(iter(self.rows),None)
class Connection:
    def __init__(self):
        self.saved={}
        self.events=[dict(event_key='entry',hebrew_year=5787,title='Bougies',category='candles',starts_at=datetime(2026,10,30,17,15,tzinfo=m.TZ)),dict(event_key='exit',hebrew_year=5787,title='Havdalah',category='havdalah',starts_at=datetime(2026,10,31,18,15,tzinfo=m.TZ))]
    @contextmanager
    def transaction(self):yield
    def execute(self,sql,params=()):
        if sql.startswith('CREATE'):return Result()
        if 'SELECT config_json' in sql:return Result([{'config_json':{'days':{},'cutoff_minutes':30}}])
        if sql.startswith('SELECT starts_at'):return Result([self.events[0]] if params[0]=='entry' else [])
        if 'FROM caisse_hebrew_calendar_events' in sql:return Result(self.events)
        if sql.startswith('SELECT event_key,hours_json'):return Result([dict(event_key=k,hours_json=v) for k,v in self.saved.items()])
        if sql.startswith('INSERT INTO caisse_religious_hours_overrides'):self.saved[params[0]]=json.loads(params[1]);return Result()
        if sql.startswith('DELETE FROM caisse_religious_hours_overrides'):self.saved.pop(params[0],None);return Result()
        if 'FROM caisse_exceptional_closures' in sql:return Result()
        raise AssertionError(sql)
class HoursTests(unittest.TestCase):
    def setUp(self):
        self.conn=Connection()
        @contextmanager
        def db():yield self.conn
        self.app=Flask(__name__);m.register_religious_calendar_phase6(self.app,db);self.client=self.app.test_client()
    def period(self):return self.client.get('/api/admin/religious-calendar').get_json()['periods'][0]
    def test_save_read_engine_and_reset(self):
        automatic=self.period()
        custom={'closure_time':'13:30','last_order':'13:00','restaurant_reopen_time':'19:00','resume_at':'2026-10-31T19:15','service_end_time':'23:30'}
        self.assertEqual(self.client.put('/api/admin/religious-calendar/hours/entry',json=custom).status_code,200)
        p=self.period();self.assertEqual(p['last_order'],'13:00');self.assertEqual(p['resume_time'],'19:15');self.assertEqual(p['automatic_hours'],automatic['automatic_hours'])
        engine=self.app.config['BECHEFAA_SITE_ORDER_CALENDAR_OVERRIDE']
        self.assertEqual(engine(datetime(2026,10,30,13,15,tzinfo=m.TZ))['mode'],'closed')
        self.assertEqual(engine(datetime(2026,10,31,19,16,tzinfo=m.TZ))['mode'],'open')
        self.assertEqual(engine(datetime(2026,10,31,23,5,tzinfo=m.TZ))['mode'],'closed')
        self.client.put('/api/admin/religious-calendar/hours/entry',json={})
        self.assertEqual(self.period()['custom_hours'],{});self.assertEqual(self.period()['closure_time'],automatic['closure_time'])
    def test_invalid_input_does_not_save(self):
        for body in ({'last_order':'26:00'},{'closure_time':'12:00','last_order':'13:00'},{'resume_at':'2026-10-31T17:00'},{'other':'x'}):
            self.assertEqual(self.client.put('/api/admin/religious-calendar/hours/entry',json=body).status_code,400)
        self.assertFalse(self.conn.saved)
    def test_page_has_editable_column(self):
        page=self.client.get('/administration/calendrier-religieux').get_data(as_text=True)
        self.assertIn('Horaires personnalisés',page);self.assertIn('hoursEditor(x)',page);self.assertIn('Rétablir le calcul',page)
if __name__=='__main__':unittest.main()
