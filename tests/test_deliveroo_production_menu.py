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

def recipes():
    raw=catalog();m=raw['payload']['menu']
    def item(key,name,kind='ITEM',price=0,groups=None):
        return {'id':key,'plu':key.removeprefix('item_'),'name':{'fr':name},'type':kind,
                'price_info':{'price':price,'overrides':[]},'modifier_ids':groups or []}
    m['items']=[item('item_2','Formule Falafel','BUNDLE',1800,['bundle_2_drink']),
        item('item_4','Formule Enfant','BUNDLE',1560,['bundle_4_main','bundle_4_drink']),
        item('item_8','Tender Chicken Maison',price=960,groups=['type_8','count_8']),
        item('classic','Classic Panure traditionnelle Maison','CHOICE'),
        item('crispy','Crispy Panure extra croustillante Maison','CHOICE'),
        item('cheesy','Cheesy cœur cheddar','CHOICE',180),item('five','5 pièces','CHOICE'),
        item('ten','10 pièces','CHOICE',840),item('item_76','Caprisun',price=180),
        item('item_70','Coca cola',price=360),item('item_68','Evian',price=360)]
    for row in m['items']:
        if row['id'] in ('item_76','item_70','item_68'):
            row['price_info']['overrides']=[{'type':'ITEM','id':'item_2','price':100 if row['id']=='item_70' else 0}, {'type':'ITEM','id':'item_4','price':0}]
    def mod(key,ids):return {'id':key,'item_ids':ids,'name':{'fr':key},'min_selection':1,'max_selection':1}
    m['modifiers']=[mod('bundle_2_drink',['item_76','item_70','item_68']),
        mod('bundle_4_main',['item_8']),mod('bundle_4_drink',['item_76','item_70','item_68']),
        mod('type_8',['classic','crispy','cheesy']),mod('count_8',['five','ten'])]
    m['categories'][0]['item_ids']=[x['id'] for x in m['items'] if x['type']!='CHOICE']
    return raw

class ProductionRecipeTests(unittest.TestCase):
    def fixed(self):return menu.make_preview(recipes(),DEST)['document']['menu']
    def test_falafel_is_eighteen_euros_and_coca_has_no_premium(self):
        fixed=self.fixed();items={x['id']:x for x in fixed['items']}
        self.assertEqual(items['item_2']['price_info']['price'],1800)
        self.assertEqual(next(x['price'] for x in items['item_70']['price_info']['overrides'] if x['id']=='item_2'),0)

    def test_kids_caprisun_is_included_other_drinks_use_marked_premium(self):
        fixed=self.fixed();items={x['id']:x for x in fixed['items']};mods={x['id']:x for x in fixed['modifiers']}
        for key in mods['bundle_4_drink']['item_ids']:
            self.assertEqual(next(x['price'] for x in items[key]['price_info']['overrides'] if x['id']=='item_4'),0 if key=='item_76' else 180)

    def test_kids_has_classic_or_crispy_without_quantity_or_cheesy(self):
        fixed=self.fixed();items={x['id']:x for x in fixed['items']};mods={x['id']:x for x in fixed['modifiers']}
        child=items[mods['bundle_4_main']['item_ids'][0]]
        self.assertEqual(len(child['modifier_ids']),1)
        self.assertEqual(mods[child['modifier_ids'][0]]['item_ids'],['classic','crispy'])
        self.assertEqual(child['plu'],'8')

    def test_standalone_tenders_and_source_are_preserved(self):
        raw=recipes();before=copy.deepcopy(raw);fixed=menu.make_preview(raw,DEST)['document']['menu']
        self.assertEqual(raw,before)
        original=next(x for x in raw['payload']['menu']['items'] if x['id']=='item_8')
        self.assertEqual(next(x for x in fixed['items'] if x['id']=='item_8'),original)

    def test_future_markup_changes_affect_drink_surcharge_once(self):
        raw=recipes();raw['markup_percentage']=10
        fixed=menu.make_preview(raw,DEST)['document']['menu']
        cola=next(x for x in fixed['items'] if x['id']=='item_70')
        self.assertEqual(next(x['price'] for x in cola['price_info']['overrides'] if x['id']=='item_4'),165)

    def test_unexpected_falafel_price_blocks_preview(self):
        raw=recipes();raw['payload']['menu']['items'][0]['price_info']['price']=1900
        with self.assertRaises(ValueError):menu.make_preview(raw,DEST)

    def test_inferred_diet_labels_are_not_published_or_written_to_source(self):
        raw=recipes();raw['payload']['menu']['items'][0]['diets']=['dairy_free','vegetarian']
        fixed=menu.make_preview(raw,DEST)['document']['menu']
        self.assertEqual(fixed['items'][0]['diets'],[])
        self.assertEqual(raw['payload']['menu']['items'][0]['diets'],['dairy_free','vegetarian'])

    def test_known_bundle_constituents_use_their_own_modifier_plus(self):
        from clean_caisse.deliveroo_production_catalog_phase6 import check_order_plus
        mapping={'4':{'name':'formule enfant','parent':None},'8':{'name':'tender chicken maison','parent':None},'opt:8:0:1':{'name':'classic','parent':'8'}}
        order={'items':[{'pos_item_id':'4','name':'Formule Enfant','modifiers':[{'pos_item_id':'8','name':'Tender Chicken Maison','modifiers':[{'pos_item_id':'opt:8:0:1','name':'Classic'}]}]}]}
        self.assertEqual(check_order_plus(order,mapping),(None,[]))
        order['items'][0]['modifiers'][0]['name']='Wrong product'
        self.assertEqual(check_order_plus(order,mapping)[0],'pos_item_id_mismatched')

    def test_unrelated_product_is_not_accepted_as_bundle_child(self):
        from clean_caisse.deliveroo_production_catalog_phase6 import check_order_plus
        mapping={'4':{'name':'formule enfant','parent':None},'99':{'name':'autre','parent':None}}
        order={'items':[{'pos_item_id':'4','name':'Formule Enfant','modifiers':[{'pos_item_id':'99','name':'Autre'}]}]}
        self.assertEqual(check_order_plus(order,mapping)[0],'pos_item_id_mismatched')

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
        for request in calls[1:]:self.assertEqual(request.get_header('User-agent'),menu.INTEGRATOR_USER_AGENT)
        self.assertIsNone(calls[2].get_header('Authorization'))
        self.assertEqual(json.loads(calls[2].data)['menu'],catalog()['payload']['menu'])
        self.assertEqual(json.loads(calls[3].data),{'action':'publish_menu_to_live','params':{}})


