import copy
import json
import subprocess
import unittest
from contextlib import contextmanager
from pathlib import Path
from flask import Flask
from clean_caisse.history_modifier import register_history_modifier
from clean_caisse.paid_order_reopen_isolated_phase5 import register_paid_order_reopen_isolated_phase5


class PendingEditTests(unittest.TestCase):
    def setUp(self):
        self.order = {'id':'order-1','num':60,'status':'Enregistrée','paid_amount':0,
                      'payment_status':'À ENCAISSER','z_closure_id':None,'sales_channel':'RESTO','total':17.5}
        self.items = [{'line_id':'burger-1','product_id':'burger','name':'Bacon burger','qty':1,
                       'unit_price':17.5,'options':[{'name':'À point'}]},
                      {'line_id':'coke-1','product_id':'coke','name':'Coca','qty':1,'unit_price':3,'options':[]}]
        self.writes=[]
        owner=self
        class Result:
            def __init__(self,row):self.row=row
            def fetchone(self):return self.row
        class Conn:
            @contextmanager
            def transaction(self):yield
            def commit(self):pass
            def execute(self,sql,params=()):
                if sql.lstrip().startswith('SELECT'):
                    return Result(copy.deepcopy(owner.order))
                owner.writes.append((sql,params))
                return Result(None)
        @contextmanager
        def db():yield Conn()
        self.app=Flask(__name__)
        register_history_modifier(self.app,db,lambda c:None,lambda c,o:o)
        register_paid_order_reopen_isolated_phase5(self.app,db,lambda c:None)

    def update(self,context='pos_before_kitchen'):
        return self.app.test_client().put('/api/orders/order-1',json={'items':self.items,'edit_context':context})

    def test_pending_edit_keeps_number_and_does_not_admit_to_kitchen(self):
        response=self.update();data=response.get_json()
        self.assertEqual(response.status_code,200)
        self.assertEqual((data['id'],data['num'],data['total'],data['status']),('order-1',60,20.5,'Enregistrée'))
        self.assertFalse(data['kitchen_resend'])
        updates=[params for sql,params in self.writes if sql.lstrip().startswith('UPDATE caisse_orders')]
        self.assertEqual(len(updates),1)
        self.assertEqual(updates[0][1],'Enregistrée')
        self.assertFalse(updates[0][2])
        self.assertFalse(json.loads(updates[0][3])['kitchen_resend'])
        self.assertFalse(any('INSERT INTO caisse_orders' in sql for sql,_ in self.writes))
        lines=[params for sql,params in self.writes if 'INSERT INTO caisse_order_items' in sql]
        self.assertEqual([params[1] for params in lines],['burger-1','coke-1'])
        self.assertEqual(json.loads(lines[0][6]),[{'name':'À point'}])

    def test_server_rejects_changed_status_payment_closure_and_site_before_writing(self):
        original=copy.deepcopy(self.order)
        for changes in [{'status':'À préparer'},{'status':'Terminée','paid_amount':17.5},
                        {'paid_amount':1},{'payment_status':'PAYÉE'},{'z_closure_id':3},{'sales_channel':'SITE'}]:
            self.order={**original,**changes};self.writes=[]
            self.assertEqual(self.update().status_code,409,changes)
            self.assertEqual(self.writes,[],changes)

    def test_existing_history_update_still_admits_to_kitchen(self):
        data=self.update('history').get_json()
        self.assertEqual(data['status'],'À préparer')
        self.assertTrue(data['kitchen_resend'])

    def test_browser_updates_same_order_without_creating_or_printing(self):
        script=r'''
const vm=require('vm'),fs=require('fs'),assert=require('assert');
const calls=[],alerts=[];let handler,saveButton,failSave=true;
const message={html:'',querySelector(){return null},set innerHTML(s){this.html=s},get innerHTML(){return this.html}};
const document={readyState:'complete',getElementById(id){return id==='order-message'?message:null},querySelector(){return saveButton},addEventListener(name,fn){if(name==='click')handler=fn}};
const context={document,window:{addEventListener(){}},setTimeout:fn=>fn(),MutationObserver:class{observe(){}},confirm:()=>true,alert:s=>alerts.push(s),
LAST_SAVED_ORDER:{id:'order-1',num:60,status:'Enregistrée',total:17.5},ORDER:[],renderOrder(){saveButton={dataset:{},removeAttribute(){},textContent:'',disabled:false}},saveOrder(){throw Error('Must not create another order')},
fetch:async(url,options)=>{calls.push({url,options});let data;
if(options.method==='PUT'&&failSave)return {ok:false,json:async()=>({ok:false,error:'La commande a changé d’état'})};
if(options.method==='PUT')data={ok:true,id:'order-1',num:60,total:20.5,status:'Enregistrée',kitchen_resend:false};
else if(url.endsWith('payment-phase41'))data={ok:true,order:{paid_amount:0,payment_status:'À ENCAISSER',z_locked:false}};
else data={ok:true,order:{id:'order-1',num:60,status:'Enregistrée',customer_name:'Client réel',items:[{line_id:'burger-1',name:'Bacon burger',qty:1,unit_price:17.5,options:[{name:'À point'}]}]}};
return {ok:true,json:async()=>data};}};
vm.createContext(context);vm.runInContext(fs.readFileSync('clean_caisse/static/pos-pending-edit.js','utf8'),context);
(async()=>{
await context.window.bechefaaPendingEdit.open();assert(context.window.bechefaaPendingEdit.isEditing());assert.equal(context.ORDER[0].options[0].name,'À point');
assert.equal(saveButton.textContent,'Enregistrer les modifications');
let prevented=false;handler({target:{closest:selector=>selector.includes('.pos-ref-pay')?{}:null},preventDefault(){prevented=true},stopImmediatePropagation(){}});assert(prevented);
context.ORDER.push({name:'Coca',product_id:'coke',qty:1,unit_price:3,options:[]});
await context.window.bechefaaPendingEdit.save();assert(context.window.bechefaaPendingEdit.isEditing());assert.equal(context.ORDER.length,2);assert.equal(context.LAST_SAVED_ORDER.total,17.5);
failSave=false;
await context.window.bechefaaPendingEdit.save();assert(!context.window.bechefaaPendingEdit.isEditing());assert.equal(context.LAST_SAVED_ORDER.id,'order-1');assert.equal(context.ORDER.length,0);
const writes=calls.filter(c=>c.options.method==='PUT');assert.equal(writes.length,2);assert.equal(writes[0].url,'/api/orders/order-1');
const payload=JSON.parse(writes[0].options.body);assert.equal(payload.edit_context,'pos_before_kitchen');assert.equal(payload.items.length,2);assert(payload.items[1].line_id);
assert(!calls.some(c=>c.options.method==='POST'||c.url.includes('epson')||c.url.includes('send-kitchen')));
assert(message.html.includes('Envoyer en cuisine'));
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        subprocess.run(['node','-e',script],check=True,capture_output=True)

if __name__=='__main__':unittest.main()
