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

    def test_malformed_kitchen_items_and_modifiers_block_readiness(self):
        from copy import deepcopy
        preview = deepcopy(self.preview)
        preview["items"][0]["quantity"] = True
        preview["items"][0]["options"][0]["quantity"] = 0
        result = assess_kitchen_readiness(preview)
        self.assertIn("invalid_kitchen_quantity", result["blockers"])
        self.assertIn("invalid_kitchen_modifier_quantity", result["blockers"])
        self.assertFalse(result["checks_passed"])

    def test_missing_kitchen_names_and_options_block_readiness(self):
        from copy import deepcopy
        preview = deepcopy(self.preview)
        preview["items"][0]["name"] = " "
        preview["items"][0]["options"] = None
        result = assess_kitchen_readiness(preview)
        self.assertIn("invalid_kitchen_item", result["blockers"])
        self.assertIn("invalid_kitchen_options", result["blockers"])

    def test_invalid_name_does_not_hide_other_invalid_fields(self):
        from copy import deepcopy
        preview = deepcopy(self.preview)
        preview["items"][0]["name"] = " "
        preview["items"][0]["quantity"] = 0
        preview["items"][0]["options"][0]["quantity"] = False
        result = assess_kitchen_readiness(preview)
        self.assertIn("invalid_kitchen_item", result["blockers"])
        self.assertIn("invalid_kitchen_quantity", result["blockers"])
        self.assertIn("invalid_kitchen_modifier_quantity", result["blockers"])
        self.assertFalse(result["checks_passed"])

    def test_missing_or_tampered_amount_audit_blocks_readiness(self):
        from copy import deepcopy
        missing = deepcopy(self.preview)
        missing.pop("amount_audit")
        result = assess_kitchen_readiness(missing)
        self.assertIn("amount_audit_missing", result["blockers"])
        tampered = deepcopy(self.preview)
        tampered["amount_audit"]["ready_for_dispatch"] = True
        tampered["amount_audit"]["price_policy_verified"] = True
        tampered["amount_audit"]["line_diagnostics"] = []
        result = assess_kitchen_readiness(tampered)
        self.assertIn("amount_audit_dispatch_guard_missing", result["blockers"])
        self.assertIn("amount_audit_price_guard_missing", result["blockers"])
        self.assertIn("amount_line_diagnostics_missing", result["blockers"])
        self.assertFalse(result["checks_passed"])
        self.assertFalse(result["dispatch_performed"])
        self.assertFalse(result["writes"])

    def test_paid_modifiers_not_in_line_total_block_readiness(self):
        from copy import deepcopy
        preview = deepcopy(self.preview)
        preview["amount_audit"]["requires_financial_review"] = True
        preview["amount_audit"]["review_reasons"] = [
            "paid_modifiers_excluded_from_line_totals",
        ]
        result = assess_kitchen_readiness(
            preview, plu_approved=True, price_policy_approved=True,
            instruction_schema_verified=True,
        )
        self.assertIn("amount_requires_financial_review", result["blockers"])
        self.assertFalse(result["checks_passed"])
        self.assertFalse(result["dispatch_performed"])
        self.assertFalse(result["writes"])

    def test_unverified_non_text_and_blank_instructions_block_readiness(self):
        from copy import deepcopy
        preview = deepcopy(self.preview)
        preview["instruction_field_audit"]["non_text_candidate_paths"] = [
            "body.order.special_instructions",
        ]
        preview["instruction_field_audit"]["blank_candidate_paths"] = [
            "body.order.items[0].notes",
        ]
        result = assess_kitchen_readiness(preview)
        self.assertIn("non_text_instruction_candidates", result["blockers"])
        self.assertIn("blank_instruction_candidates", result["blockers"])
        self.assertFalse(result["checks_passed"])
        self.assertFalse(result["dispatch_performed"])
        self.assertFalse(result["writes"])

    def test_unsafe_instruction_controls_block_readiness(self):
        from copy import deepcopy
        preview = deepcopy(self.preview)
        preview["instruction_field_audit"]["unsafe_control_candidate_paths"] = [
            "body.order.special_instructions",
        ]
        result = assess_kitchen_readiness(preview)
        self.assertIn("unsafe_instruction_candidates", result["blockers"])
        self.assertFalse(result["checks_passed"])
        self.assertFalse(result["writes"])

    def test_incomplete_or_missing_instruction_scan_blocks_readiness(self):
        from copy import deepcopy
        for incomplete in (False, None, "true"):
            with self.subTest(scan_complete=incomplete):
                preview = deepcopy(self.preview)
                if incomplete is None:
                    preview["instruction_field_audit"].pop("scan_complete")
                else:
                    preview["instruction_field_audit"]["scan_complete"] = incomplete
                result = assess_kitchen_readiness(preview)
                self.assertIn("instruction_scan_incomplete", result["blockers"])
                self.assertFalse(result["checks_passed"])
                self.assertFalse(result["dispatch_performed"])
                self.assertFalse(result["writes"])

    def test_missing_control_diagnostic_blocks_readiness(self):
        from copy import deepcopy
        preview = deepcopy(self.preview)
        preview["instruction_field_audit"].pop("unsafe_control_candidate_paths")
        result = assess_kitchen_readiness(preview)
        self.assertIn("instruction_candidate_diagnostics_missing", result["blockers"])
        self.assertFalse(result["checks_passed"])

    def test_unsafe_kitchen_labels_block_readiness(self):
        from copy import deepcopy
        for bad_label in ("Burger\nFAUSSE COMMANDE", "Burger\x1b[2J", "Burger\x85"):
            preview = deepcopy(self.preview)
            preview["items"][0]["name"] = bad_label
            result = assess_kitchen_readiness(preview)
            self.assertIn("invalid_kitchen_item", result["blockers"])
            self.assertFalse(result["checks_passed"])
            self.assertFalse(result["dispatch_performed"])
            self.assertFalse(result["writes"])

        for key in ("group", "name"):
            preview = deepcopy(self.preview)
            preview["items"][0]["options"][0][key] = "Extras\r\nFAUSSE LIGNE"
            result = assess_kitchen_readiness(preview)
            self.assertIn("invalid_kitchen_modifier", result["blockers"])
            self.assertFalse(result["checks_passed"])

    def test_normal_french_kitchen_labels_remain_valid(self):
        from copy import deepcopy
        preview = deepcopy(self.preview)
        preview["items"][0]["name"] = "Burgér à l'échalote"
        preview["items"][0]["options"][0]["group"] = "Suppléments"
        preview["items"][0]["options"][0]["name"] = "Crème fraîche"
        result = assess_kitchen_readiness(preview)
        self.assertNotIn("invalid_kitchen_item", result["blockers"])
        self.assertNotIn("invalid_kitchen_modifier", result["blockers"])
        self.assertFalse(result["dispatch_performed"])

    def test_invalid_preview_never_passes(self):
        result = assess_kitchen_readiness(
            {"writes": True, "items": []}, plu_approved=True,
            price_policy_approved=True, instruction_schema_verified=True,
        )
        self.assertIn("invalid_read_only_preview", result["blockers"])
        self.assertIn("missing_kitchen_items", result["blockers"])


if __name__ == "__main__":
    unittest.main()