class AccessProbeTests(unittest.TestCase):
    def test_error_summary_redacts_secrets_and_presigned_urls(self):
        raw=json.dumps({'message':'invalid params synthetic-token https://bucket.s3.amazonaws.com/key?signature=secret','debug':'discard','errors':[{'field':'params','message':'invalid params'}]}).encode()
        summary=menu.provider_error_summary(raw,'synthetic-token')
        text=json.dumps(summary)
        self.assertNotIn('synthetic-token',text);self.assertNotIn('signature',text);self.assertNotIn('discard',text)
        self.assertIn('invalid params',text)

    def test_job_400_body_is_captured_without_retry(self):
        calls=[]
        class Opener:
            def open(self,req,**kwargs):
                calls.append(req)
                raise HTTPError(req.full_url,400,'bad request',{},BytesIO(b'{"message":"invalid params"}'))
        with self.assertRaises(menu.ProviderFailure) as caught:menu.MenuTransport(Opener()).publish_job(DEST,'synthetic-token')
        self.assertEqual(caught.exception.detail['fields']['message'],'invalid params')
        self.assertEqual(len(calls),1)

    def probe(self, body, status=403, content_type='application/json', path='/menu/v1/brands/brand/menus/menu', identified_client=False):
        calls=[]
        class Opener:
            def open(self, request, **kwargs):
                calls.append(request)
                raise HTTPError(request.full_url,status,'synthetic',{'Content-Type':content_type},BytesIO(body))
        result=menu.MenuTransport(Opener()).probe(path,'synthetic-token',identified_client=identified_client)
        self.assertEqual([r.get_method() for r in calls],['GET'])
        if identified_client:self.assertEqual(calls[0].get_header('User-agent'),menu.INTEGRATOR_USER_AGENT)
        self.assertNotIn('synthetic-token',json.dumps(result))
        return result

    def test_json_error_keeps_code_without_reflected_message(self):
        result=self.probe(b'{"code":"ACCESS_DENIED","message":"synthetic-token"}')
        self.assertEqual(result['http_status'],403)
        self.assertEqual(result['provider_code'],'ACCESS_DENIED')
        self.assertNotIn('message',result)

    def test_html_denial_is_classified_without_returning_body(self):
        result=self.probe(b'<html>Access denied synthetic-token</html>',content_type='text/html')
        self.assertEqual(result['response_class'],'access_denied')
        self.assertNotIn('body',result)

    def test_site_brand_association_and_menu_absence_are_distinct(self):
        with patch.dict(os.environ,{'BECHEFAA_DELIVEROO_PRODUCTION_BRAND_ID':'brand'}):
            result=self.probe(b'{"brand_id":["brand"]}',status=200,path='/site/v1/restaurant_locations/site')
        self.assertTrue(result['configured_brand_associated'])
        self.assertEqual(self.probe(b'{}',status=404)['http_status'],404)

    def test_probe_rejects_publish_and_auth_paths(self):
        for path in ('/menu/v3/brands/brand/jobs','/oauth2/token'):
            with self.assertRaises(ValueError):menu.MenuTransport().probe(path,'synthetic')

    def test_identified_client_keeps_get_and_redacts_cloudflare_html(self):
        result=self.probe(b'<title>Just a moment...</title><script>synthetic-token</script>',content_type='text/html',identified_client=True)
        self.assertEqual(result['request_profile'],'identified_integrator')
        self.assertEqual(result['response_class'],'cloudflare_challenge')
        result=self.probe(b'<h1>Sorry, you have been blocked</h1>Error code: 1020',content_type='text/html')
        self.assertEqual(result['response_class'],'cloudflare_block_page')
        self.assertEqual(result['cloudflare_error_code'],'1020')


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
            def publish_job(self,dest,token):outer.sent+=1;return 'job-only-synthetic'
            def probe(self,path,token):return {'method':'GET','path':path,'http_status':403}
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

    def test_access_diagnostic_does_not_create_attempt_or_activate_orders(self):
        with self.app.test_client() as client:result=client.get('/api/deliveroo/production-menu-access').get_json()
        self.assertTrue(result['read_only']);self.assertFalse(result['s3_url_requested'])
        self.assertEqual(len(result['probes']),2)
        self.assertEqual([p['http_status'] for p in result['probes']],[403,403])
        self.assertEqual(self.sent,0)
        self.assertEqual(os.environ['BECHEFAA_DELIVEROO_PRODUCTION_ENABLED'],'0')
        self.assertIsNone(self.rows("SELECT to_regclass('deliveroo_production_menu_attempts') AS name")[0]['name'])

    def test_access_diagnostic_preserves_uncertain_attempt(self):
        def timeout(prepared,progress):raise TimeoutError('synthetic')
        self.app.config['BECHEFAA_DELIVEROO_MENU_TRANSPORT'].publish=timeout
        self.assertEqual(self.publish().status_code,502)
        before=self.rows('SELECT * FROM deliveroo_production_menu_attempts')
        with self.app.test_client() as client:self.assertEqual(client.get('/api/deliveroo/production-menu-access').status_code,200)
        self.assertEqual(self.rows('SELECT * FROM deliveroo_production_menu_attempts'),before)
        self.assertEqual(self.publish().status_code,409)

    def test_html_denial_compares_only_get_client_identification(self):
        calls=[]
        def probe(path,token,identified_client=False):
            calls.append((path,identified_client))
            return {'method':'GET','path':path,'http_status':404 if identified_client else 403,'content_type':'application/json' if identified_client else 'text/html'}
        self.app.config['BECHEFAA_DELIVEROO_MENU_TRANSPORT'].probe=probe
        with self.app.test_client() as client:result=client.get('/api/deliveroo/production-menu-access').get_json()
        self.assertEqual(len(result['probes']),4)
        self.assertEqual([identified for _,identified in calls],[False,True,False,True])
        self.assertEqual(calls[0][0],calls[1][0]);self.assertEqual(calls[2][0],calls[3][0])
        self.assertEqual(self.sent,0)

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

    def denied_attempt(self,stage='generate_s3',status=403):
        transport=self.app.config['BECHEFAA_DELIVEROO_MENU_TRANSPORT']
        original=transport.publish
        def deny(prepared,progress):
            self.sent+=1;progress(stage);raise menu.ProviderFailure(stage,status)
        transport.publish=deny
        self.assertEqual(self.publish().status_code,502)
        transport.publish=original

    def test_refused_s3_requires_explicit_recovery_and_preserves_original(self):
        self.denied_attempt()
        self.assertEqual(self.publish().status_code,409)
        self.assertEqual(self.publish({**self.body,'retry_denied_s3':True}).status_code,200)
        original=self.rows('SELECT previous_attempt FROM deliveroo_production_menu_recoveries')[0]['previous_attempt']
        self.assertEqual(original['http_status'],403);self.assertEqual(original['stage'],'generate_s3')
        self.assertEqual(self.rows('SELECT state FROM deliveroo_production_menu_attempts')[0]['state'],'submitted')
        self.assertEqual(self.publish({**self.body,'retry_denied_s3':True}).status_code,409)
        self.assertEqual(self.sent,2)

    def test_recovery_never_repeats_after_a_second_denial(self):
        self.denied_attempt()
        def deny(prepared,progress):self.sent+=1;raise menu.ProviderFailure('generate_s3',403)
        self.app.config['BECHEFAA_DELIVEROO_MENU_TRANSPORT'].publish=deny
        body={**self.body,'retry_denied_s3':True}
        self.assertEqual(self.publish(body).status_code,502)
        self.assertEqual(self.publish(body).status_code,409);self.assertEqual(self.sent,2)

    def test_recovery_blocks_s3_upload_and_job_uncertainty(self):
        self.denied_attempt()
        for stage,status,job in (('s3_upload',403,None),('publish_job',403,None),('generate_s3',None,None),('generate_s3',403,'existing-job')):
            with self.connect() as conn:conn.execute('UPDATE deliveroo_production_menu_attempts SET stage=%s,http_status=%s,job_id=%s',(stage,status,job))
            self.assertEqual(self.publish({**self.body,'retry_denied_s3':True}).status_code,409)
        self.assertEqual(self.sent,1)

    def test_concurrent_recovery_publishes_once(self):
        self.denied_attempt()
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses=list(pool.map(lambda _:self.publish({**self.body,'retry_denied_s3':True}).status_code,range(2)))
        self.assertEqual(sorted(statuses),[200,409]);self.assertEqual(self.sent,2)

    def test_changed_catalog_cannot_recover_old_digest(self):
        self.denied_attempt()
        changed=catalog();changed['payload']['menu']['items'][0]['price_info']['price']=1300
        self.builder.return_value=changed
        with self.app.test_client() as client:prepared=client.get('/api/deliveroo/production-menu-preview').get_json()
        self.assertEqual(self.publish({k:prepared[k] for k in ('digest','confirmation')}|{'retry_denied_s3':True}).status_code,409)
        self.assertEqual(self.sent,1)

    def resume_job(self,body=None):
        with self.app.test_client() as client:
            return client.post('/api/deliveroo/production-menu-resume-job',json=self.body if body is None else body,headers={'Origin':'https://caisse.bechefaa.fr'})

    def test_job_only_recovery_never_uploads_and_preserves_refusal(self):
        self.denied_attempt('publish_job',400)
        def no_upload(*args):raise AssertionError('Must not upload again')
        self.app.config['BECHEFAA_DELIVEROO_MENU_TRANSPORT'].publish=no_upload
        result=self.resume_job()
        self.assertEqual(result.status_code,200);self.assertFalse(result.get_json()['upload_performed'])
        self.assertEqual(self.sent,2);self.assertEqual(self.resume_job().status_code,409)
        old=self.rows('SELECT previous_attempt FROM deliveroo_production_menu_job_recoveries')[0]['previous_attempt']
        self.assertEqual(old['stage'],'publish_job');self.assertEqual(old['http_status'],400)

    def test_job_error_is_saved_and_second_resume_blocked(self):
        self.denied_attempt('publish_job',400)
        def deny(*args):self.sent+=1;raise menu.ProviderFailure('publish_job',400,{'fields':{'message':'invalid params'}})
        self.app.config['BECHEFAA_DELIVEROO_MENU_TRANSPORT'].publish_job=deny
        self.assertEqual(self.resume_job().status_code,502)
        self.assertEqual(self.resume_job().status_code,409);self.assertEqual(self.sent,2)
        with self.app.test_client() as client:status=client.get('/api/deliveroo/production-menu-job').get_json()
        self.assertFalse(status['calls_deliveroo'])
        self.assertEqual(status['attempt']['error_detail']['fields']['message'],'invalid params')

    def test_job_resume_rejects_wrong_state_and_confirmation(self):
        self.denied_attempt('publish_job',400)
        self.assertEqual(self.resume_job({**self.body,'confirmation':'wrong'}).status_code,409)
        for stage,status,job in (('s3_upload',400,None),('publish_job',None,None),('publish_job',400,'existing-job')):
            with self.connect() as conn:conn.execute('UPDATE deliveroo_production_menu_attempts SET stage=%s,http_status=%s,job_id=%s',(stage,status,job))
            self.assertEqual(self.resume_job().status_code,409)
        self.assertEqual(self.sent,1)

    def test_concurrent_job_resume_is_serialized(self):
        self.denied_attempt('publish_job',400)
        with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(lambda _:self.resume_job().status_code,range(2)))
        self.assertEqual(sorted(statuses),[200,409]);self.assertEqual(self.sent,2)

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

