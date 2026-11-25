import unittest
from flask import Flask, Response
from clean_caisse.active_cart_protection_phase6 import register_active_cart_protection_phase6

class ActiveCartInjectionTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__)
        @self.app.get('/pos')
        def pos():return '<html><body><div id="order">Panier courant</div></body></html>'
        @self.app.get('/other')
        def other():return '<html><body>Autre écran</body></html>'
        register_active_cart_protection_phase6(self.app)
        self.client=self.app.test_client()

    def test_pos_gets_exactly_one_draft_script_preserving_existing_markup(self):
        response=self.client.get('/pos')
        self.assertEqual(response.status_code,200)
        self.assertIn('<div id="order">Panier courant</div>',response.text)
        self.assertEqual(response.text.count('id="pos-active-cart-protection"'),1)
        self.assertIn('/static/pos-active-cart.js?v=20261125',response.text)

    def test_other_pages_are_not_modified(self):
        self.assertNotIn('pos-active-cart',self.client.get('/other').text)

if __name__=='__main__':unittest.main()
