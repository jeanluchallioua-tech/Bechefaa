"""Production menu contracts: synthetic catalog and isolated local PostgreSQL only."""
import copy
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from clean_caisse import deliveroo_production_menu_phase6 as menu
import test_deliveroo_production_postgres as fixture

def catalog():
    return {'ok':True,'warnings':[],'summary':{'main_items':1,'warnings':0},'markup_percentage':20,
            'payload':{'menu':{'currency_code':'EUR','categories':[{'id':'cat','item_ids':['item']}],
                       'items':[{'id':'item','plu':'real-plu','name':{'fr':'Burger BÉCHÉFAA'},
                                 'price_info':{'price':1200},'modifier_ids':[]}],'modifiers':[]}}}

DEST={'brand_id':'brand-production','site_id':'site-production','menu_id':menu.MENU_ID}

class PreviewTests(unittest.TestCase):
    def test_preview_is_unchanged_and_target_bound(self):
        raw=catalog();before=copy.deepcopy(raw)
        result=menu.make_preview(raw,DEST)
        self.assertEqual(raw,before);self.assertFalse(result['upload_performed'])
        self.assertEqual(result['document']['site_ids'],['site-production'])
        changed=menu.make_preview(raw,{**DEST,'brand_id':'other-brand'})
        self.assertNotEqual(result['digest'],changed['digest'])
        self.assertEqual(result['document']['menu']['items'][0]['name'],{'fr':'Burger BÉCHÉFAA'})

    def test_warnings_block_publication(self):
        raw=catalog();raw['warnings']=[{'type':'missing_price'}]
        with self.assertRaises(ValueError):menu.make_preview(raw,DEST)

    def test_unknown_item_and_modifier_references_are_rejected(self):
        for change in ('category','modifier'):
            raw=catalog()
            if change=='category':raw['payload']['menu']['categories'][0]['item_ids']=['missing']
            else:raw['payload']['menu']['items'][0]['modifier_ids']=['missing']
            with self.assertRaises(ValueError):menu.make_preview(raw,DEST)

    def test_duplicate_ids_and_missing_plus_are_rejected(self):
        for change in ('duplicate','plu'):
            raw=catalog()
            if change=='duplicate':raw['payload']['menu']['items']*=2
            else:raw['payload']['menu']['items'][0]['plu']=''
            with self.assertRaises(ValueError):menu.make_preview(raw,DEST)

    def test_fractional_and_negative_prices_are_rejected(self):
        for price in (12.5,-1,True):
            raw=catalog();raw['payload']['menu']['items'][0]['price_info']['price']=price
            with self.assertRaises(ValueError):menu.make_preview(raw,DEST)

    def test_only_https_s3_presigned_url_is_accepted(self):
        good='https://bucket.s3.eu-west-1.amazonaws.com/menu?signature=synthetic'
        self.assertEqual(menu.MenuTransport.upload_url({'nested':{'url':good}}),good)
        for url in ('http://bucket.s3.amazonaws.com/x','https://evil.example/x','https://s3.amazonaws.com.evil.example/x','https://user:password@s3.amazonaws.com/x','https://s3.amazonaws.com:444/x'):
            self.assertIsNone(menu.MenuTransport.upload_url({'url':url}))

    def test_production_host_and_site_guards(self):
        from test_deliveroo_production import ENV
        with patch.dict(os.environ,ENV):
            for key,value in [('BECHEFAA_DELIVEROO_PRODUCTION_SITE_ID','101'),('BECHEFAA_DELIVEROO_API_URL','https://api-sandbox.developers.deliveroo.com')]:
                with patch.dict(os.environ,{key:value}):
                    with self.assertRaises(ValueError):menu.target()

    def test_v3_sequence_has_no_sandbox_marker_or_credentials_on_s3(self):
        calls=[]
        class Reply:
            status=200
            def __init__(self,data):self.data=data
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return json.dumps(self.data).encode() if self.data is not None else b''
        class Opener:
            def open(self,req,**kwargs):
                calls.append(req)
                return Reply([{'access_token':'synthetic-token'}, {'url':'https://bucket.s3.eu-west-1.amazonaws.com/menu?signature=synthetic'},None,{'id':'job-synthetic'}][len(calls)-1])
        with patch.dict(os.environ,{'BECHEFAA_DELIVEROO_CLIENT_ID':'synthetic-client','BECHEFAA_DELIVEROO_CLIENT_SECRET':'synthetic-secret'}):
            stages=[];job=menu.MenuTransport(Opener()).publish(menu.make_preview(catalog(),DEST),stages.append)
        self.assertEqual(job,'job-synthetic');self.assertEqual(stages,['generate_s3','s3_upload','publish_job'])
        self.assertEqual([x.get_method() for x in calls],['POST','PUT','PUT','POST'])
        self.assertIsNone(calls[2].get_header('Authorization'))
        self.assertEqual(json.loads(calls[2].data)['menu'],catalog()['payload']['menu'])
        self.assertEqual(json.loads(calls[3].data),{'action':'publish_menu_to_live','params':{}})


