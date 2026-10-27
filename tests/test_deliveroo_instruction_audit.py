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

    def test_nested_delivery_allergy_and_camelcase_notes_are_discovered(self):
        payload = event()
        order = payload["body"]["order"]
        order["delivery"] = {"instructions": "Sonner deux fois"}
        order["customer"] = {"allergy_information": "Allergie sesame"}
        order["items"][0]["modifiers"][0]["specialInstructions"] = "Sans sel"
        original = copy.deepcopy(payload)
        result = audit_instruction_fields(payload)
        self.assertEqual(result["candidate_paths"], [
            "body.order.customer.allergy_information",
            "body.order.delivery.instructions",
            "body.order.items[0].modifiers[0].specialInstructions",
        ])
        self.assertTrue(result["scan_complete"])
        self.assertFalse(result["writes"])
        self.assertEqual(payload, original)

    def test_sibling_body_instructions_are_not_silently_ignored(self):
        # Webhook schema is not approved: notes beside order must also block
        # the opt-in bridge rather than disappear from kitchen preparation.
        payload = event()
        payload["body"]["delivery"] = {"instructions": "Sonner deux fois"}
        payload["body"]["customer_notes"] = "Sans cacahuetes"
        original = copy.deepcopy(payload)
        result = audit_instruction_fields(payload)
        self.assertEqual(result["candidate_paths"], [
            "body.customer_notes",
            "body.delivery.instructions",
        ])
        self.assertTrue(result["scan_complete"])
        self.assertFalse(result["schema_verified"])
        self.assertFalse(result["writes"])
        self.assertEqual(payload, original)

    def test_sibling_body_scan_budget_is_fail_closed(self):
        payload = event()
        payload["body"]["metadata"] = ["x"] * 6000
        result = audit_instruction_fields(payload)
        self.assertFalse(result["scan_complete"])
        self.assertFalse(result["writes"])

    def test_nested_structured_note_is_not_treated_as_printable_text(self):
        payload = event()
        payload["body"]["order"]["delivery"] = {
            "delivery_instructions": {"text": "Code porte 1234"}}
        result = audit_instruction_fields(payload)
        self.assertEqual(result["non_text_candidate_paths"],
                         ["body.order.delivery.delivery_instructions"])
        self.assertFalse(result["schema_verified"])

    def test_deep_payload_is_explicitly_marked_incomplete(self):
        payload = event()
        current = payload["body"]["order"]
        for _ in range(18):
            current["context"] = {}
            current = current["context"]
        current["instructions"] = "Ne pas perdre cette note"
        result = audit_instruction_fields(payload)
        self.assertFalse(result["scan_complete"])
        self.assertFalse(result["writes"])

    def test_alternate_instruction_key_spelling_is_discovered_without_rewriting(self):
        payload = event()
        order = payload["body"]["order"]
        order["ORDER_NOTES"] = "Sans oignons"
        order["delivery"] = {"Delivery-Instructions": "Code porte"}
        order["items"][0]["Customer Notes"] = "Sans sauce"
        order["items"][0]["modifiers"][0]["SPECIAL_INSTRUCTIONS"] = "Bien cuit"
        original = copy.deepcopy(payload)
        result = audit_instruction_fields(payload)
        self.assertEqual(result["candidate_paths"], [
            "body.order.ORDER_NOTES",
            "body.order.delivery.Delivery-Instructions",
            "body.order.items[0].Customer Notes",
            "body.order.items[0].modifiers[0].SPECIAL_INSTRUCTIONS",
        ])
        self.assertTrue(result["scan_complete"])
        self.assertFalse(result["writes"])
        self.assertEqual(payload, original)

    def test_flat_object_and_scalar_array_exhaust_scan_budget(self):
        # A large object/list of scalars used to bypass the container-only
        # counter, permitting unbounded scanning before a later instruction.
        for oversized in (
            {f"metadata_{i}": "value" for i in range(6000)},
            ["value"] * 6000,
        ):
            with self.subTest(container=type(oversized).__name__):
                payload = event()
                payload["body"]["order"]["metadata"] = oversized
                result = audit_instruction_fields(payload)
                self.assertFalse(result["scan_complete"])
                self.assertFalse(result["schema_verified"])
                self.assertFalse(result["writes"])

    def test_small_flat_metadata_stays_complete(self):
        payload = event()
        payload["body"]["order"]["metadata"] = {"label": "ok", "count": 3}
        result = audit_instruction_fields(payload)
        self.assertTrue(result["scan_complete"])
        self.assertEqual(result["candidate_paths"], [])

    def test_allergy_dietary_and_kitchen_note_aliases_are_detected(self):
        payload = event()
        order = payload["body"]["order"]
        order["customer"] = {"Food Allergies": "Arachides",
                             "dietaryRequirements": "Sans gluten"}
        order["items"][0]["item_notes"] = "Cuisson longue"
        order["items"][0]["modifiers"][0]["modifier_notes"] = "Sans sauce"
        order["kitchen_notes"] = "Separer les sacs"
        original = copy.deepcopy(payload)
        result = audit_instruction_fields(payload)
        self.assertEqual(result["candidate_paths"], [
            "body.order.customer.Food Allergies",
            "body.order.customer.dietaryRequirements",
            "body.order.items[0].item_notes",
            "body.order.items[0].modifiers[0].modifier_notes",
            "body.order.kitchen_notes",
        ])
        self.assertTrue(result["scan_complete"])
        self.assertFalse(result["writes"])
        self.assertEqual(payload, original)

    def test_structured_allergies_are_not_assumed_printable(self):
        payload = event()
        payload["body"]["order"]["allergies"] = ["peanuts"]
        result = audit_instruction_fields(payload)
        self.assertEqual(result["non_text_candidate_paths"], [
            "body.order.allergies",
        ])
        self.assertFalse(result["schema_verified"])

    def test_allergen_and_preparation_aliases_are_flagged_read_only(self):
        # These aliases are precautionary, not claims about the webhook schema.
        for scope, key in (
            ("customer", "Allergen Information"),
            ("customer", "allergen_notes"),
            ("order", "customer_comments"),
            ("order", "special_request"),
            ("item", "preparationInstructions"),
            ("item", "cooking_notes"),
            ("modifier", "modifier_instructions"),
            ("modifier", "dietary_notes"),
        ):
            with self.subTest(scope=scope, key=key):
                payload = event()
                order = payload["body"]["order"]
                target = (order.setdefault("customer", {}) if scope == "customer"
                          else order if scope == "order"
                          else order["items"][0] if scope == "item"
                          else order["items"][0]["modifiers"][0])
                target[key] = "Sans allergenes"
                original = copy.deepcopy(payload)
                result = audit_instruction_fields(payload)
                self.assertEqual(len(result["candidate_paths"]), 1)
                self.assertTrue(result["candidate_paths"][0].endswith("." + key))
                self.assertTrue(result["scan_complete"])
                self.assertFalse(result["writes"])
                self.assertEqual(payload, original)

    def test_unrelated_fields_are_not_mistaken_for_customer_notes(self):
        payload = event()
        payload["body"]["order"]["customer_name"] = "Camille"
        payload["body"]["order"]["items"][0]["name"] = "Burger"
        self.assertEqual(audit_instruction_fields(payload)["candidate_paths"], [])


if __name__ == "__main__":
    unittest.main()
