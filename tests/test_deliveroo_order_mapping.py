import unittest

from clean_caisse.deliveroo_order_mapping_phase6 import (
    DeliverooMappingError, parse_order_new,
)


class DeliverooMappingTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "event": "order.new",
            "body": {"order": {
                "id": "fr:f5a2e989-c72c-47ae-9652-d75b3c50fdf1",
                "display_id": "7866", "location_id": "101",
                "brand_id": "bceaa87a-74db-434e-b548-6da7e7de67a6",
                "status": "placed", "fulfillment_type": "deliveroo",
                "total_price": {"fractional": 895, "currency_code": "EUR"},
                "items": [{
                    "pos_item_id": "MU11002", "name": "Veggie Burger (V)",
                    "quantity": 1,
                    "unit_price": {"fractional": 800, "currency_code": "EUR"},
                    "total_price": {"fractional": 895, "currency_code": "EUR"},
                    "modifiers": [{
                        "pos_item_id": "OM21001", "name": "Guacamole",
                        "quantity": 1,
                        "unit_price": {"fractional": 95, "currency_code": "EUR"},
                    }],
                }],
            }},
        }

    def test_deliveroo_sandbox_example(self):
        result = parse_order_new(self.payload)
        self.assertEqual(result["display_id"], "7866")
        self.assertEqual(result["total_eur"], "8.95")
        self.assertEqual(result["items"][0]["modifiers"][0]["unit_price_eur"], "0.95")
        self.assertFalse(result["writes"])

    def test_wrong_event_rejected(self):
        self.payload["event"] = "order.status_update"
        with self.assertRaises(DeliverooMappingError):
            parse_order_new(self.payload)

    def test_missing_items_rejected(self):
        self.payload["body"]["order"]["items"] = []
        with self.assertRaises(DeliverooMappingError):
            parse_order_new(self.payload)


if __name__ == "__main__":
    unittest.main()
