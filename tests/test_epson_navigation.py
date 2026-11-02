import re
import unittest
from urllib.parse import parse_qs,urlsplit
from flask import Flask
from clean_caisse.epson_epos_network_phase6 import _assistant_launch_html
from clean_caisse.printing_phase1 import register_printing_phase1

ANDROID={'User-Agent':'Mozilla/5.0 (Linux; Android 15) SamsungBrowser/28.0'}


class EpsonNavigationTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__)
        register_printing_phase1(self.app,None,None,None)

    def test_android_launcher_uses_explicit_epson_intent_without_timer_or_payload_change(self):
        xml='<?xml version="1.0"?><epos-print><text>Émile &amp; cuisine</text><cut/><text>Client</text><cut/></epos-print>'
        with self.app.test_request_context('/epson/print-order-pack/id?return_to=/historique-modification',headers=ANDROID):
            html=_assistant_launch_html(xml).get_data(as_text=True)
        url=re.search(r"window.location.href='([^']+)'",html).group(1)
        self.assertTrue(url.startswith('intent://tmprintassistant.epson.com/print?'))
        self.assertIn('scheme=tmprintassistant;package=com.epson.tmassistant;end',url)
        query=parse_qs(urlsplit(url).query)
        self.assertEqual(query['data'],[xml]);self.assertEqual(query['data-type'],['eposprintxml'])
        self.assertTrue(query['success'][0].endswith('/historique-modification?epson=success'))
        self.assertNotIn('setTimeout',html)
        self.assertIn('leftForAssistant&&!document.hidden',html)

    def test_return_path_cannot_redirect_outside_pos_or_history(self):
        with self.app.test_request_context('/epson/print-client/id?return_to=https://other.example',headers=ANDROID):
            html=_assistant_launch_html('<epos-print/>').get_data(as_text=True)
        self.assertNotIn('other.example',html)
        self.assertIn("replace('/pos')",html)

    def test_android_preview_print_button_uses_existing_epson_route_without_autoprint(self):
        with self.app.test_client() as client:
            for kind,route in [('client','client'),('cuisine','kitchen')]:
                html=client.get('/impression/'+kind+'/saved-id?preview=1&auto=1',headers=ANDROID).get_data(as_text=True)
                self.assertIn('/epson/print-'+route+'/saved-id',html)
                self.assertIn('>Imprimer</button>',html)
                self.assertNotIn('window.print()',html)
                self.assertNotIn('location.replace(',html)

    def test_desktop_print_dialog_is_preserved(self):
        with self.app.test_client() as client:
            html=client.get('/impression/client/saved-id').get_data(as_text=True)
        self.assertIn('window.print()',html)


if __name__=='__main__':unittest.main()
