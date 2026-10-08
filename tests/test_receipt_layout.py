import base64
import copy
import io
import unittest
from xml.etree import ElementTree as ET
from PIL import Image
from flask import Flask
from clean_caisse.epson_epos_network_phase6 import _kitchen_xml, _client_xml, _combined_xml
from clean_caisse.receipt_photo_layout import render_receipt, receipt_png, option_groups, option_values
from clean_caisse.printing_phase1 import register_printing_phase1

class ReceiptLayoutTests(unittest.TestCase):
    def setUp(self):
        self.order = {'num':60,'total':34,'customer_name':'Shaïlie Guez','items':[
            {'qty':1,'name':'Sandwich "Fait ton sandwich"','unit_price':16.5,
             'options_text':'Choix de cuisson::À point;;Sans les ingredients::Sans tomates'},
            {'qty':1,'name':'Bacon Burger','unit_price':17.5,'options':[{'group':'Cuisson','name':'À point'}]}]}
    def test_distinct_option_layouts_preserve_order(self):
        before=copy.deepcopy(self.order)
        self.assertEqual(option_groups(self.order['items'][0]),['Choix de cuisson: À point','Sans les ingredients: Sans tomates'])
        self.assertEqual(option_values(self.order['items'][0]),['À point','Sans tomates'])
        _kitchen_xml(self.order); _client_xml(self.order)
        self.assertEqual(before,self.order)
    def test_preview_pixels_equal_all_printer_raster_bytes(self):
        for kind, fn in [('kitchen',_kitchen_xml),('client',_client_xml)]:
            root=ET.fromstring(fn(self.order))
            actual=b''.join(base64.b64decode(n.text) for n in root.findall('{*}image'))
            paper=render_receipt(self.order,kind)
            self.assertEqual(actual,paper.tobytes())
            png=Image.open(io.BytesIO(receipt_png(self.order,kind)))
            self.assertEqual(png.size,paper.size)
            self.assertEqual(png.point(lambda p:0 if p else 255).tobytes(),actual)
            for node in root.findall('{*}image'):
                self.assertLessEqual(int(node.attrib['height']),512)
    def test_combined_still_cuts_two_tickets(self):
        root=ET.fromstring(_combined_xml(self.order))
        self.assertEqual(len(root.findall('{*}cut')),2)
    def test_approved_text_and_conditional_identity(self):
        from unittest.mock import patch
        from clean_caisse.receipt_photo_layout import Paper
        identity={'siret':'SIRET-TEST','vat_number':'TVA-TEST'}
        for mode in ['COMPTOIR','SALLE','LIVRAISON']:
            order=copy.deepcopy(self.order)
            order['source']=mode
            order['table_number']=2 if mode=='SALLE' else None
            order['customer_name']='Autre client réel'
            for kind in ['client','kitchen']:
                calls=[]
                original=Paper.text
                def record(paper,text='',**kwargs):
                    calls.append(str(text));return original(paper,text,**kwargs)
                with patch.object(Paper,'text',record): render_receipt(order,kind,identity)
                content='\n'.join(calls)
                self.assertIn('Autre client réel',content)
                self.assertNotIn('Choix de cuisson',content)
                self.assertNotIn('Supplements',content)
                self.assertIn('  - À point',calls)
                self.assertIn('  - Sans tomates',calls)
                has_identity=kind=='client' and mode!='LIVRAISON'
                self.assertEqual('SIRET-TEST' in content,has_identity)
                self.assertEqual('TVA-TEST' in content,has_identity)
                if kind=='client':
                    self.assertTrue(any('Bacon Burger' in line and '17,50 €' in line for line in calls))

    def test_kitchen_name_is_compact_and_country_removed(self):
        from unittest.mock import patch
        from clean_caisse.receipt_photo_layout import Paper
        calls=[]
        original=Paper.text
        def record(paper,text='',**kwargs):
            calls.append((str(text),kwargs));return original(paper,text,**kwargs)
        with patch.object(Paper,'text',record):
            render_receipt(self.order,'kitchen')
            render_receipt(self.order,'client',{'address':'1 rue Émile Zola, France','city':'Fontenay-sous-Bois France'})
        content='\n'.join(x[0] for x in calls)
        self.assertNotIn('France',content)
        title=[x for x in calls if 'Fait ton sandwich' in x[0]][0]
        self.assertEqual(title[1].get('columns',48),48)
        self.assertIn('sandwich"',title[0])

    def test_long_ticket_is_chunked_without_pixel_loss(self):
        self.order['items']*=30
        root=ET.fromstring(_client_xml(self.order))
        self.assertGreater(len(root.findall('{*}image')),4)
        actual=b''.join(base64.b64decode(n.text) for n in root.findall('{*}image'))
        self.assertEqual(actual,render_receipt(self.order,'client').tobytes())

    def test_each_selection_has_its_own_line_and_words_remain_whole(self):
        from unittest.mock import patch
        from clean_caisse.receipt_photo_layout import Paper
        item={'qty':1,'name':'Sandwich Shawarma','unit_price':17.5,
              'options_text':'Cuisson::À point;;Sans ingredients::aubergine, choux blanc, tehina, houmous;;Garnitures::Cornichons, Oignons confits, Oignons rouge;;Sauces::Sauce américaine, Moutarde au miel'}
        expected=['À point','Sans aubergine','Sans choux blanc','Sans tehina','Sans houmous',
                  'Cornichons','Oignons confits','Oignons rouge','Sauce américaine','Moutarde au miel']
        self.assertEqual(option_values(item),expected)
        self.assertEqual(option_values({'options_text':'Supplément::Sauce à 1,50 €'}),['Sauce à 1,50 €'])
        for kind in ['kitchen','client']:
            calls=[]
            original=Paper.text
            def record(paper,text='',**kwargs):
                calls.append(str(text));return original(paper,text,**kwargs)
            with patch.object(Paper,'text',record):
                render_receipt(dict(self.order,items=[item]),kind)
                Paper().option('Sans aubergine et sans choux blanc avec une sauce tehina')
            for detail in expected:
                self.assertIn('  - '+detail,calls)
            self.assertTrue(all(len(line)<=48 for line in calls if line.startswith('  ')))
            self.assertIn('    sauce tehina',calls)

    def test_browser_preview_never_auto_prints(self):
        app=Flask(__name__)
        register_printing_phase1(app,None,None,None)
        client=app.test_client()
        for kind in ['client','cuisine']:
            html=client.get(f'/impression/{kind}/60?preview=1&auto=1').get_data(as_text=True)
            self.assertIn('/apercu/image-ticket/',html)
            self.assertNotIn('window.print()',html)
            self.assertNotIn('epos-print',html)

if __name__=='__main__':unittest.main()
