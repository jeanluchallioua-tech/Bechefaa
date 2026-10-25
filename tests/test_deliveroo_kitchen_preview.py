import unittest

from clean_caisse.deliveroo_kitchen_preview_phase6 import preview_order
from clean_caisse.deliveroo_order_mapping_phase6 import DeliverooMappingError
from tests.test_deliveroo_order_reconcile import sample


class DeliverooKitchenPreviewTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"products": [{
            "id": "MU11002", "name": "Veggie Burger", "active": True,
            "options": [{"name": "Extras", "options": [{"name": "Guacamole"}]}],
        }]}

    def test_preview_preserves_quantity_and_origin_without_dispatch(self):
        payload = sample()
        payload["body"]["order"]["display_id"] = "7866"
        payload["body"]["order"]["items"][0]["quantity"] = 2
        payload["body"]["order"]["items"][0]["modifiers"][0]["quantity"] = 3
        result = preview_order(payload, self.catalog)
        self.assertEqual(result["origin"]["print_header"], "COMMANDE DELIVEROO - 7866")
        self.assertEqual(result["items"][0]["quantity"], 2)
        self.assertEqual(result["items"][0]["options"], [
            {"group": "Extras", "name": "Guacamole", "quantity": 3}
        ])
        self.assertFalse(result["writes"])
        self.assertFalse(result["ready_for_dispatch"])
        self.assertTrue(result["requires_price_policy"])
        self.assertEqual(result["display_id"], "7866")
        self.assertFalse(result["instructions_verified"])

    def test_explicit_legacy_mapping_previews_kitchen_without_dispatch(self):
        payload = sample()
        payload["body"]["order"]["display_id"] = "7866"
        payload["body"]["order"]["items"][0]["modifiers"][0]["pos_item_id"] = "OM21001"
        payload["body"]["order"]["items"][0]["modifiers"][0]["quantity"] = 2
        result = preview_order(
            payload, self.catalog, {("MU11002", "OM21001"): "opt:MU11002:0:0"}
        )
        self.assertEqual(result["origin"]["print_header"], "COMMANDE DELIVEROO - 7866")
        self.assertEqual(result["items"][0]["options"], [
            {"group": "Extras", "name": "Guacamole", "quantity": 2}
        ])
        self.assertFalse(result["ready_for_dispatch"])
        self.assertFalse(result["writes"])

    def test_unapproved_legacy_mapping_blocks_kitchen_preview(self):
        payload = sample()
        payload["body"]["order"]["items"][0]["modifiers"][0]["pos_item_id"] = "OM21001"
        with self.assertRaisesRegex(DeliverooMappingError, "Unapproved"):
            preview_order(payload, self.catalog, {})

    def test_unmatched_sandbox_modifier_blocks_preview(self):
        payload = sample()
        payload["body"]["order"]["items"][0]["modifiers"][0]["pos_item_id"] = "OM21001"
        with self.assertRaises(DeliverooMappingError):
            preview_order(payload, self.catalog)


if __name__ == "__main__":
    unittest.main()
