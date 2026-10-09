import json
import sqlite3
import subprocess
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

class SiteOrderFlowTests(unittest.TestCase):
    def test_cashier_send_kitchen_redirects_to_both_tickets_after_database_update(self):
        from clean_caisse import app as backend
        for status in ['Enregistrée','À préparer']:
            writes=[]
            class Result:
                def fetchone(self):
                    return {'id':'local-test-order','num':1,'status':status,'total':17.5,'source':'COMPTOIR'}
            class Conn:
                @contextmanager
                def transaction(self):yield
                def execute(self,sql,params=()):
                    if sql.lstrip().startswith('UPDATE'):writes.append(params)
                    return Result()
            @contextmanager
            def db():yield Conn()
            with patch.object(backend,'db',db):
                response=backend.app.test_client().post('/send-kitchen-classic/local-test-order')
            self.assertEqual(response.status_code,303)
            self.assertEqual(response.headers['Location'],'/epson/print-order-pack/local-test-order')
            self.assertEqual(len(writes),1 if status=='Enregistrée' else 0)

    def test_notification_test_target_survives_pin_and_normal_page_stays_normal(self):
        from flask import Flask
        from clean_caisse.access_pin_phase6 import register_access_pin_phase6
        from clean_caisse.order_notifications_phase33 import register_order_notifications_phase33
        app=Flask(__name__);app.secret_key='local-test-only'
        app.add_url_rule('/pos',endpoint='pos',view_func=lambda:'<html><body>Caisse</body></html>')
        app.add_url_rule('/cuisine-preparation',endpoint='kitchen',view_func=lambda:'<html><body>Cuisine</body></html>')
        register_order_notifications_phase33(app);register_access_pin_phase6(app)
        for target in ['/pos','/cuisine-preparation']:
            client=app.test_client()
            url=target+'?test_notifications=1'
            response=client.get(url,base_url='https://localhost')
            self.assertEqual(response.status_code,303)
            with patch('clean_caisse.access_pin_phase6._pin_configured',return_value='1234'):
                response=client.post('/auth/pin',data={'pin':'1234'},base_url='https://localhost')
            self.assertEqual(response.headers['Location'],url)
            html=client.get(url,base_url='https://localhost').get_data(as_text=True)
            self.assertIn('if(!true)return;',html)
            self.assertNotIn('__TEST_MODE__',html)
            html=client.get(target,base_url='https://localhost').get_data(as_text=True)
            self.assertIn('if(!false)return;',html)

    def test_history_hides_unpaid_site_drafts_and_keeps_restaurant_orders(self):
        from clean_caisse import app as backend
        conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
        conn.execute('CREATE TABLE caisse_orders(id TEXT,num INTEGER,customer_name TEXT,source TEXT,payment TEXT,status TEXT,total REAL,created_at INTEGER,updated_at INTEGER,sales_channel TEXT,paid_amount REAL)')
        for ident,channel,status,paid in [('abandoned','SITE','Enregistrée',0),('paid','SITE','À préparer',17.5),('counter','RESTO','Enregistrée',0)]:
            conn.execute('INSERT INTO caisse_orders VALUES(?,1,?,?,?, ?,17.5,1,1,?,?)',(ident,'Client', 'Emporter','CB',status,channel,paid))
        class Result:
            def __init__(self,rows):self.rows=rows
            def fetchall(self):return self.rows
        class DB:
            def commit(self):pass
            def execute(self,sql,params=()):
                if 'caisse_order_items' in sql:return Result([])
                return Result([dict(row) for row in conn.execute(sql,params).fetchall()])
        @contextmanager
        def db():yield DB()
        with patch.object(backend,'db',db),patch.object(backend,'ensure_order_schema',lambda c:None):
            data=backend.app.test_client().get('/api/orders/history').get_json()
        self.assertTrue(data['ok'])
        self.assertEqual({o['id'] for o in data['orders']},{'paid','counter'})

    def test_failed_kitchen_dispatch_is_retryable_and_never_applies_unpaid_order(self):
        from clean_caisse import mollie_payments_isolated_phase6 as m
        class Conn:
            @contextmanager
            def transaction(self):yield
        @contextmanager
        def db():yield Conn()
        payment={'id':'tr_test','status':'paid','metadata':{'order_id':'paid-order'}}
        with patch.object(m,'_mollie_request',return_value=payment),patch.object(m,'_apply_paid_payment',return_value={'duplicate':False}) as apply,patch.object(m,'_send_paid_order_to_kitchen',return_value={'ok':False}),patch.object(m,'_sync_mollie_refunds_for_payment',return_value=[]):
            with self.assertRaises(RuntimeError):m._finalize_payment(None,db,None,'tr_test')
            apply.assert_called_once()
        payment['status']='canceled'
        with patch.object(m,'_mollie_request',return_value=payment),patch.object(m,'_apply_paid_payment') as apply,patch.object(m,'_send_paid_order_to_kitchen') as send,patch.object(m,'_sync_mollie_refunds_for_payment',return_value=[]):
            result=m._finalize_payment(None,db,None,'tr_test')
            self.assertFalse(result['paid']);apply.assert_not_called();send.assert_not_called()

    def test_notifications_track_admission_by_id_not_order_number(self):
        source=Path('clean_caisse/order_notifications_phase33.py').read_text()
        inspect=source[source.index(' function inspect(orders,'):source.index(' async function poll(){')]
        script='''const assert=require('assert');
const LAST_KEY='test',PAGE='pos',PRINT_ENABLED=false;let seen={},initialized=false,printing=false,beeps=0,notices=[];
const localStorage={setItem(){}};function beep(){beeps++}function showSiteNotice(o){notices.push(o.id)}function autoPrintSiteOrder(){}
'''+inspect+'''
const now=Date.now();
const make=(id,num,status)=>({id,num,status,sales_channel:'SITE',updated_at:now});
inspect([make('draft',40,'Enregistrée')]);assert.equal(beeps,0);assert(!seen.draft);
inspect([make('later',42,'À préparer')]);assert.equal(beeps,1);
inspect([make('earlier',41,'À préparer'),make('later',42,'À préparer')]);assert.equal(beeps,2);assert.equal(notices.at(-1),'earlier');
inspect([make('earlier',41,'À préparer')]);assert.equal(beeps,2);
inspect([make('draft',40,'À préparer')]);assert.equal(beeps,3);
'''
        subprocess.run(['node','-e',script],check=True,capture_output=True)

    def test_first_recent_kitchen_order_alerts_and_repeat_does_not(self):
        source=Path('clean_caisse/order_notifications_phase33.py').read_text()
        inspect=source[source.index(' function inspect(orders,'):source.index(' async function poll(){')]
        script="const assert=require('assert');const LAST_KEY='test',PAGE='kitchen',PRINT_ENABLED=false;let seen={},initialized=false,printing=false,beeps=0;const localStorage={setItem(){}};function beep(){beeps++}function showSiteNotice(){}function autoPrintSiteOrder(){};"+inspect+"inspect([{id:'new',num:1,status:'À préparer',updated_at:Date.now()}]);assert.equal(beeps,1);inspect([{id:'new',num:1,status:'À préparer',updated_at:Date.now()}]);assert.equal(beeps,1);"
        subprocess.run(['node','-e',script],check=True,capture_output=True)

    def test_simulation_uses_detection_without_printing_or_changing_seen_orders(self):
        source=Path('clean_caisse/order_notifications_phase33.py').read_text()
        inspect=source[source.index(' function inspect(orders,'):source.index(' async function poll(){')]
        for page in ['pos','kitchen']:
            script="const assert=require('assert');const LAST_KEY='test',PAGE="+json.dumps(page)+""",PRINT_ENABLED=true;
let seen={existing:123},initialized=true,printing=false,beeps=0,prints=0,writes=0,notices=[];
const localStorage={setItem(){writes++}};function beep(){beeps++}function showSiteNotice(o,simulation){notices.push(simulation)}function autoPrintSiteOrder(){prints++}
"""+inspect+"""
const order={id:'test-order',status:'À préparer',sales_channel:'SITE',updated_at:Date.now()};
assert.equal(inspect([order],{simulation:true}),1);assert.equal(beeps,1);assert.equal(prints,0);assert.equal(writes,0);assert.deepEqual(seen,{existing:123});assert.equal(initialized,true);
assert.equal(inspect([order],{simulation:true}),1);assert.equal(beeps,2);assert.equal(prints,0);assert.equal(writes,0);
assert.equal(inspect([order]),1);assert.equal(beeps,3);assert.equal(prints,1);assert.equal(writes,1);assert(seen['test-order']);
"""
            subprocess.run(['node','-e',script],check=True,capture_output=True)

if __name__=='__main__':unittest.main()
