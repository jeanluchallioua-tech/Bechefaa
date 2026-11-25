import copy
from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask

from clean_caisse.uber_sandbox_link import STORE_ID, CLIENT_ID
from clean_caisse.uber_sandbox_order_read import order_summary
from clean_caisse.uber_sandbox_pos_display import PREPROD_HOST, PANEL
from clean_caisse.uber_webhook_phase6 import register_uber_webhook_phase6

ORDER = '01460685-2d3d-4d79-af00-4eaba3384a34'
M = 'clean_caisse.uber_sandbox_pos_display'
BASE = 'https://' + PREPROD_HOST


class SandboxPosDisplayTests(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.conn = self.db.return_value.__enter__.return_value
        self.cur = self.conn.cursor.return_value.__enter__.return_value
        app = Flask(__name__)
        app.secret_key = 'test-only'
        @app.get('/pos')
        def pos():
            return '<html><body><div id="cart">Commande restaurant en cours</div></body></html>'
        register_uber_webhook_phase6(app, self.db)
        self.client = app.test_client()
        with self.client.session_transaction(base_url=BASE) as s:
            s['caisse_auth'] = True
            s['uber_sandbox_csrf'] = 'csrf'
        self.raw = {'id':ORDER,'display_id':'84A34','current_state':'ACCEPTED',
            'store':{'id':STORE_ID}, 'order_manager_client_id':CLIENT_ID,
            'cart':{'items':[{'id':'p1','title':'Burger','quantity':1,
                'selected_modifier_groups':[{'selected_items':[{'id':'o1','title':'Sans tomate','quantity':1}]}]}]},
            'payment':{'charges':{'total':{'amount':1980,'currency_code':'EUR'}}},
            'eater':{'phone':'private-phone','first_name':'private-name'}}
        self.summary = order_summary(self.raw,ORDER)
        self.import_path = '/administration/uber-sandbox/pos-display/import'
        self.list_path = '/api/uber/sandbox/pos-display'

    def post(self, **data):
        return self.client.post(self.import_path, base_url=BASE,
            data={'csrf':'csrf','order_id':ORDER, **data})

    def test_manual_import_writes_only_deduplicated_sandbox_display_table(self):
        with patch(M+'.notified_orders',return_value=[ORDER]), patch(M+'.get_token',return_value='token') as token, patch(M+'.fetch_order',return_value=(self.summary,True)) as fetch:
            response=self.post()
        self.assertEqual(response.status_code,303)
        self.assertEqual(response.headers['Location'],'/administration/uber-sandbox/orders?order_id='+ORDER)
        token.assert_called_once_with('client_credentials',scope='eats.store.orders.read')
        fetch.assert_called_once_with(ORDER,'token')
        self.assertEqual(self.cur.execute.call_count,2)
        for call in self.cur.execute.call_args_list:
            self.assertIn('uber_sandbox_display_orders',call.args[0])
        sql,params=self.cur.execute.call_args.args
        self.assertIn('ON CONFLICT (store_id, order_id) DO UPDATE',sql)
        self.assertEqual(params[:2],(STORE_ID,ORDER))
        self.assertNotIn('private-phone',params[2])
        self.assertNotIn('private-name',params[2])
        self.assertIn('Sans tomate',params[2])
        self.conn.commit.assert_called_once()

    def test_import_returns_to_management_with_confirmation_without_opening_pos(self):
        with patch(M+'.notified_orders',return_value=[ORDER]), patch(M+'.get_token'), patch(M+'.fetch_order',return_value=(self.summary,True)):
            response=self.post()
        with patch('clean_caisse.uber_sandbox_accept.notified_orders',return_value=[ORDER]), patch('clean_caisse.uber_sandbox_accept.manager_status',return_value=True), patch('clean_caisse.uber_sandbox_accept.get_token'), patch('clean_caisse.uber_sandbox_accept.fetch_order',return_value=(self.summary,True)):
            page=self.client.get(response.headers['Location'],base_url=BASE)
        self.assertEqual(page.status_code,200)
        self.assertIn('Commande importée. Revenez dans votre onglet de caisse déjà ouvert',page.text)
        self.assertNotIn('window.open',page.text)
        self.assertNotIn('target="_blank"',page.text)
        with self.client.session_transaction(base_url=BASE) as state:
            self.assertNotIn('uber_sandbox_imported_order',state)

    def test_guard_blocks_other_host_session_csrf_invalid_id_before_network(self):
        with patch(M+'.notified_orders') as notifications, patch(M+'.get_token') as token:
            self.assertEqual(self.client.post(self.import_path,base_url='https://caisse.bechefaa.fr').status_code,404)
            self.assertEqual(self.post(csrf='wrong').status_code,403)
            self.assertEqual(self.post(order_id='../evil').status_code,400)
            with self.client.session_transaction(base_url=BASE) as s: s.clear()
            self.assertEqual(self.post().status_code,403)
            notifications.assert_not_called()
            token.assert_not_called()
            self.db.assert_not_called()

    def test_unnotified_and_denied_order_cannot_enter_display_table(self):
        with patch(M+'.notified_orders',return_value=[]), patch(M+'.fetch_order') as fetch:
            self.assertEqual(self.post().status_code,404)
            fetch.assert_not_called()
        denied=copy.deepcopy(self.summary)
        denied['current_state']='DENIED'
        with patch(M+'.notified_orders',return_value=[ORDER]), patch(M+'.get_token'), patch(M+'.fetch_order',return_value=(denied,True)):
            self.assertEqual(self.post().status_code,409)
        self.db.assert_not_called()

    def test_finished_sandbox_order_can_be_shown_without_reaccepting(self):
        finished=copy.deepcopy(self.summary)
        finished['current_state']='FINISHED'
        with patch(M+'.notified_orders',return_value=[ORDER]), patch(M+'.get_token'), patch(M+'.fetch_order',return_value=(finished,True)):
            self.assertEqual(self.post().status_code,303)

    def test_first_list_visit_does_not_create_table_or_contact_uber(self):
        self.cur.fetchone.return_value=(False,)
        with patch(M+'.get_token') as token:
            response=self.client.get(self.list_path,base_url=BASE)
            token.assert_not_called()
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['orders'],[])
        self.assertFalse(response.json['creates_pos_sales'])
        self.assertTrue(response.json['read_only'])
        self.assertEqual(self.cur.execute.call_count,1)
        self.assertTrue(self.cur.execute.call_args.args[0].startswith('SELECT'))
        self.conn.commit.assert_not_called()

    def test_list_queries_only_current_store_and_labels_import_time(self):
        self.cur.fetchone.side_effect=[{'display_exists':True}, {'kitchen_exists':False}]
        self.cur.fetchall.return_value=[{'imported_at':datetime(2026,11,23,17,tzinfo=timezone.utc),'summary':self.summary}]
        response=self.client.get(self.list_path+'?store_id=other',base_url=BASE)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['orders'][0]['order']['display_id'],'84A34')
        self.assertEqual(response.json['orders'][0]['imported_at'],'2026-11-23T17:00:00+00:00')
        store_queries=[c for c in self.cur.execute.call_args_list if len(c.args)>1]
        self.assertTrue(store_queries)
        self.assertTrue(all(c.args[1]==(STORE_ID,) for c in store_queries))
        self.assertTrue(all(c.args[0].startswith('SELECT') for c in self.cur.execute.call_args_list))
        self.conn.commit.assert_not_called()
        self.assertEqual(response.headers['Cache-Control'],'no-store')

    def test_database_failure_is_not_shown_as_empty_list(self):
        self.cur.execute.side_effect=RuntimeError('private-db-string')
        response=self.client.get(self.list_path,base_url=BASE)
        self.assertEqual(response.status_code,503)
        self.assertNotIn('private-db-string',response.text)
        self.assertNotIn('orders',response.json)

    def test_production_host_and_unauthenticated_list_do_not_access_database(self):
        self.assertEqual(self.client.get(self.list_path,base_url='https://caisse.bechefaa.fr').status_code,404)
        with self.client.session_transaction(base_url=BASE) as s: s.clear()
        self.assertEqual(self.client.get(self.list_path,base_url=BASE).status_code,403)
        self.db.assert_not_called()

    def test_pos_panel_preserves_cart_markup_and_is_absent_from_production(self):
        response=self.client.get('/pos?uber_test_import='+ORDER,base_url=BASE)
        self.assertIn('<div id="cart">Commande restaurant en cours</div>',response.text)
        self.assertEqual(response.text.count('id="uber-sandbox-pos"'),1)
        self.assertIn('hors ventes et statistiques',response.text)
        production=self.client.get('/pos',base_url='https://caisse.bechefaa.fr')
        self.assertNotIn('id="uber-sandbox-pos"',production.text)
        with self.client.session_transaction(base_url=BASE) as s: s.clear()
        unauthenticated=self.client.get('/pos',base_url=BASE)
        self.assertNotIn('id="uber-sandbox-pos"',unauthenticated.text)
        self.db.assert_not_called()

    def test_import_button_only_appears_for_accepted_or_finished_order(self):
        for state,should_show in [('CREATED',False),('DENIED',False),('ACCEPTED',True),('FINISHED',True)]:
            raw=copy.deepcopy(self.raw)
            raw['current_state']=state
            with patch('clean_caisse.uber_sandbox_accept.notified_orders',return_value=[ORDER]), patch('clean_caisse.uber_sandbox_accept.manager_status',return_value=True), patch('clean_caisse.uber_sandbox_accept.get_token'), patch('clean_caisse.uber_sandbox_accept.call_uber',return_value=raw):
                response=self.client.get('/administration/uber-sandbox/orders',base_url=BASE)
            self.assertEqual(response.status_code,200)
            self.assertEqual('Importer cette commande dans la caisse déjà ouverte' in response.text,should_show)


    def test_pos_reads_finished_kitchen_stage_without_importing_a_sale(self):
        self.cur.fetchone.return_value={'display_exists':True}
        self.cur.fetchall.return_value=[{'imported_at':datetime(2026,11,23,17,tzinfo=timezone.utc),'summary':self.summary}]
        with patch('clean_caisse.uber_sandbox_kitchen.read_kitchen_orders',return_value=[{'order':self.summary,'stage':'Terminée'}]):
            response=self.client.get(self.list_path,base_url=BASE)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['orders'][0]['kitchen_stage'],'Terminée')
        self.assertTrue(response.json['kitchen_status_available'])
        self.conn.commit.assert_not_called()

    def test_kitchen_read_failure_keeps_existing_pos_order_visible(self):
        self.cur.fetchone.return_value={'display_exists':True}
        self.cur.fetchall.return_value=[{'imported_at':datetime(2026,11,23,17,tzinfo=timezone.utc),'summary':self.summary}]
        with patch('clean_caisse.uber_sandbox_kitchen.read_kitchen_orders',side_effect=RuntimeError('private')):
            response=self.client.get(self.list_path,base_url=BASE)
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(response.json['orders']),1)
        self.assertFalse(response.json['kitchen_status_available'])
        self.assertNotIn('private',response.text)


if __name__=='__main__': unittest.main()

