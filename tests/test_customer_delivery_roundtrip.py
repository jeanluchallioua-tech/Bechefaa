"""Exercise form API fields through actual persistence and the print endpoint."""
import ast
import json
import re
import sqlite3
import time
import unittest
import uuid
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from unittest.mock import patch
from flask import Flask, Response, jsonify, request
from clean_caisse.customer_phase1 import register_customer_phase1
from clean_caisse.clients_management_isolated_phase6 import register_clients_management_isolated_phase6, _import_client_rows
from clean_caisse.epson_epos_network_phase6 import register_epson_epos_network_phase6
from clean_caisse.receipt_photo_layout import Paper


class SqliteAdapter:
    """Execute the SQL using SQLite; translate only PostgreSQL-specific syntax."""
    def __init__(self):
        self.raw=sqlite3.connect(':memory:')
        self.raw.row_factory=lambda c,r:dict(zip([d[0] for d in c.description],r))
    def execute(self,sql,params=()):
        if sql.startswith('LOCK TABLE'):return self.raw.execute('SELECT 1')
        add=re.match(r'ALTER TABLE (\w+) ADD COLUMN IF NOT EXISTS (\w+) (.*)',sql,re.S)
        if add:
            table,column,kind=add.groups()
            if any(r['name']==column for r in self.raw.execute('PRAGMA table_info('+table+')')):
                return self.raw.execute('SELECT 1')
            sql=f'ALTER TABLE {table} ADD COLUMN {column} {kind}'
        sql=sql.replace("::jsonb",'').replace('::bigint','').replace('::text','').replace('ILIKE','LIKE')
        sql=sql.replace('(EXTRACT(EPOCH FROM NOW())*1000)',str(int(time.time()*1000)))
        return self.raw.execute(sql.replace('%s','?'),tuple(float(v) if isinstance(v,Decimal) else v for v in params))
    def commit(self):self.raw.commit()
    @contextmanager
    def transaction(self):
        try:yield;self.raw.commit()
        except Exception:self.raw.rollback();raise


class CustomerDeliveryRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.conn=SqliteAdapter()
        @contextmanager
        def db():yield self.conn
        source=ast.parse((Path(__file__).parents[1]/'clean_caisse/app.py').read_text())
        names=['ensure_order_schema','ticket_type','create_order','order_payload']
        nodes=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in names]
        for node in nodes:node.decorator_list=[]
        env={'__package__':'clean_caisse','request':request,'jsonify':jsonify,'db':db,'Decimal':Decimal,
             'InvalidOperation':InvalidOperation,'time':time,'uuid':uuid,'json':json}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'order_api','exec'),env)
        self.ensure=env['ensure_order_schema'];self.ensure(self.conn);self.conn.commit()
        self.app=Flask(__name__)
        self.app.add_url_rule('/api/orders',view_func=env['create_order'],methods=['POST'])
        self.app.add_url_rule('/pos',view_func=lambda:Response('<body><aside class="cart"><div class="ticket-choice"></div></aside></body>',mimetype='text/html'))
        register_customer_phase1(self.app,db,self.ensure)
        register_clients_management_isolated_phase6(self.app,db,self.ensure)
        register_epson_epos_network_phase6(self.app,db,self.ensure,env['order_payload'])
        self.client=self.app.test_client()
        self.customer={'first_name':'Jean','last_name':'Dupont','phone':'0612345678',
            'address':'12 rue des Tests','postal_code':'94120','city':'Fontenay-sous-Bois',
            'door_intercom':'A123 / DUPONT','floor':'3e étage','instructions':'Porte à gauche\nSonner deux fois'}
    def test_create_edit_order_and_print_preserve_every_delivery_field(self):
        created=self.client.post('/api/clients',json=self.customer)
        self.assertEqual(created.status_code,200,created.get_json())
        cid=created.get_json()['client']['id']
        row=self.client.get('/api/clients').get_json()['clients'][0]
        for key in ['floor','instructions','door_intercom','phone']:self.assertEqual(row[key],self.customer[key])
        updated={**self.customer,'floor':'4e étage','instructions':'Ascenseur B, puis porte droite'}
        saved=self.client.put('/api/clients/'+cid,json=updated)
        self.assertEqual(saved.status_code,200,saved.get_json())
        row=self.client.get('/api/clients').get_json()['clients'][0]
        self.assertEqual(row['floor'],'4e étage');self.assertEqual(row['instructions'],updated['instructions'])
        order=self.client.post('/api/orders',json={'service_mode':'LIVRAISON','customer':row,
            'items':[{'name':'Burger','unit_price':12,'qty':1}]})
        self.assertEqual(order.status_code,201,order.get_json())
        self.assertNotIn('customer_warning',order.get_json())
        oid=order.get_json()['id']
        # Reprinting must complete older orders even when their saved phone/details are blank.
        self.conn.execute("UPDATE caisse_orders SET phone='',delivery_details='{}' WHERE id=%s",(oid,));self.conn.commit()
        calls=[];original=Paper.text
        def record(paper,text='',**kwargs):calls.append(str(text));return original(paper,text,**kwargs)
        with patch.object(Paper,'text',record):
            printed=self.client.get('/api/epson/client-xml/'+oid)
        self.assertEqual(printed.status_code,200,printed.get_data(as_text=True))
        content='\n'.join(calls)
        for value in ['Tél. : 0612345678','A123 / DUPONT','Étage: 4e étage','Ascenseur B, puis porte droite']:
            self.assertIn(value,content)
        snapshot=json.loads(self.conn.execute('SELECT delivery_details FROM caisse_orders WHERE id=%s',(oid,)).fetchone()['delivery_details'])
        self.assertEqual(snapshot,{})  # printing reads data; it does not rewrite orders
        # Older orders may also predate customer linking: only an unambiguous
        # exact identity/address match is eligible to complete the ticket.
        self.conn.execute('UPDATE caisse_orders SET customer_id=NULL WHERE id=%s',(oid,));self.conn.commit()
        calls.clear()
        with patch.object(Paper,'text',record):
            printed=self.client.get('/api/epson/client-xml/'+oid)
        self.assertEqual(printed.status_code,200)
        self.assertIn('Tél. : 0612345678','\n'.join(calls))
        self.conn.execute("INSERT INTO caisse_clients SELECT 'ambiguous-client',first_name,last_name,display_name,'0699999999',email,address,postal_code,city,door_intercom,notes,created_at,updated_at,floor,instructions FROM caisse_clients WHERE id=%s",(cid,));self.conn.commit()
        calls.clear()
        with patch.object(Paper,'text',record):
            printed=self.client.get('/api/epson/client-xml/'+oid)
        self.assertEqual(printed.status_code,200)
        self.assertNotIn('0612345678','\n'.join(calls));self.assertNotIn('0699999999','\n'.join(calls))
    def test_admin_can_clear_new_fields_and_older_payloads_do_not_erase_them(self):
        cid=self.client.post('/api/clients',json=self.customer).get_json()['client']['id']
        old={k:v for k,v in self.customer.items() if k not in ('floor','instructions')}
        self.assertEqual(self.client.put('/api/clients/'+cid,json=old).status_code,200)
        row=self.client.get('/api/clients').get_json()['clients'][0]
        self.assertEqual(row['floor'],'3e étage')
        self.client.put('/api/clients/'+cid,json={**old,'floor':'','instructions':''})
        row=self.client.get('/api/clients').get_json()['clients'][0]
        self.assertEqual(row['floor'],'');self.assertEqual(row['instructions'],'')
    def test_import_accepts_and_retains_the_new_fields(self):
        with self.conn.transaction():_import_client_rows(self.conn,[self.customer])
        with self.conn.transaction():_import_client_rows(self.conn,[{'phone':self.customer['phone'],'first_name':'Jean'}])
        row=self.client.get('/api/clients').get_json()['clients'][0]
        self.assertEqual(row['floor'],'3e étage');self.assertEqual(row['instructions'],self.customer['instructions'])
    def test_both_customer_forms_expose_floor_and_instructions(self):
        pos=self.client.get('/pos').get_data(as_text=True)
        page=self.client.get('/clients').get_data(as_text=True)
        self.assertIn('id="cust-floor"',pos);self.assertIn('id="cust-instructions"',pos)
        self.assertIn('id="f_floor"',page);self.assertIn('id="f_instructions"',page)

if __name__=='__main__':unittest.main()
