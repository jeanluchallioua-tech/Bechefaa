import unittest
from copy import deepcopy

from clean_caisse.deliveroo_amount_audit_phase6 import audit_order_amounts
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

    def test_order_total_difference_may_be_fees_or_discount(self):
        payload = sample()
        payload["body"]["order"]["total_price"]["fractional"] = 1000
        audit = audit_order_amounts(payload)
        self.assertEqual(audit["difference_eur"], "1.05")
        self.assertFalse(audit["totals_match"])
        self.assertFalse(audit["ready_for_dispatch"])

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


if __name__ == "__main__":
    unittest.main()
