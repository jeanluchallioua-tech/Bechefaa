import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask

# Load under an isolated package so the tests never initialize the real POS DB.
ROOT=Path(__file__).resolve().parents[1]
PKG='_bechefaa_notification_settings_tests'
package=types.ModuleType(PKG);package.__path__=[str(ROOT/'clean_caisse')]
sys.modules[PKG]=package
stub=types.ModuleType(PKG+'.app');stub.db=MagicMock()
sys.modules[PKG+'.app']=stub
settings=importlib.import_module(PKG+'.notification_settings_phase6')
notifications=importlib.import_module(PKG+'.order_notifications_phase33')


class MarketplaceSettingsTests(unittest.TestCase):
    def setUp(self):
        self.db=MagicMock();self.conn=self.db.return_value.__enter__.return_value
        self.values={'pos_enabled':True,'pos_volume':82,'kitchen_enabled':True,'kitchen_volume':67,
            'deliveroo_enabled':False,'deliveroo_volume':45,'ubereats_enabled':True,'ubereats_volume':100}
        self.conn.execute.return_value.fetchone.return_value=dict(self.values)
        self.patch=patch.object(settings,'db',self.db);self.patch.start();self.addCleanup(self.patch.stop)
        app=Flask(__name__)
        @app.get('/pos')
        def pos():return '<html><body><div id="cart">Panier courant</div></body></html>'
        @app.get('/cuisine-preparation')
        def kitchen():return '<html><body><div id="todo">Cuisine existante</div></body></html>'
        notifications.register_order_notifications_phase33(app)
        self.client=app.test_client()

    def test_registration_does_not_access_database(self):
        self.db.assert_not_called()

    def test_existing_settings_are_read_and_migration_defaults_preserve_volume(self):
        response=self.client.get('/api/notification-settings')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json,{'ok':True,**self.values})
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        statements=[c.args[0] for c in self.conn.execute.call_args_list]
        migration=next(sql for sql in statements if sql.startswith('ALTER'))
        self.assertIn('deliveroo_volume INTEGER NOT NULL DEFAULT 100',migration)
        self.assertIn('ubereats_enabled BOOLEAN NOT NULL DEFAULT TRUE',migration)
        self.assertNotIn('UPDATE',migration)
        self.assertTrue(all('caisse_notification_settings' in sql for sql in statements))

    def test_old_cached_screen_save_retains_marketplace_settings(self):
        response=self.client.put('/api/notification-settings',json={
            'pos_enabled':False,'pos_volume':38,'kitchen_enabled':True,'kitchen_volume':90})
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.json['deliveroo_enabled'])
        self.assertEqual(response.json['deliveroo_volume'],45)
        self.assertEqual(response.json['ubereats_volume'],100)
        update=next(c for c in self.conn.execute.call_args_list if c.args[0].startswith('UPDATE'))
        self.assertNotIn('deliveroo',update.args[0]);self.assertNotIn('ubereats',update.args[0])

    def test_partial_marketplace_save_retains_all_screen_settings(self):
        response=self.client.put('/api/notification-settings',json={'ubereats_enabled':False,'deliveroo_volume':60})
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.json['ubereats_enabled'])
        self.assertEqual(response.json['deliveroo_volume'],60)
        self.assertEqual(response.json['pos_volume'],82)
        update=next(c for c in self.conn.execute.call_args_list if c.args[0].startswith('UPDATE'))
        self.assertNotIn('pos_volume',update.args[0]);self.assertNotIn('kitchen_volume',update.args[0])
        self.assertTrue(all('caisse_notification_settings' in c.args[0] for c in self.conn.execute.call_args_list))

    def test_volume_clamping_and_invalid_inputs(self):
        response=self.client.put('/api/notification-settings',json={'deliveroo_volume':999,'ubereats_volume':-5})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['deliveroo_volume'],100)
        self.assertEqual(response.json['ubereats_volume'],0)
        self.db.reset_mock()
        for payload in ([],True,{'deliveroo_volume':[]},{'ubereats_volume':True},{'pos_enabled':'false'}):
            self.assertEqual(self.client.put('/api/notification-settings',json=payload).status_code,400)
        self.db.assert_not_called()

    def test_errors_do_not_disclose_database_connection_details(self):
        self.conn.execute.side_effect=RuntimeError('private DB credentials')
        for method in ('get','put'):
            response=getattr(self.client,method)('/api/notification-settings',**({'json':{'pos_volume':40}} if method=='put' else {}))
            self.assertEqual(response.status_code,500)
            self.assertNotIn('private DB credentials',response.text)

    def test_admin_contains_four_sections_and_shared_sound_policy(self):
        response=self.client.get('/administration/notifications')
        self.assertEqual(response.status_code,200)
        for label in ('Caisse','Cuisine','Deliveroo','Uber Eats'):
            self.assertIn('<h2>'+label+'</h2>',response.text)
        for key in ('deliveroo','ubereats'):
            self.assertIn('id="'+key+'Enabled"',response.text)
            self.assertIn('id="'+key+'Volume"',response.text)
            self.assertIn("testTone('pos','"+key+"')",response.text)
            self.assertIn("testTone('kitchen','"+key+"')",response.text)
        self.assertIn('function notificationSoundPolicy(',response.text)
        self.db.assert_not_called()

    def test_existing_screen_content_is_preserved(self):
        response=self.client.get('/pos')
        self.assertIn('<div id="cart">Panier courant</div>',response.text)
        self.assertIn("window.bechefaaNotifyDeliveroo=()=>beep('deliveroo')",response.text)
        self.assertIn("window.bechefaaNotifyUberEats=()=>beep('ubereats')",response.text)
        self.assertIn('function notificationSoundPolicy(',response.text)
        self.assertNotIn('__SOUND_POLICY__',response.text)
        self.db.assert_not_called()

if __name__=='__main__':unittest.main()

