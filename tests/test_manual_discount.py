import ast
import json
import subprocess
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import test_customer_delivery_roundtrip as roundtrip
from clean_caisse.manual_discount import discount_total
from clean_caisse.order_tax_snapshot_phase31 import register_order_tax_snapshot_phase31
from clean_caisse.payment_core_phase41 import register_payment_core_phase41
from clean_caisse.receipt_photo_layout import Paper

class ManualDiscountTests(unittest.TestCase):
    def setUp(self):
        roundtrip.CustomerDeliveryRoundTripTests.setUp(self)
        execute=self.conn.execute
        self.conn.execute=lambda sql,params=():execute(sql.replace(' FOR UPDATE',''),params)
    def create(self,amount=3,mode='EMPORTER'):
        return self.client.post('/api/orders',json={'customer':{'first_name':'Jean'},'service_mode':mode,'manual_discount_amount':amount,'items':[{'line_id':'l','product_id':'burger','name':'Burger','qty':2,'unit_price':15,'options':[]}]})
    def test_discount_round_trip_tax_edit_and_receipt(self):
        register_order_tax_snapshot_phase31(self.app,lambda: self.db_context())
        register_payment_core_phase41(self.app,lambda:self.db_context(),self.ensure)
        self.conn.execute('ALTER TABLE caisse_orders ADD COLUMN z_closure_id BIGINT NULL')
        response=self.create();self.assertEqual(response.status_code,201,response.get_json());data=response.get_json()
        self.assertEqual(data['total'],27);self.assertEqual(data['discount_amount'],3)
        oid=data['id'];payment=self.client.get('/api/orders/'+oid+'/payment-phase41');self.assertEqual(payment.status_code,200,payment.get_json());self.assertEqual(payment.get_json()['order']['total'],27)
        row=self.conn.execute('SELECT * FROM caisse_orders WHERE id=%s',(oid,)).fetchone()
        self.assertEqual(row['total_ttc'],27);self.assertEqual(row['total_ht'],24.55);self.assertEqual(row['tax_amount'],2.45)
        order=self.client.get('/api/orders/'+oid).get_json()['order']
        self.assertEqual(order['discount_amount'],3);self.assertEqual(order['items'][0]['unit_price'],15)
        # A regular history edit preserves the euro discount even without a discount field.
        items=order['items'];items[0]['qty']=3
        edit=self.client.put('/api/orders/'+oid,json={'items':items})
        self.assertEqual(edit.status_code,200,edit.get_json());self.assertEqual(edit.get_json()['total'],42)
        calls=[];original=Paper.price
        def record(p,label,amount,*a,**kw):calls.append((label,Decimal(str(amount))));return original(p,label,amount,*a,**kw)
        with patch.object(Paper,'price',record):
            printed=self.client.get('/api/epson/client-xml/'+oid)
        self.assertEqual(printed.status_code,200);self.assertIn(('Remise',Decimal('-3')),calls);self.assertIn(('Sous-total',Decimal('45')),calls)
        removed=self.client.put('/api/orders/'+oid,json={'items':items,'manual_discount_amount':0})
        self.assertEqual(removed.get_json()['total'],45);self.assertEqual(removed.get_json()['discount_amount'],0)
    def db_context(self):
        from contextlib import contextmanager
        @contextmanager
        def context():yield self.conn
        return context()
    def test_reject_bad_amount_scope_and_paid_changes(self):
        for amount in (-1,30,31,'NaN','Infinity','no'):
            self.assertEqual(self.create(amount).status_code,400,amount)
        self.assertEqual(self.create(3,'LIVRAISON').status_code,400)
        data=self.create().get_json();oid=data['id']
        self.conn.execute('ALTER TABLE caisse_orders ADD COLUMN paid_amount NUMERIC DEFAULT 0')
        self.conn.execute('UPDATE caisse_orders SET paid_amount=5 WHERE id=%s',(oid,));self.conn.commit()
        order=self.client.get('/api/orders/'+oid).get_json()['order']
        blocked=self.client.put('/api/orders/'+oid,json={'items':order['items'],'manual_discount_amount':4});self.assertEqual(blocked.status_code,409,blocked.get_json())
        self.assertEqual(self.conn.execute('SELECT total FROM caisse_orders WHERE id=%s',(oid,)).fetchone()['total'],27)
    def test_non_cumulative_and_decimal_comma(self):
        self.assertEqual(discount_total(Decimal('30'),'3,50','EMPORTER'),(Decimal('3.50'),Decimal('26.50')))
        for kwargs in ({'coupon_code':'YARON10'},{'sales_channel':'SITE'}):
            with self.assertRaises(ValueError):discount_total(Decimal('30'),3,'EMPORTER',**kwargs)
    def test_browser_cart_and_save_send_the_net_total(self):
        source=Path('clean_caisse/app.py').read_text()
        code=source[source.index('function setManualDiscount'):source.index('function sendKitchen(orderId,orderNum)')]
        script=r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
let body;const box={innerHTML:''},message={innerHTML:''};const nodes={'manual-discount-total':{textContent:''},'manual-discount-line':{textContent:''},'manual-discount-summary':{style:{}}};
const c={ORDER:[{unit_price:15,qty:2,name:'Burger',options:[]}],TICKET_TYPE:'Emporter',MANUAL_DISCOUNT:0,LAST_SAVED_ORDER:null,esc:String,alert:()=>{},CustomEvent:class{},document:{querySelector:()=>null,getElementById:id=>nodes[id]||(id==='order'?box:message),dispatchEvent(){}},fetch:async(u,o)=>{body=JSON.parse(o.body);return{ok:true,json:async()=>({ok:true,id:'a',num:1,total:27,discount_amount:3})}}};
vm.createContext(c);vm.runInContext(CODE,c);
(async()=>{c.setManualDiscount('3');const previous=box.innerHTML;let validity; c.previewManualDiscount({value:'4',setCustomValidity:v=>validity=v});assert.equal(validity,'');assert.equal(nodes['manual-discount-total'].textContent,'26,00 €');assert.equal(box.innerHTML,previous);c.previewManualDiscount({value:'99',setCustomValidity:v=>validity=v});assert(validity);c.setManualDiscount('3');assert(box.innerHTML.includes('27,00 €'));assert(box.innerHTML.includes('Remise'));await c.saveOrder();assert.equal(body.manual_discount_amount,3);assert.equal(c.ORDER.length,0);assert.equal(c.MANUAL_DISCOUNT,0);c.ORDER=[{unit_price:15,qty:2,name:'Burger',options:[]}];c.TICKET_TYPE='Salle';c.MANUAL_DISCOUNT=3;c.renderOrder();assert(!box.innerHTML.includes('id="manual-discount"'));assert(box.innerHTML.includes('30,00 €'));})().catch(e=>{console.error(e);process.exitCode=1});
'''.replace('CODE',json.dumps(code))
        subprocess.run(['node','-e',script],check=True,capture_output=True)
    def test_offline_total_is_discounted_without_changing_item_prices(self):
        from clean_caisse.offline_mode_phase6 import SW_JS
        functions=SW_JS[SW_JS.index('function totalOf('):SW_JS.index('function ticketType(')]
        script=functions+"\nconst assert=require('node:assert/strict');const body={items:[{qty:2,unit_price:15}],manual_discount_amount:3};assert.equal(totalOf(body),27);assert.equal(body.items[0].unit_price,15);"
        subprocess.run(['node','-e',script],check=True,capture_output=True)
if __name__=='__main__':unittest.main()
