"""Regression tests for sandbox identifiers vs BÉCHÉFAA menu-generated PLUs.

Run locally: python -m unittest tests.test_deliveroo_menu_plu_contract
No database, network, or POS writes.
"""
import unittest

from clean_caisse.deliveroo_menu_builder_phase6 import _safe_id
from clean_caisse.deliveroo_order_mapping_phase6 import DeliverooMappingError
from clean_caisse.deliveroo_order_reconcile_phase6 import reconcile


class DeliverooMenuPluContractTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"products": [{
            "id": "MU11002", "name": "Veggie Burger",
            "options": [{"name": "Extras", "options": [{"name": "Guacamole"}]}],
        }]}
        self.payload = {"event": "order.new", "body": {"order": {
            "id": "fr:example", "display_id": "7866",
            "total_price": {"currency_code": "EUR", "fractional": 895},
            "items": [{
                "pos_item_id": "MU11002", "name": "Veggie Burger",
                "quantity": 1,
                "unit_price": {"currency_code": "EUR", "fractional": 800},
                "total_price": {"currency_code": "EUR", "fractional": 895},
                "modifiers": [{
                    "pos_item_id": "OM21001", "name": "Guacamole",
                    "quantity": 1,
                    "unit_price": {"currency_code": "EUR", "fractional": 95},
                }],
            }],
        }}}

    def test_sandbox_modifier_is_not_our_generated_plu(self):
        with self.assertRaises(DeliverooMappingError):
            reconcile(self.payload, self.catalog)

    def test_generated_plu_can_be_reconciled(self):
        modifier = self.payload["body"]["order"]["items"][0]["modifiers"][0]
        modifier["pos_item_id"] = "opt:MU11002:0:0"
        mapped = reconcile(self.payload, self.catalog)
        self.assertEqual(mapped["mapped_items"][0]["options"], [
            {"group": "Extras", "name": "Guacamole"}
        ])
        self.assertFalse(mapped["writes"])

    def test_item_id_is_not_pos_plu(self):
        self.assertNotEqual(_safe_id("item", "MU11002"), "MU11002")


if __name__ == "__main__":
    unittest.main()
