import base64
import copy
import unittest
from xml.etree import ElementTree as ET
from clean_caisse.epson_epos_network_phase6 import (_kitchen_xml, _client_xml,
    _combined_xml, _option_text, _wrapped_lines)
from clean_caisse.printing_phase1 import _option_lines

class ReceiptLayoutTests(unittest.TestCase):
    def setUp(self):
        self.order = {'total':34, 'customer_name':'Client test', 'items':[
            {'qty':1,'name':'Sandwich Fait ton sandwich','unit_price':16.5,
             'options_text':'Cuisson::À point;;Ingrédients::Avec cornichons | Sans tomates;;Sauce::Sans barbecue'},
            {'qty':1,'name':'Bacon Burger','unit_price':17.5,
             'options':[{'group':'Cuisson','name':'À point'}]}]}
    def test_compact_values_and_original_order_preserved(self):
        before = copy.deepcopy(self.order)
        self.assertEqual(_option_text(self.order['items'][0]),
            'À point · Avec cornichons · Sans tomates · Sans barbecue')
        _kitchen_xml(self.order); _client_xml(self.order)
        self.assertEqual(before,self.order)
    def test_wrap_preserves_whole_words(self):
        lines = _wrapped_lines('1 x Sandwich Fait ton sandwich',24)
        self.assertEqual(lines,['1 x Sandwich Fait ton','sandwich'])
    def test_raster_dimensions_and_payload(self):
        root = ET.fromstring(_kitchen_xml(self.order))
        images = root.findall('{*}image')
        self.assertEqual(len(images),2)
        for node in images:
            w,h=int(node.attrib['width']),int(node.attrib['height'])
            self.assertEqual(len(base64.b64decode(node.text)),(w//8)*h)
            self.assertGreater(sum(base64.b64decode(node.text)),0)
    def test_client_price_stays_on_product_line(self):
        root=ET.fromstring(_client_xml(self.order))
        texts=[n.text or '' for n in root.findall('{*}text')]
        self.assertTrue(any('Bacon Burger' in x and '17,50 EUR' in x for x in texts))
        self.assertTrue(any('34,00 EUR' in x for x in texts))
    def test_combined_still_cuts_two_tickets(self):
        root=ET.fromstring(_combined_xml(self.order))
        self.assertEqual(len(root.findall('{*}cut')),2)
    def test_html_single_options_block_and_escape(self):
        html=_option_lines({'options':[{'name':'Sans <tomates>'},{'name':'À point'}]})
        self.assertEqual(html.count('<div'),1)
        self.assertIn('Sans &lt;tomates&gt; · À point',html)

if __name__ == '__main__': unittest.main()
