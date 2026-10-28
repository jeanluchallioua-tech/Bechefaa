import unittest
from copy import deepcopy

from clean_caisse.deliveroo_amount_audit_phase6 import (audit_order_amounts, audit_catalog_base_markup)
from tests.test_deliveroo_order_reconcile import sample


class DeliverooAmountAuditTests(unittest.TestCase):
    def test_default_sample_matches_modifier_hypotheses_but_never_approves(self):
        audit = audit_order_amounts(sample())
        line = audit["line_diagnostics"][0]
        self.assertEqual(audit["order_total_eur"], "8.95")
        self.assertEqual(audit["items_total_eur"], "8.95")
        self.assertEqual(audit["difference_eur"], "0.00")
        self.assertTrue(audit["totals_match"])
        self.assertEqual(line["base_total_eur"], "8.00")
        self.assertEqual(line["modifiers_once_eur"], "0.95")
        self.assertFalse(line["matches_base_only"])
        self.assertTrue(line["matches_modifiers_once"])
        self.assertTrue(line["matches_modifiers_per_parent"])
        self.assertFalse(audit["modifier_pricing_schema_verified"])
        self.assertFalse(audit["price_policy_verified"])
        self.assertFalse(audit["ready_for_dispatch"])
        self.assertFalse(audit["writes"])

    def test_parent_quantity_exposes_both_modifier_price_models(self):
        payload = sample()
        line = payload["body"]["order"]["items"][0]
        line["quantity"] = 2
        line["modifiers"][0]["quantity"] = 2
        line["total_price"]["fractional"] = 1980
        payload["body"]["order"]["total_price"]["fractional"] = 1980
        audit = audit_order_amounts(payload)
        diag = audit["line_diagnostics"][0]
        self.assertEqual(diag["base_total_eur"], "16.00")
        self.assertEqual(diag["modifiers_once_eur"], "1.90")
        self.assertEqual(diag["candidate_total_modifiers_once_eur"], "17.90")
        self.assertEqual(diag["candidate_total_modifiers_per_parent_eur"], "19.80")
        self.assertFalse(diag["matches_modifiers_once"])
        self.assertTrue(diag["matches_modifiers_per_parent"])
        self.assertFalse(audit["price_policy_verified"])

    def test_paid_modifiers_missing_from_line_total_require_review(self):
        payload = sample()
        payload["body"]["order"]["items"][0]["total_price"]["fractional"] = 800
        payload["body"]["order"]["total_price"]["fractional"] = 800
        audit = audit_order_amounts(payload)
        self.assertTrue(audit["totals_match"])
        self.assertEqual(audit["unexplained_line_indices"], [])
        self.assertEqual(audit["paid_modifiers_excluded_line_indices"], [0])
        self.assertTrue(audit["line_diagnostics"][0]["paid_modifiers_excluded_from_line_total"])
        self.assertIn("paid_modifiers_excluded_from_line_totals", audit["review_reasons"])
        self.assertTrue(audit["requires_financial_review"])
        self.assertFalse(audit["price_policy_verified"])
        self.assertFalse(audit["ready_for_dispatch"])
        self.assertFalse(audit["writes"])

    def test_zero_cost_modifier_does_not_trigger_paid_modifier_warning(self):
        payload = sample()
        line = payload["body"]["order"]["items"][0]
        line["modifiers"][0]["unit_price"]["fractional"] = 0
        line["total_price"]["fractional"] = 800
        payload["body"]["order"]["total_price"]["fractional"] = 800
        audit = audit_order_amounts(payload)
        self.assertEqual(audit["paid_modifiers_excluded_line_indices"], [])
        self.assertFalse(audit["requires_financial_review"])
        self.assertFalse(audit["ready_for_dispatch"])

    def test_order_total_difference_may_be_fees_or_discount(self):
        payload = sample()
        payload["body"]["order"]["total_price"]["fractional"] = 1000
        audit = audit_order_amounts(payload)
        self.assertEqual(audit["difference_eur"], "1.05")
        self.assertFalse(audit["totals_match"])
        self.assertFalse(audit["ready_for_dispatch"])

    def test_price_review_identifies_unexplained_line_totals(self):
        payload = sample()
        payload["body"]["order"]["items"][0]["total_price"]["fractional"] = 990
        payload["body"]["order"]["total_price"]["fractional"] = 990
        audit = audit_order_amounts(payload)
        self.assertTrue(audit["totals_match"])
        self.assertEqual(audit["unexplained_line_indices"], [0])
        self.assertEqual(audit["review_reasons"], [
            "line_totals_match_no_candidate_model",
        ])
        self.assertTrue(audit["requires_financial_review"])
        self.assertFalse(audit["price_policy_verified"])
        self.assertFalse(audit["ready_for_dispatch"])
        self.assertFalse(audit["writes"])

    def test_price_review_identifies_order_level_difference(self):
        payload = sample()
        payload["body"]["order"]["total_price"]["fractional"] = 1000
        audit = audit_order_amounts(payload)
        self.assertEqual(audit["unexplained_line_indices"], [])
        self.assertEqual(audit["review_reasons"], [
            "order_total_differs_from_item_totals",
        ])
        self.assertTrue(audit["requires_financial_review"])
        self.assertFalse(audit["writes"])

    def test_consistent_candidate_amounts_do_not_approve_policy(self):
        audit = audit_order_amounts(sample())
        self.assertEqual(audit["unexplained_line_indices"], [])
        self.assertEqual(audit["review_reasons"], [])
        self.assertFalse(audit["requires_financial_review"])
        self.assertFalse(audit["price_policy_verified"])
        self.assertFalse(audit["modifier_pricing_schema_verified"])

    def test_multiple_lines_and_no_modifiers(self):
        payload = sample()
        second = deepcopy(payload["body"]["order"]["items"][0])
        second["pos_item_id"] = "SECOND"
        second["quantity"] = 3
        second["modifiers"] = []
        second["unit_price"]["fractional"] = 125
        second["total_price"]["fractional"] = 375
        payload["body"]["order"]["items"].append(second)
        payload["body"]["order"]["total_price"]["fractional"] = 1270
        audit = audit_order_amounts(payload)
        self.assertEqual(len(audit["line_diagnostics"]), 2)
        self.assertEqual(audit["items_total_eur"], "12.70")
        self.assertTrue(audit["totals_match"])
        self.assertTrue(audit["line_diagnostics"][1]["matches_base_only"])
        self.assertFalse(audit["writes"])



