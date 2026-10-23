import ast
import json
import sqlite3
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from flask import Flask, jsonify, request
from clean_caisse.table_core_phase36 import OPEN_TABLE_ORDER_SQL, register_table_core_phase36


class Result:
    def __init__(self, rows=()):self.rows=list(rows)
    def fetchone(self):return self.rows[0] if self.rows else None
    def fetchall(self):return self.rows


class MemoryDB:
    """Model the explicit shared SQL lock and retained rows for route tests."""
    def __init__(self):
        self.lock=threading.RLock();self.orders={};self.reservations={};self.now=0;self.inserts=0
    def open_orders(self):
        return [o for o in self.orders.values() if o.get('table_number') and o.get('status')!='Annulée'
                and o.get('payment_status')!='PAYÉE' and (o['total']<=0 or o.get('paid_amount',0)<o['total'])]
    @contextmanager
    def __call__(self):
        owner=self
        class Conn:
            locked=False
            @contextmanager
            def transaction(self):
                try:yield
                finally:
                    if self.locked:owner.lock.release();self.locked=False
            def execute(self, sql, params=()):
                q=' '.join(sql.split())
                if q.startswith(('ALTER TABLE','CREATE TABLE')):return Result()
                if q.startswith('LOCK TABLE caisse_orders'):
                    owner.lock.acquire();self.locked=True;return Result()
                if 'SELECT COALESCE(MAX(num)' in q:return Result([{'next_num':len(owner.orders)+1}])
                if 'FROM caisse_orders WHERE offline_sync_key' in q:return Result()
                if q.startswith('SELECT id,num,status FROM caisse_orders'):
                    return Result([owner.orders[params[0]]] if params[0] in owner.orders else [])
                if 'FROM caisse_orders WHERE table_number IS NOT NULL' in q:
                    rows=owner.open_orders()
                    if params:rows=[o for o in rows if o['table_number']==params[0] and o['id']!=params[1]]
                    return Result(rows)
                if 'FROM caisse_table_reservations' in q and q.startswith('SELECT'):
                    rows=[{'table_number':n,**r} for n,r in owner.reservations.items() if r['expires_at']>owner.now]
                    if params:rows=[r for r in rows if r['table_number']==params[0]]
                    return Result(rows)
                if q.startswith('DELETE FROM caisse_table_reservations'):
                    if 'WHERE table_number=%s' in q:
                        owner.reservations.pop(params[0],None)
                    else:
                        for n,r in list(owner.reservations.items()):
                            match=r['owner_token']==params[0]
                            if 'AND table_number=%s' in q:match=match and n==params[1]
                            elif 'OR expires_at' in q:match=match or r['expires_at']<=owner.now
                            if match:owner.reservations.pop(n)
                    return Result()
                if q.startswith('INSERT INTO caisse_table_reservations'):
                    n,token=params
                    if n in owner.reservations:raise ValueError('duplicate reservation')
                    owner.reservations[n]={'owner_token':token,'expires_at':owner.now+120};return Result()
                if q.startswith('INSERT INTO caisse_orders'):
                    oid,num=params[:2];owner.inserts+=1
                    owner.orders[oid]={'id':oid,'num':num,'table_number':params[10],'status':params[13],
                                       'total':float(params[14]),'paid_amount':0,'payment_status':'À ENCAISSER'}
                    return Result()
                if q.startswith('INSERT INTO caisse_order_items'):return Result()
                if q.startswith('UPDATE caisse_orders SET table_number'):
                    owner.orders[params[-1]]['table_number']=params[0];return Result()
                raise AssertionError(q)
        yield Conn()


