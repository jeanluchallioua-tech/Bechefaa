import copy
import sys
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask
from clean_caisse.uber_sandbox_link import STORE_ID
from clean_caisse.uber_sandbox_pos_display import PREPROD_HOST
from clean_caisse.uber_sandbox_receipts import receipt_order, register_uber_sandbox_receipts

ORDER = '01460685-2d3d-4d79-af00-4eaba3384a34'
BASE = 'https://' + PREPROD_HOST


class UberTestReceiptTests(unittest.TestCase):
    def setUp(self):
        eur = lambda n: {'amount': n, 'currency_code': 'EUR'}
        self.summary = {'id': ORDER, 'store_id': STORE_ID, 'display_id': '84A34', 'current_state': 'ACCEPTED',
            'charges': {'total': eur(4200), 'tax': None}, 'items': [
                {'title': 'Classic Burger', 'quantity': 2, 'total_price': eur(4200), 'options': [
                    {'title': 'Barbecue', 'quantity': 1, 'unit_price': eur(120), 'options': []},
                    {'title': 'Oignons', 'quantity': 1, 'removed': True, 'options': []}]}]}
        self.db = MagicMock()
        self.conn = self.db.return_value.__enter__.return_value
        self.cur = self.conn.cursor.return_value.__enter__.return_value
        self.cur.fetchone.side_effect = [(True,), (self.summary,), (False,)]
        app = Flask(__name__)
        app.secret_key = 'test'
        register_uber_sandbox_receipts(app, self.db)
        self.client = app.test_client()
        with self.client.session_transaction(base_url=BASE) as s:
            s['caisse_auth'] = True
        self.path = '/administration/uber-sandbox/receipts/' + ORDER

    def test_prices_include_modifiers_exactly_once_and_snapshot_is_unchanged(self):
        before = copy.deepcopy(self.summary)
        order = receipt_order(self.summary)
        self.assertEqual(order['items'][0]['unit_price'], Decimal('21'))
        self.assertEqual(order['total_ttc'], Decimal('42'))
        self.assertEqual(order['items'][0]['options'], [{'name':'Barbecue'}, {'name':'Sans Oignons'}])
        self.assertEqual(order['payment'], 'UBER TEST — HORS VENTES')
        self.assertEqual(order['source'], 'LIVRAISON')
        self.assertEqual(self.summary, before)

    def test_missing_amount_or_other_store_never_produces_zero_price_receipt(self):
        for mutate in (lambda s:s.update(store_id='other'), lambda s:s['items'][0].update(total_price=None),
                       lambda s:s['charges']['total'].update(currency_code='USD')):
            bad=copy.deepcopy(self.summary);mutate(bad)
            with self.assertRaises(ValueError): receipt_order(bad)

    def test_preview_exposes_both_images_and_tax_assumption_without_printing(self):
        response=self.client.get(self.path,base_url=BASE)
        self.assertEqual(response.status_code,200)
        self.assertIn(self.path+'/kitchen.png',response.text)
        self.assertIn(self.path+'/client.png',response.text)
        self.assertIn('10 %',response.text)
        self.assertNotIn('tmprintassistant',response.text)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertTrue(all(c.args[0].startswith('SELECT') for c in self.cur.execute.call_args_list))
        self.conn.commit.assert_not_called()

    def test_image_uses_existing_locked_renderer_and_identity(self):
        self.cur.fetchone.side_effect=[(True,),(self.summary,),(True,)]
        self.cur.fetchall.return_value=[('name','BECHEFAA'),('siret','123')]
        renderer=MagicMock(return_value=b'PNG test')
        with patch.dict(sys.modules,{'clean_caisse.receipt_photo_layout':SimpleNamespace(receipt_png=renderer)}):
            response=self.client.get(self.path+'/client.png',base_url=BASE)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.mimetype,'image/png')
        order,kind,identity=renderer.call_args.args
        self.assertEqual(kind,'client');self.assertEqual(identity['name'],'BECHEFAA')
        self.assertEqual(order['items'][0]['unit_price'],21)
        self.conn.commit.assert_not_called()

    def test_wrong_host_missing_session_and_invalid_id_do_not_touch_database(self):
        self.assertEqual(self.client.get(self.path,base_url='https://caisse.bechefaa.fr').status_code,404)
        self.assertEqual(self.client.get(self.path+'/other.png',base_url=BASE).status_code,404)
        self.assertEqual(self.client.get(self.path.replace(ORDER,'bad'),base_url=BASE).status_code,400)
        with self.client.session_transaction(base_url=BASE) as s:s.clear()
        self.assertEqual(self.client.get(self.path,base_url=BASE).status_code,403)
        self.db.assert_not_called()

    def test_unimported_or_corrupt_snapshot_is_not_previewed(self):
        self.cur.fetchone.side_effect=[(True,),None]
        self.assertEqual(self.client.get(self.path,base_url=BASE).status_code,404)
        self.cur.fetchone.side_effect=[(True,),({'id':'wrong'},)]
        self.assertEqual(self.client.get(self.path,base_url=BASE).status_code,503)


if __name__=='__main__':unittest.main()