class DeliverooCatalogMarkupAuditTests(unittest.TestCase):
    def setUp(self):
        self.payload = sample()
        self.catalog = {"products": [{
            "id": "MU11002", "name": "Veggie Burger", "price": "10.00",
        }]}

    def test_matching_assumed_fifteen_percent_never_approves_policy(self):
        self.payload["body"]["order"]["items"][0]["unit_price"]["fractional"] = 1150
        audit = audit_catalog_base_markup(
            self.payload, self.catalog, markup_percentage="15"
        )
        line = audit["line_diagnostics"][0]
        self.assertEqual(line["catalog_base_eur"], "10.00")
        self.assertEqual(line["expected_unit_eur"], "11.50")
        self.assertEqual(line["reported_unit_eur"], "11.50")
        self.assertEqual(line["status"], "matches_assumed_markup")
        self.assertEqual(audit["review_reasons"], [])
        self.assertFalse(audit["requires_financial_review"])
        self.assertFalse(audit["price_policy_verified"])
        self.assertFalse(audit["ready_for_dispatch"])
        self.assertFalse(audit["writes"])

    def test_mismatch_reports_exact_difference_without_approving(self):
        audit = audit_catalog_base_markup(
            self.payload, self.catalog, markup_percentage=15
        )
        line = audit["line_diagnostics"][0]
        self.assertEqual(line["reported_unit_eur"], "8.00")
        self.assertEqual(line["expected_unit_eur"], "11.50")
        self.assertEqual(line["difference_eur"], "-3.50")
        self.assertEqual(audit["review_reasons"], [
            "unit_price_differs_from_assumed_markup"
        ])
        self.assertTrue(audit["requires_financial_review"])
        self.assertFalse(audit["price_policy_verified"])

    def test_round_half_up_matches_menu_builder_policy(self):
        self.catalog["products"][0]["price"] = "0.10"
        self.payload["body"]["order"]["items"][0]["unit_price"]["fractional"] = 11
        audit = audit_catalog_base_markup(
            self.payload, self.catalog, markup_percentage="5"
        )
        self.assertEqual(audit["line_diagnostics"][0]["expected_unit_eur"], "0.11")
        self.assertEqual(audit["review_reasons"], [])

    def test_missing_and_inactive_products_are_reviewed(self):
        audit = audit_catalog_base_markup(
            self.payload, {"products": []}, markup_percentage=15
        )
        self.assertEqual(audit["review_reasons"], ["missing_catalog_product"])
        self.catalog["products"][0]["active"] = False
        audit = audit_catalog_base_markup(
            self.payload, self.catalog, markup_percentage=15
        )
        self.assertEqual(audit["review_reasons"], ["inactive_catalog_product"])

    def test_invalid_catalogue_price_is_not_treated_as_zero(self):
        for bad in (None, "not a price", True, "-1", "NaN", "Infinity"):
            with self.subTest(bad=bad):
                self.catalog["products"][0]["price"] = bad
                audit = audit_catalog_base_markup(
                    self.payload, self.catalog, markup_percentage=15
                )
                self.assertEqual(audit["review_reasons"], ["invalid_catalog_price"])
                self.assertFalse(audit["price_policy_verified"])

    def test_duplicate_catalogue_ids_fail_closed(self):
        from clean_caisse.deliveroo_order_mapping_phase6 import DeliverooMappingError
        self.catalog["products"].append(deepcopy(self.catalog["products"][0]))
        with self.assertRaisesRegex(DeliverooMappingError, "Duplicate catalogue"):
            audit_catalog_base_markup(
                self.payload, self.catalog, markup_percentage=15
            )

    def test_markup_must_be_supplied_as_valid_nonnegative_number(self):
        from clean_caisse.deliveroo_order_mapping_phase6 import DeliverooMappingError
        for bad in (None, True, "-1", "NaN", "Infinity", "fifteen"):
            with self.subTest(bad=bad):
                with self.assertRaises(DeliverooMappingError):
                    audit_catalog_base_markup(
                        self.payload, self.catalog, markup_percentage=bad
                    )



