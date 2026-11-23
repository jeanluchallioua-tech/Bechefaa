import copy
from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask
from clean_caisse.uber_webhook_phase6 import register_uber_webhook_phase6
from clean_caisse.uber_sandbox_link import STORE_ID, UberFailure
from clean_caisse.uber_sandbox_pos_display import PREPROD_HOST

M='clean_caisse.uber_sandbox_kitchen'
ORDER='01460685-2d3d-4d79-af00-4eaba3384a34'
BASE='https://'+PREPROD_HOST


class SandboxKitchenTests(unittest.TestCase):
    def setUp(self):
        self.db=MagicMock()
        self.conn=self.db.return_value.__enter__.return_value
        self.cur=self.conn.cursor.return_value.__enter__.return_value
        app=Flask(__name__)
        app.secret_key='test-only'
        register_uber_webhook_phase6(app,self.db)
        self.client=app.test_client()
        with self.client.session_transaction(base_url=BASE) as s:
            s['caisse_auth']=True
            s['uber_sandbox_csrf']='csrf'
        self.summary={'id':ORDER,'store_id':STORE_ID,'display_id':'84A34','current_state':'ACCEPTED',
            'items':[{'title':'Classic Burger','quantity':1,'options':[]}],
            'charges':{'total':{'amount':2100,'currency_code':'EUR'}}}
        self.dispatch='/api/uber/sandbox/kitchen/dispatch'
        self.stage='/api/uber/sandbox/kitchen/stage'
        self.list='/api/uber/sandbox/kitchen-display'

    def post(self,path,data,csrf='csrf'):
        return self.client.post(path,base_url=BASE,json=data,headers={'X-Uber-Test-CSRF':csrf})

    def test_dispatch_uses_only_read_uber_scope_and_unique_local_kitchen_table(self):
        for claimed in ({'order_id':ORDER},None):
            self.cur.fetchone.side_effect=[{'display_exists':True},{'order_id':ORDER},claimed]
            with patch(M+'.notified_orders',return_value=[ORDER]),patch(M+'.get_token',return_value='token') as token,patch(M+'.fetch_order',return_value=(self.summary,True)):
                response=self.post(self.dispatch,{'order_id':ORDER})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json['created'],claimed is not None)
            self.assertFalse(response.json['printing_enabled'])
            self.assertFalse(response.json['creates_pos_sales'])
            token.assert_called_once_with('client_credentials',scope='eats.store.orders.read')
            sql,params=self.cur.execute.call_args.args
            self.assertIn('ON CONFLICT (store_id, order_id) DO NOTHING',sql)
            self.assertEqual(params[:2],(STORE_ID,ORDER))
            self.assertTrue(all(('uber_sandbox_display_orders' in c.args[0] or 'uber_sandbox_kitchen_orders' in c.args[0]) for c in self.cur.execute.call_args_list))
        self.assertEqual(self.conn.commit.call_count,2)

    def test_guard_requires_preproduction_session_csrf_and_valid_uuid(self):
        with patch(M+'.notified_orders') as ids,patch(M+'.get_token') as token:
            self.assertEqual(self.client.post(self.dispatch,base_url='https://caisse.bechefaa.fr').status_code,403)
            self.assertEqual(self.post(self.dispatch,{'order_id':ORDER},csrf='wrong').status_code,403)
            self.assertEqual(self.post(self.dispatch,{'order_id':'../evil'}).status_code,400)
            with self.client.session_transaction(base_url=BASE) as s:s.clear()
            self.assertEqual(self.post(self.dispatch,{'order_id':ORDER}).status_code,403)
            ids.assert_not_called();token.assert_not_called();self.db.assert_not_called()

    def test_dispatch_requires_notification_existing_import_and_fresh_accepted_state(self):
        with patch(M+'.notified_orders',return_value=[]),patch(M+'.get_token') as token:
            self.assertEqual(self.post(self.dispatch,{'order_id':ORDER}).status_code,404)
            token.assert_not_called()
        with patch(M+'.notified_orders',return_value=[ORDER]),patch(M+'.get_token') as token:
            self.cur.fetchone.side_effect=[(False,)]
            self.assertEqual(self.post(self.dispatch,{'order_id':ORDER}).status_code,409)
            token.assert_not_called()
        denied=copy.deepcopy(self.summary);denied['current_state']='CANCELED'
        with patch(M+'.notified_orders',return_value=[ORDER]),patch(M+'.get_token'),patch(M+'.fetch_order',return_value=(denied,True)):
            self.cur.fetchone.side_effect=[(True,),(ORDER,)]
            self.assertEqual(self.post(self.dispatch,{'order_id':ORDER}).status_code,409)
        self.assertTrue(all(c.args[0].startswith('SELECT') for c in self.cur.execute.call_args_list))
        self.conn.commit.assert_not_called()

    def test_uber_failure_never_inserts_kitchen_row(self):
        self.cur.fetchone.side_effect=[(True,),(ORDER,)]
        with patch(M+'.notified_orders',return_value=[ORDER]),patch(M+'.get_token',side_effect=UberFailure('HTTP 403')):
            self.assertEqual(self.post(self.dispatch,{'order_id':ORDER}).status_code,502)
        self.conn.commit.assert_not_called()
        self.assertTrue(all(c.args[0].startswith('SELECT') for c in self.cur.execute.call_args_list))

    def test_first_kitchen_read_does_not_create_any_table(self):
        self.cur.fetchone.return_value=(False,)
        response=self.client.get(self.list,base_url=BASE)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['orders'],[])
        self.assertEqual(response.json['csrf'],'csrf')
        self.assertTrue(response.json['read_only'])
        self.assertEqual(self.cur.execute.call_count,1)
        self.assertTrue(self.cur.execute.call_args.args[0].startswith('SELECT'))
        self.conn.commit.assert_not_called()

    def test_kitchen_list_filters_store_and_preserves_item_options(self):
        self.cur.fetchone.return_value={'kitchen_exists':True}
        self.cur.fetchall.return_value=[{'order_id':ORDER,'summary':self.summary,
            'sent_at':datetime(2026,11,23,17,tzinfo=timezone.utc),'stage':'À préparer'}]
        response=self.client.get(self.list+'?store_id=other',base_url=BASE)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['orders'][0]['stage'],'À préparer')
        self.assertEqual(response.json['orders'][0]['order']['items'][0]['title'],'Classic Burger')
        self.assertEqual(self.cur.execute.call_args.args[1],(STORE_ID,))
        self.assertTrue(all(c.args[0].startswith('SELECT') for c in self.cur.execute.call_args_list))
        self.conn.commit.assert_not_called()

    def test_valid_kitchen_transitions_never_call_uber_or_sales_tables(self):
        for previous,stage in [('À préparer','En préparation'),('En préparation','Terminée')]:
            self.cur.fetchone.return_value=(ORDER,)
            with patch(M+'.get_token') as token:
                response=self.post(self.stage,{'order_id':ORDER,'previous':previous,'stage':stage})
                token.assert_not_called()
            self.assertEqual(response.status_code,200)
            sql,params=self.cur.execute.call_args.args
            self.assertIn('UPDATE uber_sandbox_kitchen_orders',sql)
            self.assertEqual(params,(stage,STORE_ID,ORDER,previous))
        self.assertEqual(self.conn.commit.call_count,2)

    def test_invalid_reverse_skipped_transition_and_stale_click_are_rejected(self):
        for previous,stage in [('À préparer','Terminée'),('Terminée','À préparer'),([], 'Terminée')]:
            response=self.post(self.stage,{'order_id':ORDER,'previous':previous,'stage':stage})
            self.assertEqual(response.status_code,400)
        self.db.assert_not_called()
        self.cur.fetchone.return_value=None
        self.assertEqual(self.post(self.stage,{'order_id':ORDER,'previous':'À préparer','stage':'En préparation'}).status_code,409)

    def test_kitchen_page_is_dedicated_and_production_access_is_blocked(self):
        response=self.client.get('/administration/uber-sandbox/kitchen',base_url=BASE)
        self.assertEqual(response.status_code,200)
        self.assertIn('data-mode="kitchen"',response.text)
        self.assertIn('Activer les alertes sonores Uber TEST',response.text)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(self.client.get('/administration/uber-sandbox/kitchen',base_url='https://caisse.bechefaa.fr').status_code,403)
        self.assertEqual(self.client.get(self.list,base_url='https://caisse.bechefaa.fr').status_code,403)
        self.db.assert_not_called()

    def test_database_failure_is_not_mistaken_for_empty_kitchen(self):
        self.cur.execute.side_effect=RuntimeError('private credentials')
        response=self.client.get(self.list,base_url=BASE)
        self.assertEqual(response.status_code,503)
        self.assertNotIn('orders',response.json)
        self.assertNotIn('private credentials',response.text)


if __name__=='__main__':unittest.main()
