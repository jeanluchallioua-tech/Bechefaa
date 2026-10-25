import unittest

from clean_caisse.deliveroo_plu_audit_phase6 import audit_order_plu
from tests.test_deliveroo_order_reconcile import sample


class DeliverooPluAuditTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"products": [{
            "id": "MU11002", "name": "Veggie Burger",
            "options": [{"name": "Extras", "options": [{"name": "Guacamole"}]}],
        }]}

    def test_legacy_sandbox_modifier_is_flagged_without_guessing(self):
        payload = sample()
        payload["body"]["order"]["items"][0]["modifiers"][0]["pos_item_id"] = "OM21001"
        result = audit_order_plu(payload, self.catalog)
        self.assertFalse(result["compatible"])
        self.assertFalse(result["writes"])
        self.assertFalse(result["auto_mapping"])
        self.assertEqual(result["findings"][0]["received_plu"], "OM21001")
        self.assertEqual(result["findings"][0]["expected_plu_format"],
                         "opt:MU11002:<group_index>:<choice_index>")

    def test_generated_modifier_is_compatible(self):
        result = audit_order_plu(sample(), self.catalog)
        self.assertTrue(result["compatible"])
        self.assertEqual(result["findings"], [])
        self.assertFalse(result["writes"])

    def test_unknown_product_is_flagged(self):
        payload = sample()
        payload["body"]["order"]["items"][0]["pos_item_id"] = "UNKNOWN"
        result = audit_order_plu(payload, self.catalog)
        self.assertEqual(result["findings"][0]["type"], "unknown_product")


if __name__ == "__main__":
    unittest.main()