class DeliverooModifierMarkupAuditTests(unittest.TestCase):
    def setUp(self):
        self.payload = sample()
        self.catalog = {"products": [{
            "id": "MU11002", "name": "Veggie Burger",
            "options": [{"name": "Extras", "options": [
                {"name": "Guacamole", "price": "0.95"},
            ]}],
        }]}

    def test_matching_modifier_markup_is_diagnostic_not_approval(self):
        from clean_caisse.deliveroo_amount_audit_phase6 import audit_catalog_modifier_markup
        self.payload["body"]["order"]["items"][0]["modifiers"][0]["unit_price"]["fractional"] = 109
        before = deepcopy(self.payload)
        audit = audit_catalog_modifier_markup(
            self.payload, self.catalog, markup_percentage="15"
        )
        self.assertEqual(self.payload, before)
        self.assertEqual(audit["modifier_diagnostics"][0]["expected_unit_eur"], "1.09")
        self.assertEqual(audit["modifier_diagnostics"][0]["status"], "matches_assumed_modifier_markup")
        self.assertEqual(audit["review_reasons"], [])
        self.assertFalse(audit["modifier_pricing_schema_verified"])
        self.assertFalse(audit["price_policy_verified"])
        self.assertFalse(audit["ready_for_dispatch"])
        self.assertFalse(audit["writes"])

    def test_mismatch_reports_exact_difference(self):
        from clean_caisse.deliveroo_amount_audit_phase6 import audit_catalog_modifier_markup
        audit = audit_catalog_modifier_markup(
            self.payload, self.catalog, markup_percentage=15
        )
        line = audit["modifier_diagnostics"][0]
        self.assertEqual(line["difference_eur"], "-0.14")
        self.assertEqual(line["status"], "modifier_price_differs_from_assumed_markup")
        self.assertTrue(audit["requires_financial_review"])

    def test_legacy_plu_never_matches_by_label(self):
        from clean_caisse.deliveroo_amount_audit_phase6 import audit_catalog_modifier_markup
        modifier = self.payload["body"]["order"]["items"][0]["modifiers"][0]
        modifier["pos_item_id"] = "OM21001"
        modifier["name"] = "Guacamole"
        audit = audit_catalog_modifier_markup(
            self.payload, self.catalog, markup_percentage=15
        )
        self.assertEqual(audit["review_reasons"], ["unmapped_modifier_plu"])
        self.assertIsNone(audit["modifier_diagnostics"][0]["expected_unit_eur"])
        self.assertFalse(audit["ready_for_dispatch"])

    def test_inactive_choice_and_invalid_price_are_flagged(self):
        from clean_caisse.deliveroo_amount_audit_phase6 import audit_catalog_modifier_markup
        choice = self.catalog["products"][0]["options"][0]["options"][0]
        choice["active"] = 0
        audit = audit_catalog_modifier_markup(
            self.payload, self.catalog, markup_percentage=15
        )
        self.assertEqual(audit["review_reasons"], ["inactive_catalog_modifier_choice"])
        choice["active"] = 1
        choice["price"] = "invalid"
        audit = audit_catalog_modifier_markup(
            self.payload, self.catalog, markup_percentage=15
        )
        self.assertEqual(audit["review_reasons"], ["invalid_catalog_modifier_price"])

    def test_null_or_boolean_catalogue_choice_is_not_a_free_modifier(self):
        from clean_caisse.deliveroo_amount_audit_phase6 import audit_catalog_modifier_markup

        for invalid_choice in (None, True, False):
            with self.subTest(choice=invalid_choice):
                catalog = deepcopy(self.catalog)
                catalog["products"][0]["options"][0]["options"][0] = invalid_choice
                before_payload = deepcopy(self.payload)
                before_catalog = deepcopy(catalog)
                audit = audit_catalog_modifier_markup(
                    self.payload, catalog, markup_percentage="20"
                )
                line = audit["modifier_diagnostics"][0]
                self.assertEqual(line["status"], "invalid_catalog_modifier_choice")
                self.assertIsNone(line["expected_unit_eur"])
                self.assertEqual(audit["review_reasons"], ["invalid_catalog_modifier_choice"])
                self.assertTrue(audit["requires_financial_review"])
                self.assertFalse(audit["price_policy_verified"])
                self.assertFalse(audit["ready_for_dispatch"])
                self.assertFalse(audit["writes"])
                self.assertEqual(self.payload, before_payload)
                self.assertEqual(catalog, before_catalog)

    def test_null_or_boolean_positional_labels_never_pass_price_audit(self):
        from clean_caisse.deliveroo_amount_audit_phase6 import audit_catalog_modifier_markup

        self.payload["body"]["order"]["items"][0]["modifiers"][0]["unit_price"]["fractional"] = 0
        for invalid in (None, True, False):
            with self.subTest(label=invalid):
                catalog = deepcopy(self.catalog)
                catalog["products"][0]["options"][0]["options"][0] = [invalid, 0]
                audit = audit_catalog_modifier_markup(
                    self.payload, catalog, markup_percentage="20"
                )
                self.assertEqual(
                    audit["review_reasons"], ["invalid_catalog_modifier_choice"]
                )
                self.assertIsNone(audit["modifier_diagnostics"][0]["expected_unit_eur"])
                self.assertTrue(audit["requires_financial_review"])
                self.assertFalse(audit["ready_for_dispatch"])
                self.assertFalse(audit["writes"])

    def test_blank_catalogue_modifier_labels_never_pass_price_audit(self):
        # A zero-price placeholder used to look like a valid free supplement
        # in this price audit, although the strict PLU reconciler rejects it.
        from clean_caisse.deliveroo_amount_audit_phase6 import audit_catalog_modifier_markup

        self.payload["body"]["order"]["items"][0]["modifiers"][0]["unit_price"]["fractional"] = 0
        for invalid_choice in (
            "", "   ", [], ["  ", 0],
            {"name": "", "price": 0},
            {"label": "   ", "price": 0},
        ):
            with self.subTest(choice=invalid_choice):
                catalog = deepcopy(self.catalog)
                catalog["products"][0]["options"][0]["options"][0] = invalid_choice
                before_payload = deepcopy(self.payload)
                before_catalog = deepcopy(catalog)
                audit = audit_catalog_modifier_markup(
                    self.payload, catalog, markup_percentage="20"
                )
                line = audit["modifier_diagnostics"][0]
                self.assertEqual(line["status"], "invalid_catalog_modifier_choice")
                self.assertIsNone(line["expected_unit_eur"])
                self.assertEqual(audit["review_reasons"], ["invalid_catalog_modifier_choice"])
                self.assertTrue(audit["requires_financial_review"])
                self.assertFalse(audit["ready_for_dispatch"])
                self.assertFalse(audit["writes"])
                self.assertEqual(self.payload, before_payload)
                self.assertEqual(catalog, before_catalog)

    def test_zero_price_modifier_and_empty_modifier_list_never_approve(self):
        from clean_caisse.deliveroo_amount_audit_phase6 import audit_catalog_modifier_markup
        self.catalog["products"][0]["options"][0]["options"][0]["price"] = 0
        self.payload["body"]["order"]["items"][0]["modifiers"][0]["unit_price"]["fractional"] = 0
        audit = audit_catalog_modifier_markup(
            self.payload, self.catalog, markup_percentage=15
        )
        self.assertEqual(audit["modifier_diagnostics"][0]["expected_unit_eur"], "0.00")
        self.assertEqual(audit["review_reasons"], [])
        self.payload["body"]["order"]["items"][0]["modifiers"] = []
        empty = audit_catalog_modifier_markup(
            self.payload, self.catalog, markup_percentage=15
        )
        self.assertEqual(empty["modifier_diagnostics"], [])
        self.assertFalse(empty["price_policy_verified"])
        self.assertFalse(empty["ready_for_dispatch"])

    def test_explicit_zero_modifier_price_beats_legacy_fallbacks(self):
        from clean_caisse.deliveroo_amount_audit_phase6 import audit_catalog_modifier_markup

        choice = self.catalog["products"][0]["options"][0]["options"][0]
        choice.update({"price": 0, "extraPrice": "0.95", "supplement": "1.50"})
        self.payload["body"]["order"]["items"][0]["modifiers"][0]["unit_price"]["fractional"] = 0
        audit = audit_catalog_modifier_markup(
            self.payload, self.catalog, markup_percentage=15
        )
        line = audit["modifier_diagnostics"][0]
        self.assertEqual(line["catalog_base_eur"], "0.00")
        self.assertEqual(line["expected_unit_eur"], "0.00")
        self.assertEqual(line["status"], "matches_assumed_modifier_markup")
        self.assertEqual(audit["review_reasons"], [])
        self.assertFalse(audit["price_policy_verified"])
        self.assertFalse(audit["ready_for_dispatch"])
        self.assertFalse(audit["writes"])

    def test_duplicate_catalogue_products_and_invalid_markup_fail_closed(self):
        from clean_caisse.deliveroo_amount_audit_phase6 import audit_catalog_modifier_markup
        from clean_caisse.deliveroo_order_mapping_phase6 import DeliverooMappingError
        self.catalog["products"].append(deepcopy(self.catalog["products"][0]))
        with self.assertRaisesRegex(DeliverooMappingError, "Duplicate catalogue"):
            audit_catalog_modifier_markup(
                self.payload, self.catalog, markup_percentage=15
            )
        self.catalog["products"].pop()
        for bad in (None, True, "-1", "NaN", "Infinity"):
            with self.subTest(bad=bad):
                with self.assertRaises(DeliverooMappingError):
                    audit_catalog_modifier_markup(
                        self.payload, self.catalog, markup_percentage=bad
                    )