@unittest.skipUnless(fixture.URL,'Requires disposable local deliveroo_ci database')
class MenuPostgresTests(unittest.TestCase):
    setUpClass=classmethod(fixture.ProductionPostgresTests.setUpClass.__func__)
    rows=fixture.ProductionPostgresTests.rows
    def setUp(self):
        fixture.ProductionPostgresTests.setUp(self)
        patcher=patch.object(menu,'build_deliveroo_menu_preview',return_value=catalog())
        self.builder=patcher.start();self.addCleanup(patcher.stop)
        # Menu publication must be possible while order routing stays disabled.
        self.disabled=patch.dict(os.environ,{'BECHEFAA_DELIVEROO_PRODUCTION_ENABLED':'0'})
        self.disabled.start();self.addCleanup(self.disabled.stop)
        menu.register_deliveroo_production_menu_phase6(self.app,lambda:self.connect())
        self.sent=0
        outer=self
        class Transport:
            def publish(self,prepared,progress):
                outer.sent+=1;progress('publish_job');return 'job-synthetic'
            def token(self):return 'synthetic'
            def send(self,*args,**kwargs):return {'id':'job-synthetic','status':'success','type':'publish_menu_to_live'}
        self.app.config['BECHEFAA_DELIVEROO_MENU_TRANSPORT']=Transport()
        with self.app.test_client() as client:self.prepared=client.get('/api/deliveroo/production-menu-preview').get_json()
        self.body={k:self.prepared[k] for k in ('digest','confirmation')}

    def publish(self,body=None,origin='https://caisse.bechefaa.fr'):
        with self.app.test_client() as client:
            return client.post('/api/deliveroo/production-menu-publish',json=self.body if body is None else body,headers={'Origin':origin})

    def test_preview_has_no_publication_table_or_network_side_effect(self):
        self.assertTrue(self.prepared['ok']);self.assertEqual(self.sent,0);self.assertEqual(self.http,[])
        self.assertIsNone(self.rows("SELECT to_regclass('deliveroo_production_menu_attempts') AS name")[0]['name'])

    def test_origin_and_confirmation_are_required(self):
        self.assertEqual(self.publish(origin='https://other.example').status_code,403)
        self.assertEqual(self.publish({**self.body,'confirmation':'wrong'}).status_code,409)
        self.assertEqual(self.sent,0)

    def test_catalog_change_after_review_blocks_publish(self):
        changed=catalog();changed['payload']['menu']['items'][0]['price_info']['price']=1300
        self.builder.return_value=changed
        self.assertEqual(self.publish().status_code,409);self.assertEqual(self.sent,0)

    def test_double_click_does_not_publish_twice_or_activate_orders(self):
        response=self.publish();self.assertEqual(response.status_code,200)
        self.assertFalse(response.get_json()['published'])
        self.assertEqual(self.publish().status_code,409);self.assertEqual(self.sent,1)
        self.assertEqual(os.environ['BECHEFAA_DELIVEROO_PRODUCTION_ENABLED'],'0')
        self.assertEqual(self.rows('SELECT id FROM caisse_orders'),[])

    def test_ambiguous_timeout_remains_blocked_after_retry(self):
        def timeout(prepared,progress):self.sent+=1;raise TimeoutError('synthetic')
        self.app.config['BECHEFAA_DELIVEROO_MENU_TRANSPORT'].publish=timeout
        self.assertEqual(self.publish().status_code,502)
        self.assertEqual(self.publish().status_code,409);self.assertEqual(self.sent,1)
        self.assertEqual(self.rows('SELECT state FROM deliveroo_production_menu_attempts')[0]['state'],'uncertain')

    def test_concurrent_publication_is_serialized(self):
        with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(lambda _:self.publish().status_code,range(2)))
        self.assertEqual(sorted(statuses),[200,409]);self.assertEqual(self.sent,1)

    def test_job_status_read_does_not_resubmit(self):
        self.assertEqual(self.publish().status_code,200)
        with self.app.test_client() as client:result=client.get('/api/deliveroo/production-menu-job').get_json()
        self.assertEqual(result['response']['status'],'success');self.assertEqual(self.sent,1)
        self.assertEqual(self.rows('SELECT state FROM deliveroo_production_menu_attempts')[0]['state'],'success')

    def test_legacy_test_buttons_cannot_publish_from_production(self):
        with self.app.test_client() as client:
            for path in ('/api/deliveroo/menu-upload-phase6','/api/deliveroo/scenario15-v3-async-upload-phase6'):
                self.assertEqual(client.post(path,json={}).status_code,409)
        self.assertEqual(self.sent,0)

if __name__=='__main__':unittest.main()
