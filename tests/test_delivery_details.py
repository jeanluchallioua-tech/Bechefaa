import copy
import json
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from flask import Flask
from clean_caisse.customer_phase1 import _clean_customer, _upsert_and_attach
from clean_caisse.epson_epos_network_phase6 import register_epson_epos_network_phase6
from clean_caisse.receipt_photo_layout import Paper, render_receipt

class DeliveryDetailsTests(unittest.TestCase):
    def test_customer_values_are_saved_in_order_snapshot(self):
        writes=[]
        class Result:
            def fetchone(self):return {'notes':'Sonner deux fois'}
        class Conn:
            def execute(self,sql,params=()):writes.append((sql,params));return Result()
        customer=_clean_customer({'first_name':'Jean','door_intercom':'B123 / Dupont','floor':'3e',
                                  'instructions':'Ascenseur à gauche','building':'B'})
        with patch('clean_caisse.customer_phase1._save_customer',return_value=('client-1','Jean')):
            _upsert_and_attach(Conn(),'order-1',customer)
        update=next(p for sql,p in writes if sql.startswith('UPDATE caisse_orders'))
        details=json.loads(update[7])
        self.assertEqual(details,{'door_intercom':'B123 / Dupont','floor':'3e','building':'B',
                                  'instructions':'Ascenseur à gauche','notes':'Sonner deux fois'})
        self.assertEqual(update[-1],'order-1')

    def test_printer_loads_snapshot_or_legacy_profile(self):
        for snapshot,expected in [(None,'Ancien code'),({},None),({'door_intercom':'Code commande'},'Code commande')]:
            row={'id':'order-1','num':12,'source':'LIVRAISON','customer_id':'client-1','delivery_details':snapshot}
            reads=[]
            class Result:
                def __init__(self,row):self.row=row
                def fetchone(self):return self.row
            class Conn:
                def commit(self):pass
                def execute(self,sql,params=()):
                    if 'FROM caisse_orders WHERE' in sql:return Result(row)
                    if 'FROM caisse_clients WHERE' in sql:
                        reads.append(sql);return Result({'door_intercom':'Ancien code','notes':'Etage 2'})
                    return Result(None)
            @contextmanager
            def db():yield Conn()
            app=Flask(__name__)
            register_epson_epos_network_phase6(app,db,lambda c:None,lambda c,r:dict(r))
            with patch('clean_caisse.epson_epos_network_phase6._client_xml',side_effect=lambda order,identity:json.dumps(order)):
                response=app.test_client().get('/api/epson/client-xml/order-1')
            self.assertEqual(response.status_code,200)
            details=json.loads(response.get_data(as_text=True))['delivery_details']
            self.assertEqual(details.get('door_intercom'),expected)
            self.assertEqual(bool(reads),snapshot is None)

    def test_delivery_receipt_includes_each_field_only_on_client_ticket(self):
        order={'source':'LIVRAISON','items':[],'delivery_details':{'door_intercom':'B123 / Dupont',
               'floor':'3e','building':'B','instructions':'Ascenseur à gauche\nSonner deux fois'}}
        before=copy.deepcopy(order)
        for kind in ['client','kitchen']:
            calls=[]
            original=Paper.text
            def record(paper,text='',**kwargs):calls.append(str(text));return original(paper,text,**kwargs)
            with patch.object(Paper,'text',record):render_receipt(order,kind)
            content='\n'.join(calls)
            self.assertEqual('B123 / Dupont' in content,kind=='client')
            if kind=='client':
                self.assertIn('Étage: 3e',content)
                self.assertIn('Sonner deux fois',content)
                self.assertTrue(all(len(line)<=42 for line in calls if 'Consignes' in line))
        self.assertEqual(order,before)

if __name__=='__main__':unittest.main()
