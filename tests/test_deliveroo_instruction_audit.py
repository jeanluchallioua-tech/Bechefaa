"""Read-only regression coverage for Deliveroo instruction-field discovery.

These checks do not authorize printing customer notes: the POS bridge must
continue rejecting non-empty unmapped instructions until kitchen mapping is
explicitly approved and validated on real hardware.
"""
import copy
import unittest

from clean_caisse.deliveroo_instruction_audit_phase6 import audit_instruction_fields


def event():
    return {"event": "order.new", "body": {"order": {
        "id": "fr:example", "items": [{
            "pos_item_id": "MU11002", "modifiers": [{"pos_item_id": "OM21001"}],
        }],
    }}}


class DeliverooInstructionAuditTests(unittest.TestCase):
    def test_documented_order_notes_are_discovered_without_writes(self):
        payload = event()
        payload["body"]["order"]["order_notes"] = "Sans oignons"
        payload["body"]["order"]["cutlery_notes"] = "Sans couverts"
        original = copy.deepcopy(payload)
        result = audit_instruction_fields(payload)
        self.assertEqual(result["documented_order_note_paths"], [
            "body.order.cutlery_notes", "body.order.order_notes",
        ])
        self.assertEqual(result["candidate_paths"], result["documented_order_note_paths"])
        self.assertFalse(result["schema_verified"])
        self.assertFalse(result["writes"])
        self.assertEqual(payload, original)

    def test_nested_item_and_modifier_notes_are_discovered(self):
        payload = event()
        item = payload["body"]["order"]["items"][0]
        item["special_instructions"] = "Bien cuit"
        item["modifiers"][0]["customer_note"] = "Sans sauce"
        result = audit_instruction_fields(payload)
        self.assertEqual(result["candidate_paths"], [
            "body.order.items[0].modifiers[0].customer_note",
            "body.order.items[0].special_instructions",
        ])
        self.assertEqual(result["documented_order_note_paths"], [])

    def test_non_text_note_is_flagged_not_converted_to_printable_text(self):
        payload = event()
        payload["body"]["order"]["order_notes"] = {"text": "Sans oignons"}
        result = audit_instruction_fields(payload)
        self.assertEqual(result["non_text_candidate_paths"], ["body.order.order_notes"])
        self.assertEqual(result["candidate_values"][0]["value"], {"text": "Sans oignons"})

    def test_blank_and_control_character_notes_are_diagnostic_only(self):
        payload = event()
        payload["body"]["order"]["order_notes"] = "  \n "
        payload["body"]["order"]["items"][0]["instructions"] = "Sans sel\x00"
        result = audit_instruction_fields(payload)
        self.assertEqual(result["blank_candidate_paths"], ["body.order.order_notes"])
        self.assertEqual(result["unsafe_control_candidate_paths"],
                         ["body.order.items[0].instructions"])
        self.assertFalse(result["writes"])

    def test_missing_or_malformed_order_is_safe(self):
        for payload in (None, {}, {"body": None}, {"body": {"order": []}}):
            with self.subTest(payload=payload):
                result = audit_instruction_fields(payload)
                self.assertEqual(result["candidate_paths"], [])
                self.assertFalse(result["schema_verified"])
                self.assertFalse(result["writes"])

    def test_unrelated_fields_are_not_mistaken_for_customer_notes(self):
        payload = event()
        payload["body"]["order"]["customer_name"] = "Camille"
        payload["body"]["order"]["items"][0]["name"] = "Burger"
        self.assertEqual(audit_instruction_fields(payload)["candidate_paths"], [])


if __name__ == "__main__":
    unittest.main()
