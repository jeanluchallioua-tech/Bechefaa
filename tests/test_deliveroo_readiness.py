import unittest

from clean_caisse.deliveroo_readiness_phase6 import assess_kitchen_readiness
from clean_caisse.deliveroo_kitchen_preview_phase6 import preview_order
from tests.test_deliveroo_order_reconcile import sample


class DeliverooReadinessTests(unittest.TestCase):
    def setUp(self):
        catalog = {"products": [{
            "id": "MU11002", "name": "Veggie Burger",
            "options": [{"name": "Extras", "options": [{"name": "Guacamole"}]}],
        }]}
        self.preview = preview_order(sample(), catalog)

    def test_default_blocks_all_unverified_gates(self):
        result = assess_kitchen_readiness(self.preview)
        self.assertEqual(result["blockers"], [
            "plu_mapping_not_approved",
            "price_policy_not_approved",
            "instruction_schema_not_verified",
        ])
        self.assertFalse(result["checks_passed"])
        self.assertFalse(result["dispatch_performed"])
        self.assertFalse(result["writes"])

    def test_approval_flags_without_evidence_still_block(self):
        result = assess_kitchen_readiness(
            self.preview, plu_approved=True, price_policy_approved=True,
            instruction_schema_verified=True,
        )
        self.assertFalse(result["checks_passed"])
        self.assertIn("instruction_evidence_missing", result["blockers"])
        self.assertIn("price_policy_evidence_missing", result["blockers"])
        self.assertFalse(result["dispatch_performed"])
        self.assertFalse(result["writes"])

    def test_invalid_preview_never_passes(self):
        result = assess_kitchen_readiness(
            {"writes": True, "items": []}, plu_approved=True,
            price_policy_approved=True, instruction_schema_verified=True,
        )
        self.assertIn("invalid_read_only_preview", result["blockers"])
        self.assertIn("missing_kitchen_items", result["blockers"])


if __name__ == "__main__":
    unittest.main()
