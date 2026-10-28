"""Isolated, read-only regression for the BIS Deliveroo 20% audit."""
from copy import deepcopy
import unittest

from clean_caisse.deliveroo_preflight_phase6 import audit_deliveroo_20pct_preflight
from tests.test_deliveroo_order_reconcile import sample


class Deliveroo20PercentPreflightTests(unittest.TestCase):
    def setUp(self):
        self.payload = sample()
        line = self.payload["body"]["order"]["items"][0]
        line["unit_price"]["fractional"] = 1200
        line["total_price"]["fractional"] = 1320
        line["modifiers"][0]["unit_price"]["fractional"] = 120
        self.payload["body"]["order"]["total_price"]["fractional"] = 1320
        self.catalog = {"products": [{
            "id": "MU11002", "name": "Veggie Burger", "price": "10.00",
            "options": [{"name": "Extras", "options": [
                {"name": "Guacamole", "price": "1.00"},
            ]}],
        }]}

    def audit(self):
        original_payload = deepcopy(self.payload)
        original_catalog = deepcopy(self.catalog)
        result = audit_deliveroo_20pct_preflight(self.payload, self.catalog)
        self.assertEqual(self.payload, original_payload)
        self.assertEqual(self.catalog, original_catalog)
        self.assertEqual(result["deliveroo_markup_assumption_percent"], "20")
        self.assertFalse(result["writes"])
        self.assertFalse(result["ready_for_dispatch"])
        self.assertTrue(result["requires_explicit_dispatch_approval"])
        return result

    def test_matching_twenty_percent_is_still_not_dispatch_approval(self):
        result = self.audit()
        self.assertEqual(result["blockers"], [])
        self.assertFalse(result["base_price_audit"]["price_policy_verified"])
        self.assertFalse(result["modifier_price_audit"]["price_policy_verified"])

    def test_wrong_base_price_is_reported(self):
        self.payload["body"]["order"]["items"][0]["unit_price"]["fractional"] = 1100
        result = self.audit()
        self.assertIn("base_prices_differ_from_20pct_policy", result["blockers"])
        self.assertEqual(
            result["base_price_audit"]["line_diagnostics"][0]["expected_unit_eur"],
            "12.00",
        )

    def test_wrong_modifier_price_is_reported(self):
        self.payload["body"]["order"]["items"][0]["modifiers"][0]["unit_price"]["fractional"] = 100
        result = self.audit()
        self.assertIn("modifier_prices_differ_from_20pct_policy", result["blockers"])
        self.assertEqual(
            result["modifier_price_audit"]["modifier_diagnostics"][0]["expected_unit_eur"],
            "1.20",
        )

    def test_legacy_plu_cannot_be_approved_by_matching_label(self):
        self.payload["body"]["order"]["items"][0]["modifiers"][0]["pos_item_id"] = "OM21001"
        result = self.audit()
        self.assertIn("modifier_plu_review_required", result["blockers"])
        self.assertIn("catalogue_reconciliation_failed", result["blockers"])
        self.assertIn("modifier_prices_differ_from_20pct_policy", result["blockers"])

    def test_unknown_product_is_not_silently_mapped(self):
        self.payload["body"]["order"]["items"][0]["pos_item_id"] = "UNKNOWN"
        result = self.audit()
        self.assertIn("catalogue_reconciliation_failed", result["blockers"])
        self.assertIn("base_prices_differ_from_20pct_policy", result["blockers"])

    def test_top_level_customer_instructions_block_preflight(self):
        self.payload["delivery_instructions"] = "Sonner deux fois"
        result = self.audit()
        self.assertIn("customer_instructions_need_mapping", result["blockers"])
        self.assertEqual(result["instruction_candidate_paths"], ["delivery_instructions"])
        self.assertNotIn("Sonner deux fois", str(result))

    def test_customer_instructions_are_not_lost_or_printed(self):
        self.payload["body"]["order"]["order_notes"] = "Sans oignons"
        result = self.audit()
        self.assertIn("customer_instructions_need_mapping", result["blockers"])
        self.assertEqual(result["instruction_candidate_paths"], ["body.order.order_notes"])
        self.assertNotIn("Sans oignons", str(result))

    def test_reordered_canonical_modifier_plu_requires_review(self):
        # The PLU still resolves, but a catalogue reorder can change the
        # kitchen choice without changing its canonical index.
        self.catalog["products"][0]["options"][0]["options"][0]["name"] = "Bacon"
        result = self.audit()
        self.assertTrue(result["catalogue_label_check_complete"])
        self.assertIn("catalogue_labels_differ_from_webhook", result["blockers"])
        self.assertEqual(result["catalogue_label_drift"], [{
            "kind": "modifier", "line_index": 0, "modifier_index": 0,
            "pos_item_id": "opt:MU11002:0:0",
        }])
        self.assertNotIn("Guacamole", str(result["catalogue_label_drift"]))
        self.assertFalse(result["ready_for_dispatch"])

    def test_product_label_drift_requires_review_without_remapping(self):
        self.catalog["products"][0]["name"] = "Another Burger"
        result = self.audit()
        self.assertIn("catalogue_labels_differ_from_webhook", result["blockers"])
        self.assertEqual(result["catalogue_label_drift"], [{
            "kind": "product", "line_index": 0, "pos_item_id": "MU11002",
        }])

    def test_missing_webhook_label_is_not_treated_as_a_match(self):
        self.payload["body"]["order"]["items"][0]["modifiers"][0]["name"] = ""
        result = self.audit()
        self.assertIn("catalogue_labels_unverifiable", result["blockers"])
        self.assertEqual(result["catalogue_label_unverifiable"], [{
            "kind": "modifier", "line_index": 0, "modifier_index": 0,
            "pos_item_id": "opt:MU11002:0:0",
        }])

    def test_label_comparison_ignores_case_and_extra_spaces(self):
        self.payload["body"]["order"]["items"][0]["name"] = "  VEGGIE   burger "
        self.payload["body"]["order"]["items"][0]["modifiers"][0]["name"] = " GUACAMOLE "
        result = self.audit()
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["catalogue_label_drift"], [])
        self.assertEqual(result["catalogue_label_unverifiable"], [])

    def test_control_characters_in_product_labels_require_review(self):
        # Whitespace normalization previously hid line breaks that would be
        # unsafe on a kitchen ticket, reporting a misleading clean preflight.
        for location in ("incoming", "catalogue"):
            with self.subTest(location=location):
                self.setUp()
                if location == "incoming":
                    self.payload["body"]["order"]["items"][0]["name"] = "Veggie\nBurger"
                else:
                    self.catalog["products"][0]["name"] = "Veggie\nBurger"
                result = self.audit()
                self.assertIn("catalogue_labels_unverifiable", result["blockers"])
                self.assertEqual(result["catalogue_label_unverifiable"], [{
                    "kind": "product", "line_index": 0, "pos_item_id": "MU11002",
                }])
                self.assertFalse(result["ready_for_dispatch"])

    def test_control_characters_in_modifier_or_group_require_review(self):
        for location in ("incoming", "choice", "group"):
            with self.subTest(location=location):
                self.setUp()
                if location == "incoming":
                    self.payload["body"]["order"]["items"][0]["modifiers"][0]["name"] = "Guaca\nmole"
                elif location == "choice":
                    self.catalog["products"][0]["options"][0]["options"][0]["name"] = "Guaca\nmole"
                else:
                    self.catalog["products"][0]["options"][0]["name"] = "Extras\n"
                result = self.audit()
                self.assertIn("catalogue_labels_unverifiable", result["blockers"])
                self.assertEqual(result["catalogue_label_unverifiable"], [{
                    "kind": "modifier", "line_index": 0, "modifier_index": 0,
                    "pos_item_id": "opt:MU11002:0:0",
                }])
                self.assertFalse(result["ready_for_dispatch"])

    def test_null_positional_choice_cannot_pass_preflight(self):
        self.catalog["products"][0]["options"][0]["options"][0] = [None, 0]
        self.payload["body"]["order"]["items"][0]["modifiers"][0]["unit_price"]["fractional"] = 0
        result = self.audit()
        self.assertIn("catalogue_reconciliation_failed", result["blockers"])
        self.assertIn("modifier_prices_differ_from_20pct_policy", result["blockers"])
        self.assertFalse(result["catalogue_label_check_complete"])

    def test_failed_reconciliation_does_not_claim_label_check_complete(self):
        self.payload["body"]["order"]["items"][0]["modifiers"][0]["pos_item_id"] = "OM21001"
        result = self.audit()
        self.assertFalse(result["catalogue_label_check_complete"])
        self.assertIn("catalogue_reconciliation_failed", result["blockers"])

    def test_order_amount_discrepancy_is_reviewed(self):
        self.payload["body"]["order"]["total_price"]["fractional"] = 1500
        result = self.audit()
        self.assertIn("order_amounts_require_review", result["blockers"])

    def test_subcent_catalogue_prices_block_preflight_even_when_rounded_price_matches(self):
        # The audit must not silently turn 10.004 into 10.00 or 1.004 into 1.00.
        self.catalog["products"][0]["price"] = "10.004"
        self.catalog["products"][0]["options"][0]["options"][0]["price"] = "1.004"
        result = self.audit()
        self.assertIn("base_prices_differ_from_20pct_policy", result["blockers"])
        self.assertIn("modifier_prices_differ_from_20pct_policy", result["blockers"])
        self.assertEqual(result["base_price_audit"]["review_reasons"], ["invalid_catalog_price"])
        self.assertEqual(result["modifier_price_audit"]["review_reasons"], ["invalid_catalog_modifier_price"])
        self.assertFalse(result["ready_for_dispatch"])

    def test_malformed_catalogue_returns_blockers_not_an_audit_exception(self):
        # Invalid catalogue data must not turn a mandatory financial check
        # into an unstructured error or an accidental dispatch approval.
        malformed = (
            None,
            {"products": "invalid"},
            {"products": [
                {"id": "MU11002", "name": "Veggie Burger", "price": "10.00"},
                {"id": "MU11002", "name": "Duplicate", "price": "10.00"},
            ]},
            {"products": [{
                "id": "MU11002", "name": "Veggie Burger",
                "price": "10.00", "active": "false",
            }]},
        )
        for catalogue in malformed:
            with self.subTest(catalogue=catalogue):
                self.catalog = catalogue
                result = self.audit()
                self.assertIn("catalogue_reconciliation_failed", result["blockers"])
                self.assertIn("base_price_audit_incomplete", result["blockers"])
                self.assertIn("modifier_price_audit_incomplete", result["blockers"])
                self.assertTrue(result["base_price_audit"]["requires_financial_review"])
                self.assertTrue(result["modifier_price_audit"]["requires_financial_review"])
                self.assertFalse(result["base_price_audit"]["price_policy_verified"])
                self.assertFalse(result["modifier_price_audit"]["price_policy_verified"])
                self.assertFalse(result["ready_for_dispatch"])

    def test_oversized_instruction_tree_fails_closed(self):
        self.payload["body"]["order"]["metadata"] = ["x"] * 6000
        result = self.audit()
        self.assertIn("instruction_scan_incomplete", result["blockers"])
        self.assertFalse(result["instruction_scan_complete"])


    def test_unsafe_catalogue_labels_block_preflight_even_when_prices_match(self):
        for location in ("product", "group", "choice"):
            with self.subTest(location=location):
                self.setUp()
                product = self.catalog["products"][0]
                if location == "product":
                    product["name"] = "Veggie\\nBurger"
                elif location == "group":
                    product["options"][0]["name"] = "Extras\\x1bPrint"
                else:
                    product["options"][0]["options"][0]["name"] = True
                result = self.audit()
                self.assertIn("catalogue_reconciliation_failed", result["blockers"])
                self.assertFalse(result["catalogue_label_check_complete"])
                self.assertFalse(result["ready_for_dispatch"])

if __name__ == "__main__":
    unittest.main()
