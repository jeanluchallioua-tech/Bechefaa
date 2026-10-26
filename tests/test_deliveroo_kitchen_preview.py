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

    def test_non_text_and_blank_instruction_candidates_remain_unverified(self):
        payload = sample()
        order = payload["body"]["order"]
        order["special_instructions"] = {"text": "Sans sel"}
        order["items"][0]["notes"] = "  "
        preview = preview_order(payload, self.catalog)
        audit = preview["instruction_field_audit"]
        self.assertEqual(audit["non_text_candidate_paths"], [
            "body.order.special_instructions",
        ])
        self.assertEqual(audit["blank_candidate_paths"], [
            "body.order.items[0].notes",
        ])
        self.assertFalse(audit["schema_verified"])
        self.assertFalse(preview["instructions_verified"])
        self.assertFalse(preview["ready_for_dispatch"])
        self.assertFalse(preview["writes"])

    def test_unsafe_control_in_customer_note_is_diagnostic_only(self):
        payload = sample()
        payload["body"]["order"]["special_instructions"] = "Sans sel\x1b[2J"
        audit = preview_order(payload, self.catalog)["instruction_field_audit"]
        self.assertEqual(audit["unsafe_control_candidate_paths"], [
            "body.order.special_instructions",
        ])
        self.assertFalse(audit["schema_verified"])
        self.assertFalse(audit["writes"])

    def test_c1_customer_note_controls_block_kitchen_readiness(self):
        from clean_caisse.deliveroo_readiness_phase6 import assess_kitchen_readiness
        payload = sample()
        payload["body"]["order"]["notes"] = "Sans sel\x9b[2J"
        preview = preview_order(payload, self.catalog)
        self.assertEqual(
            preview["instruction_field_audit"]["unsafe_control_candidate_paths"],
            ["body.order.notes"],
        )
        readiness = assess_kitchen_readiness(preview)
        self.assertIn("unsafe_instruction_candidates", readiness["blockers"])
        self.assertFalse(readiness["checks_passed"])
        self.assertFalse(readiness["dispatch_performed"])
        self.assertFalse(readiness["writes"])

    def test_multiline_customer_note_is_not_an_unsafe_control(self):
        payload = sample()
        payload["body"]["order"]["notes"] = "Sans sel\nSans piment\tSVP"
        audit = preview_order(payload, self.catalog)["instruction_field_audit"]
        self.assertEqual(audit["unsafe_control_candidate_paths"], [])
        self.assertFalse(audit["schema_verified"])

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



    def test_optional_catalog_markup_is_read_only_and_never_approves(self):
        from clean_caisse.deliveroo_readiness_phase6 import assess_kitchen_readiness
        self.catalog["products"][0]["price"] = "10.00"
        payload = sample()
        self.assertNotIn("catalog_markup_audit", preview_order(payload, self.catalog))
        preview = preview_order(
            payload, self.catalog, assumed_markup_percentage="15"
        )
        audit = preview["catalog_markup_audit"]
        self.assertEqual(audit["assumed_markup_percentage"], "15")
        self.assertEqual(audit["line_diagnostics"][0]["expected_unit_eur"], "11.50")
        self.assertEqual(audit["review_reasons"], [
            "unit_price_differs_from_assumed_markup"
        ])
        self.assertFalse(audit["price_policy_verified"])
        self.assertFalse(audit["writes"])
        self.assertFalse(preview["ready_for_dispatch"])
        readiness = assess_kitchen_readiness(preview)
        self.assertIn("catalog_markup_requires_financial_review", readiness["blockers"])
        self.assertFalse(readiness["checks_passed"])
        self.assertFalse(readiness["dispatch_performed"])

    def test_matching_optional_markup_still_never_dispatches(self):
        from clean_caisse.deliveroo_readiness_phase6 import assess_kitchen_readiness
        self.catalog["products"][0]["price"] = "10.00"
        payload = sample()
        payload["body"]["order"]["items"][0]["unit_price"]["fractional"] = 1150
        preview = preview_order(
            payload, self.catalog, assumed_markup_percentage=15
        )
        self.assertEqual(preview["catalog_markup_audit"]["review_reasons"], [])
        readiness = assess_kitchen_readiness(preview)
        self.assertNotIn("catalog_markup_requires_financial_review", readiness["blockers"])
        self.assertIn("price_policy_not_approved", readiness["blockers"])
        self.assertFalse(readiness["checks_passed"])
        self.assertFalse(readiness["dispatch_performed"])
        self.assertFalse(readiness["writes"])

    def test_tampered_markup_audit_is_rejected_by_readiness(self):
        from clean_caisse.deliveroo_readiness_phase6 import assess_kitchen_readiness
        self.catalog["products"][0]["price"] = "10.00"
        preview = preview_order(
            sample(), self.catalog, assumed_markup_percentage=15
        )
        preview["catalog_markup_audit"]["price_policy_verified"] = True
        preview["catalog_markup_audit"]["ready_for_dispatch"] = True
        preview["catalog_markup_audit"]["line_diagnostics"] = []
        readiness = assess_kitchen_readiness(preview)
        self.assertIn("catalog_markup_dispatch_guard_missing", readiness["blockers"])
        self.assertIn("catalog_markup_diagnostics_missing", readiness["blockers"])
        self.assertFalse(readiness["checks_passed"])
        self.assertFalse(readiness["dispatch_performed"])


    def test_modifier_markup_is_included_but_never_authorizes_dispatch(self):
        from clean_caisse.deliveroo_readiness_phase6 import assess_kitchen_readiness
        self.catalog["products"][0]["price"] = "10.00"
        self.catalog["products"][0]["options"][0]["options"][0]["price"] = "0.95"
        payload = sample()
        line = payload["body"]["order"]["items"][0]
        line["unit_price"]["fractional"] = 1150
        line["modifiers"][0]["unit_price"]["fractional"] = 109
        line["total_price"]["fractional"] = 1259
        payload["body"]["order"]["total_price"]["fractional"] = 1259
        preview = preview_order(
            payload, self.catalog, assumed_markup_percentage="15"
        )
        audit = preview["catalog_modifier_markup_audit"]
        self.assertEqual(audit["modifier_diagnostics"][0]["expected_unit_eur"], "1.09")
        self.assertEqual(audit["review_reasons"], [])
        self.assertFalse(preview["amount_audit"]["requires_financial_review"])
        self.assertFalse(audit["price_policy_verified"])
        self.assertFalse(audit["ready_for_dispatch"])
        self.assertFalse(audit["writes"])
        readiness = assess_kitchen_readiness(preview)
        self.assertIn("price_policy_not_approved", readiness["blockers"])
        self.assertFalse(readiness["checks_passed"])
        self.assertFalse(readiness["dispatch_performed"])

    def test_modifier_price_mismatch_blocks_kitchen_readiness(self):
        from clean_caisse.deliveroo_readiness_phase6 import assess_kitchen_readiness
        self.catalog["products"][0]["price"] = "10.00"
        self.catalog["products"][0]["options"][0]["options"][0]["price"] = "0.95"
        preview = preview_order(
            sample(), self.catalog, assumed_markup_percentage="15"
        )
        self.assertEqual(
            preview["catalog_modifier_markup_audit"]["review_reasons"],
            ["modifier_price_differs_from_assumed_markup"],
        )
        readiness = assess_kitchen_readiness(preview)
        self.assertIn(
            "catalog_modifier_markup_requires_financial_review",
            readiness["blockers"],
        )
        self.assertFalse(readiness["dispatch_performed"])
        preview["catalog_modifier_markup_audit"]["price_policy_verified"] = True
        preview["catalog_modifier_markup_audit"]["modifier_diagnostics"] = []
        tampered = assess_kitchen_readiness(preview)
        self.assertIn("catalog_modifier_markup_dispatch_guard_missing", tampered["blockers"])
        self.assertIn("catalog_modifier_markup_diagnostics_missing", tampered["blockers"])
        self.assertFalse(tampered["checks_passed"])


    def test_documented_order_notes_are_inventory_only(self):
        from clean_caisse.deliveroo_readiness_phase6 import assess_kitchen_readiness
        payload = sample()
        payload["body"]["order"]["order_notes"] = "Sans cornichons"
        payload["body"]["order"]["cutlery_notes"] = "Sans couverts"
        preview = preview_order(payload, self.catalog)
        audit = preview["instruction_field_audit"]
        self.assertEqual(audit["documented_order_note_paths"], [
            "body.order.cutlery_notes", "body.order.order_notes",
        ])
        self.assertEqual(audit["candidate_paths"], [
            "body.order.cutlery_notes", "body.order.order_notes",
        ])
        self.assertFalse(audit["schema_verified"])
        self.assertFalse(preview["instructions_verified"])
        self.assertFalse(preview["ready_for_dispatch"])
        self.assertFalse(assess_kitchen_readiness(preview)["dispatch_performed"])

    def test_documented_order_notes_control_bytes_are_flagged(self):
        from clean_caisse.deliveroo_readiness_phase6 import assess_kitchen_readiness
        payload = sample()
        payload["body"]["order"]["order_notes"] = "Sans sel\\x1b[2J"
        preview = preview_order(payload, self.catalog)
        audit = preview["instruction_field_audit"]
        self.assertEqual(audit["unsafe_control_candidate_paths"], [
            "body.order.order_notes",
        ])
        self.assertIn(
            "unsafe_instruction_candidates",
            assess_kitchen_readiness(preview)["blockers"],
        )


if __name__ == "__main__":
    unittest.main()
