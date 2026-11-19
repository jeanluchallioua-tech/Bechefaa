"""Startup recovery, non-destructive updates and PIN boundaries."""
import ast
import os
import re
import subprocess
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from flask import Flask, Response
from clean_caisse.access_pin_phase6 import register_access_pin_phase6
from clean_caisse.offline_mode_phase6 import register_offline_mode_phase6, SW_JS, UI

ROOT=Path(__file__).parents[1]

class PinStartupTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__);self.app.secret_key='test-only-session-key'
        @self.app.get('/')
        def root():return 'root'
        @self.app.get('/pos')
        def pos():return Response('<html><body><div id="order"></div><script>function renderOrder(){}</script></body></html>',mimetype='text/html')
        @self.app.get('/api/orders')
        def orders():return {'ok':True}
        @self.app.get('/caisse-sw.js')
        def worker():return Response("importScripts('/offline-sw.js?v=6')",mimetype='application/javascript')
        register_offline_mode_phase6(self.app)
        register_access_pin_phase6(self.app)
        self.client=self.app.test_client()
    def test_worker_can_import_before_login_but_orders_remain_locked(self):
        for path in ['/caisse-sw.js','/offline-sw.js?v=6']:
            r=self.client.get(path);self.assertEqual(r.status_code,200);self.assertEqual(r.mimetype,'application/javascript')
        self.assertEqual(self.client.get('/api/orders').status_code,401)
        r=self.client.get('/');self.assertIn('Saisissez votre code',r.get_data(as_text=True));self.assertEqual(r.headers['X-BECHEFAA-Auth'],'required')
        self.assertNotIn('X-BECHEFAA-POS-Shell',self.client.get('/pos').headers)
    def test_remembered_pin_and_logout(self):
        with patch.dict(os.environ,{'BECHEFAA_CAISSE_PIN':'1234'}):
            r=self.client.post('/auth/pin',data={'pin':'1234'},base_url='https://localhost')
        self.assertEqual(r.status_code,303)
        self.assertEqual(self.client.get('/',base_url='https://localhost').location,'/pos')
        shell=self.client.get('/pos',base_url='https://localhost')
        self.assertEqual(shell.headers['X-BECHEFAA-POS-Shell'],'1')
        self.assertEqual(self.app.permanent_session_lifetime.days,180)
        self.client.get('/auth/logout',base_url='https://localhost')
        self.assertEqual(self.client.get('/api/orders',base_url='https://localhost').status_code,401)
    def test_all_inline_javascript_parses(self):
        for source in [UI,self.client.get('/').get_data(as_text=True)]:
            for script in re.findall(r'<script[^>]*>(.*?)</script>',source,re.S):
                subprocess.run(['node','--check'],input=script,text=True,capture_output=True,check=True)
        subprocess.run(['node','--check'],input=SW_JS,text=True,capture_output=True,check=True)
    def test_single_canonical_worker_url(self):
        source=(ROOT/'clean_caisse/app.py').read_text()
        self.assertNotIn("register('/caisse-sw.js?",source)
        self.assertNotIn("register('/caisse-sw.js?",UI)
        self.assertNotIn('await self.skipWaiting()',SW_JS)

class WorkerRecoveryTests(unittest.TestCase):
    def test_startup_cache_auth_timeout_and_pending_orders(self):
        script=Path(__file__).with_name('tablet_worker_harness.cjs').read_text()
        result=subprocess.run(['node','-e',script],input=SW_JS,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