class DeliverooOversizedPluIndexTests(unittest.TestCase):
    """Malformed PLU indices must fail closed, never escape as int() errors."""

    def test_modifier_price_audit_reports_oversized_index(self):
        from clean_caisse.deliveroo_amount_audit_phase6 import audit_catalog_modifier_markup
        payload = sample()
        payload["body"]["order"]["items"][0]["modifiers"][0]["pos_item_id"] = (
            "opt:MU11002:0:" + "9" * 5000
        )
        catalog = {"products": [{"id": "MU11002", "options": [
            {"options": [{"name": "Guacamole", "price": "0.95"}]}
        ]}]}
        before = deepcopy(payload)
        audit = audit_catalog_modifier_markup(payload, catalog, markup_percentage="20")
        self.assertEqual(audit["review_reasons"], ["unmapped_modifier_plu"])
        self.assertTrue(audit["requires_financial_review"])
        self.assertFalse(audit["ready_for_dispatch"])
        self.assertFalse(audit["writes"])
        self.assertEqual(payload, before)

    def test_legacy_map_rejects_oversized_target_as_mapping_error(self):
        from clean_caisse.deliveroo_explicit_plu_map_phase6 import reconcile_with_explicit_plu_map
        from clean_caisse.deliveroo_order_mapping_phase6 import DeliverooMappingError
        payload = sample()
        payload["body"]["order"]["items"][0]["modifiers"][0]["pos_item_id"] = "OM21001"
        catalog = {"products": [{"id": "MU11002", "options": [
            {"options": [{"name": "Guacamole", "price": "0.95"}]}
        ]}]}
        before = deepcopy(payload)
        with self.assertRaises(DeliverooMappingError):
            reconcile_with_explicit_plu_map(
                payload, catalog,
                {("MU11002", "OM21001"): "opt:MU11002:0:" + "9" * 5000},
            )
        self.assertEqual(payload, before)

if __name__ == "__main__":
    unittest.main()