class TableOccupancyTests(unittest.TestCase):
    def setUp(self):
        self.db=MemoryDB();self.app=Flask(__name__)
        register_table_core_phase36(self.app,self.db)
        source=ast.parse((Path(__file__).parents[1]/'clean_caisse/app.py').read_text())
        node=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='create_order')
        node.decorator_list=[]
        env={'__package__':'clean_caisse','request':request,'jsonify':jsonify,'db':self.db,
             'ensure_order_schema':lambda c:None,'Decimal':Decimal,'InvalidOperation':InvalidOperation,
             'time':time,'uuid':uuid,'json':json,'ticket_type':lambda s:s}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'create_order','exec'),env)
        self.app.add_url_rule('/api/orders',view_func=env['create_order'],methods=['POST'])
    def claim(self,token,table=1,**kw):
        return self.app.test_client().put('/api/tables-phase36/reservation',json={'token':token,'table_number':table,**kw})
    def create(self,token='',table=1):
        return self.app.test_client().post('/api/orders',json={'service_mode':'SALLE','table_number':table,
            'table_reservation_token':token,'items':[{'name':'Burger','qty':1,'unit_price':20}]})
    def status(self,table=1):
        r=self.app.test_client().get('/api/tables-phase36/availability')
        self.assertEqual(r.status_code,200,r.get_data(as_text=True));return r.get_json()['tables'][table-1]
    def test_selection_is_exclusive_before_order_and_release_is_owner_scoped(self):
        a,b='a'*24,'b'*24
        self.assertEqual(self.claim(a).status_code,200)
        self.assertTrue(self.status()['reserved']);self.assertFalse(self.status()['available'])
        self.assertEqual(self.claim(b).status_code,409)
        self.assertEqual(self.create(b).status_code,409);self.assertEqual(self.db.inserts,0)
        self.claim(b,None,previous_table=1);self.assertTrue(self.status()['reserved'])
        self.claim(a,None,previous_table=1);self.assertTrue(self.status()['available'])
    def test_order_remains_occupied_until_full_payment_even_after_kitchen_completion(self):
        token='a'*24;self.claim(token)
        response=self.create(token);self.assertEqual(response.status_code,201,response.get_json())
        order=self.db.orders[response.get_json()['id']]
        self.assertFalse(self.db.reservations);self.assertTrue(self.status()['occupied'])
        self.assertEqual(self.create(token).status_code,409)
        order.update(status='Terminée',paid_amount=10,payment_status='PARTIELLEMENT PAYÉE')
        self.assertTrue(self.status()['occupied']);self.assertEqual(self.claim('b'*24).status_code,409)
        order.update(paid_amount=20,payment_status='PAYÉE')
        self.assertTrue(self.status()['available']);self.assertEqual(self.claim('b'*24).status_code,200)
    def test_simultaneous_creates_cannot_save_two_orders_for_same_table(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses=list(pool.map(lambda _:self.create().status_code,range(8)))
        self.assertEqual(responses.count(201),1,responses)
        self.assertEqual(responses.count(409),7,responses);self.assertEqual(self.db.inserts,1)
    def test_simultaneous_selections_have_one_owner_and_expired_drafts_can_be_reclaimed(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses=list(pool.map(lambda i:self.claim(str(i)*24).status_code,range(1,9)))
        self.assertEqual(responses.count(200),1,responses)
        self.db.now=121;self.assertTrue(self.status()['available'])
        self.assertEqual(self.claim('z'*24).status_code,200)
    def test_stale_renewal_does_not_resurrect_released_reservation(self):
        token='a'*24;self.claim(token);self.claim(token,None,previous_table=1)
        self.assertEqual(self.claim(token,renew_only=True).status_code,409)
        self.assertTrue(self.status()['available'])
    def test_claim_switch_and_transfer_reject_occupied_table(self):
        token='a'*24;self.claim(token,1);self.claim(token,2)
        self.assertTrue(self.status(1)['available']);self.assertTrue(self.status(2)['reserved'])
        oid=self.create(token,2).get_json()['id'];self.claim('b'*24,1)
        response=self.app.test_client().put(f'/api/orders/{oid}/table-phase36',json={'table_number':1})
        self.assertEqual(response.status_code,409);self.assertEqual(self.db.orders[oid]['table_number'],2)
    def test_actual_occupancy_sql_covers_partial_final_cancelled_and_zero_total(self):
        conn=sqlite3.connect(':memory:');conn.execute('CREATE TABLE caisse_orders(table_number,status,payment_status,total,paid_amount)')
        for status,payment,total,paid,expected in [('À préparer','À ENCAISSER',20,0,1),
                ('Terminée','PARTIELLEMENT PAYÉE',20,10,1),('Terminée','PAYÉE',20,20,0),
                ('Annulée','À ENCAISSER',20,0,0),('Enregistrée','À ENCAISSER',0,0,1)]:
            conn.execute('DELETE FROM caisse_orders');conn.execute('INSERT INTO caisse_orders VALUES(1,?,?,?,?)',(status,payment,total,paid))
            count=conn.execute('SELECT COUNT(*) FROM caisse_orders WHERE '+OPEN_TABLE_ORDER_SQL).fetchone()[0]
            self.assertEqual(count,expected,(status,payment,total,paid))

if __name__=='__main__':unittest.main()
