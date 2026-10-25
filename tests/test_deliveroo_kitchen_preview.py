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

    def test_instruction_candidate_paths_are_diagnostic_only(self):
        payload = sample()
        payload["body"]["order"]["special_instructions"] = "Ne pas saler"
        payload["body"]["order"]["items"][0]["notes"] = "Bien cuit"
        result = preview_order(payload, self.catalog)
        self.assertEqual(result["instruction_field_audit"]["candidate_paths"], [
            "body.order.items[0].notes",
            "body.order.special_instructions",
        ])
        self.assertEqual(result["instruction_field_audit"]["candidate_values"], [
            {"path": "body.order.items[0].notes", "value": "Bien cuit"},
            {"path": "body.order.special_instructions", "value": "Ne pas saler"},
        ])
        self.assertFalse(result["instruction_field_audit"]["schema_verified"])
        self.assertFalse(result["instructions_verified"])
        self.assertFalse(result["ready_for_dispatch"])
        self.assertFalse(result["writes"])

    def test_instruction_audit_is_stable_across_repeated_calls(self):
        from clean_caisse.deliveroo_instruction_audit_phase6 import audit_instruction_fields
        payload = sample()
        payload["body"]["order"]["notes"] = "Sans sel"
        payload["body"]["order"]["instructions"] = "À emporter"
        payload["body"]["order"]["items"][0]["special_instructions"] = "Bien cuit"
        first = audit_instruction_fields(payload)
        self.assertEqual(first, audit_instruction_fields(payload))
        self.assertEqual(first["candidate_paths"], sorted(first["candidate_paths"]))
        self.assertEqual(
            [entry["path"] for entry in first["candidate_values"]],
            first["candidate_paths"],
        )
        self.assertFalse(first["schema_verified"])
        self.assertFalse(first["writes"])

    def test_modifier_notes_are_reported_but_not_automatically_dispatched(self):
        payload = sample()
        payload["body"]["order"]["items"][0]["modifiers"][0]["notes"] = "Sans piment"
        preview = preview_order(payload, self.catalog)
        audit = preview["instruction_field_audit"]
        self.assertEqual(audit["candidate_paths"], [
            "body.order.items[0].modifiers[0].notes",
        ])
        self.assertEqual(audit["candidate_values"], [{
            "path": "body.order.items[0].modifiers[0].notes",
            "value": "Sans piment",
        }])
        self.assertFalse(audit["schema_verified"])
        self.assertFalse(preview["instructions_verified"])
        self.assertFalse(preview["ready_for_dispatch"])
        self.assertFalse(preview["writes"])

    def test_amount_audit_is_read_only_and_does_not_approve_prices(self):
        payload = sample()
        result = preview_order(payload, self.catalog)
        audit = result["amount_audit"]
        self.assertEqual(audit["order_total_eur"], "8.95")
        self.assertEqual(audit["items_total_eur"], "8.95")
        self.assertTrue(audit["totals_match"])
        self.assertFalse(audit["price_policy_verified"])
        self.assertFalse(audit["ready_for_dispatch"])
        self.assertFalse(audit["writes"])
        payload["body"]["order"]["total_price"]["fractional"] = 1000
        mismatch = preview_order(payload, self.catalog)["amount_audit"]
        self.assertEqual(mismatch["difference_eur"], "1.05")
        self.assertFalse(mismatch["totals_match"])

    def test_unmatched_sandbox_modifier_blocks_preview(self):
        payload = sample()
        payload["body"]["order"]["items"][0]["modifiers"][0]["pos_item_id"] = "OM21001"
        with self.assertRaises(DeliverooMappingError):
            preview_order(payload, self.catalog)


if __name__ == "__main__":
    unittest.main()
