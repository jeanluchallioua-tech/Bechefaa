import unittest
from clean_caisse.deliveroo_order_reconcile_phase6 import reconcile
from clean_caisse.deliveroo_order_mapping_phase6 import DeliverooMappingError


def sample():
    return {
        "event": "order.new",
        "body": {"order": {
            "id": "fr:test-7866",
            "display_id": "7866",
            "total_price": {"fractional": 895, "currency_code": "EUR"},
            "items": [{
                "pos_item_id": "MU11002",
                "name": "Veggie Burger",
                "quantity": 1,
                "unit_price": {"fractional": 800, "currency_code": "EUR"},
                "total_price": {"fractional": 895, "currency_code": "EUR"},
                "modifiers": [{
                    "pos_item_id": "opt:MU11002:0:0",
                    "name": "Guacamole",
                    "quantity": 1,
                    "unit_price": {"fractional": 95, "currency_code": "EUR"},
                }],
            }],
        }},
    }


class DeliverooReconcileTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"products": [{
            "id": "MU11002", "name": "Veggie Burger", "active": True,
            "options": [{"name": "Suppléments", "options": [{"name": "Guacamole", "price": 0.95}]}],
        }]}

    def test_valid_product_and_modifier(self):
        result = reconcile(sample(), self.catalog)
        self.assertEqual(result["mapped_items"][0]["options"], [
            {"group": "Suppléments", "name": "Guacamole"}])
        self.assertFalse(result["writes"])
        self.assertTrue(result["requires_price_policy"])

    def test_unknown_product_rejected(self):
        payload = sample()
        payload["body"]["order"]["items"][0]["pos_item_id"] = "UNKNOWN"
        with self.assertRaises(DeliverooMappingError):
            reconcile(payload, self.catalog)

    def test_negative_or_noncanonical_option_indices_rejected(self):
        for plu in ("opt:MU11002:-1:0", "opt:MU11002:0:-1",
                    "opt:MU11002:+0:0", "opt:MU11002:00:0",
                    "opt:MU11002:0:00", "opt:MU11002:０:0"):
            with self.subTest(plu=plu):
                payload = sample()
                payload["body"]["order"]["items"][0]["modifiers"][0]["pos_item_id"] = plu
                with self.assertRaises(DeliverooMappingError):
                    reconcile(payload, self.catalog)

    def test_unrecognized_modifier_rejected(self):
        payload = sample()
        payload["body"]["order"]["items"][0]["modifiers"][0]["pos_item_id"] = "OM21001"
        with self.assertRaises(DeliverooMappingError):
            reconcile(payload, self.catalog)


if __name__ == "__main__":
    unittest.main()
