"""Table release contracts on a private schema in disposable local CI PostgreSQL."""
import os
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from urllib.parse import urlparse

from flask import Flask
from clean_caisse.table_core_phase36 import register_table_core_phase36, service_day_bounds_ms

URL=os.environ.get('DELIVEROO_TEST_DATABASE_URL','')


@unittest.skipUnless(URL,'Requires disposable local deliveroo_ci database')
class TableReleasePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parsed=urlparse(URL)
        if parsed.hostname not in ('localhost','127.0.0.1') or parsed.path!='/deliveroo_ci':
            raise RuntimeError('Only local disposable deliveroo_ci is permitted')
        import psycopg
        from psycopg.rows import dict_row
        from psycopg import sql
        cls.psycopg,cls.dict_row,cls.sql=psycopg,staticmethod(dict_row),sql

    def setUp(self):
        self.schema='table_release_'+uuid.uuid4().hex
        with self.psycopg.connect(URL,autocommit=True) as conn:
            conn.execute(self.sql.SQL('CREATE SCHEMA {}').format(self.sql.Identifier(self.schema)))
        self.addCleanup(self.drop_schema)
        with self.db() as conn:
            conn.execute('''CREATE TABLE caisse_orders(
                id TEXT PRIMARY KEY,num INTEGER,table_number INTEGER,table_label TEXT,
                status TEXT,total NUMERIC(12,2),payment_status TEXT,
                paid_amount NUMERIC(12,2),created_at BIGINT,z_closure_id BIGINT)''')
            conn.execute('''CREATE TABLE caisse_payment_transactions(
                order_id TEXT,transaction_type TEXT,status TEXT,amount NUMERIC(12,2))''')
        self.app=Flask(__name__)
        register_table_core_phase36(self.app,self.db)

    def drop_schema(self):
        with self.psycopg.connect(URL,autocommit=True) as conn:
            conn.execute(self.sql.SQL('DROP SCHEMA {} CASCADE').format(self.sql.Identifier(self.schema)))

    @contextmanager
    def db(self):
        with self.psycopg.connect(URL,row_factory=self.dict_row) as conn:
            conn.execute(self.sql.SQL('SET search_path TO {}').format(self.sql.Identifier(self.schema)))
            conn.commit()
            yield conn

    def seed(self,oid='order',table=1,created=None,paid=0,payment='À ENCAISSER',closure=None,status='Terminée'):
        with self.db() as conn:
            conn.execute('INSERT INTO caisse_orders VALUES(%s,258,%s,%s,%s,20,%s,%s,%s,%s)',
                (oid,table,'Table '+str(table),status,payment,paid,int(time.time()*1000) if created is None else created,closure))

    def ledger(self,amount,status='SUCCEEDED',kind='PAYMENT',oid='order'):
        with self.db() as conn:conn.execute('INSERT INTO caisse_payment_transactions VALUES(%s,%s,%s,%s)',(oid,kind,status,amount))

    def availability(self,table=1):
        with self.app.test_client() as client:r=client.get('/api/tables-phase36/availability')
        self.assertEqual(r.status_code,200,r.get_data(as_text=True))
        self.assertEqual(r.headers['Cache-Control'],'no-store')
        return r.get_json()['tables'][table-1]

    def claim(self,token='a'*24,table=1):
        with self.app.test_client() as client:
            return client.put('/api/tables-phase36/reservation',json={'token':token,'table_number':table}).status_code

    def test_previous_service_and_z_closed_orders_release_without_rewriting_history(self):
        self.seed('yesterday',created=service_day_bounds_ms()[0]-1)
        self.seed('closed',table=2,closure=42)
        with self.db() as conn:before=conn.execute('SELECT * FROM caisse_orders ORDER BY id').fetchall()
        self.assertTrue(self.availability(1)['available']);self.assertTrue(self.availability(2)['available'])
        self.assertEqual(self.claim(table=1),200);self.assertEqual(self.claim('b'*24,table=2),200)
        with self.db() as conn:self.assertEqual(conn.execute('SELECT * FROM caisse_orders ORDER BY id').fetchall(),before)

    def test_complete_ledger_releases_stale_summary_and_preserves_transactions(self):
        self.seed();self.ledger(7);self.ledger(13)
        self.assertTrue(self.availability()['available']);self.assertEqual(self.claim(),200)
        with self.db() as conn:
            order=conn.execute('SELECT * FROM caisse_orders').fetchone()
            self.assertEqual(order['paid_amount'],0);self.assertEqual(order['payment_status'],'À ENCAISSER')
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM caisse_payment_transactions').fetchone()['n'],2)

    def test_unpaid_partial_pending_and_refunded_balances_still_block(self):
        self.seed();self.assertTrue(self.availability()['occupied'])
        self.ledger(10);self.ledger(10,status='PENDING_EXTERNAL')
        self.assertTrue(self.availability()['occupied']);self.assertEqual(self.claim(),409)
        self.ledger(10);self.ledger(1,kind='REFUND')
        self.assertTrue(self.availability()['occupied']);self.assertEqual(self.claim(),409)

    def test_paid_current_order_releases_and_old_order_cannot_hide_current_unpaid(self):
        self.seed('paid',paid=20,payment='PAYÉE')
        self.assertTrue(self.availability()['available'])
        self.seed('old',created=service_day_bounds_ms()[0]-1)
        self.seed('new',status='Enregistrée')
        self.assertTrue(self.availability()['occupied']);self.assertEqual(self.claim(),409)

    def test_released_table_still_has_only_one_reservation_owner(self):
        self.seed(created=service_day_bounds_ms()[0]-1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses=list(pool.map(lambda t:self.claim(t),['a'*24,'b'*24]))
        self.assertEqual(sorted(statuses),[200,409])

    def test_no_ledger_uses_paid_summary_and_keeps_unpaid_table_locked(self):
        with self.db() as conn:conn.execute('DROP TABLE caisse_payment_transactions')
        self.seed('paid',paid=20,payment='PAYÉE')
        self.seed('unpaid',table=2)
        self.assertTrue(self.availability(1)['available'])
        self.assertTrue(self.availability(2)['occupied'])


if __name__=='__main__':unittest.main()
