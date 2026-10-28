import unittest
from copy import deepcopy

from clean_caisse.deliveroo_explicit_plu_map_phase6 import reconcile_with_explicit_plu_map
from clean_caisse.deliveroo_order_mapping_phase6 import DeliverooMappingError
from tests.test_deliveroo_order_reconcile import sample


class ExplicitPluMapTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"products": [{
            "id": "MU11002", "name": "Veggie Burger",
            "options": [{"name": "Extras", "options": [{"name": "Guacamole"}]}],
        }]}
        self.payload = sample()
        self.payload["body"]["order"]["items"][0]["modifiers"][0]["pos_item_id"] = "OM21001"

    def test_approved_parent_scoped_mapping_is_read_only(self):
        original = deepcopy(self.payload)
        result = reconcile_with_explicit_plu_map(
            self.payload, self.catalog, {("MU11002", "OM21001"): "opt:MU11002:0:0"}
        )
        self.assertEqual(self.payload, original)
        self.assertEqual(result["mapped_items"][0]["options"][0]["name"], "Guacamole")
        self.assertFalse(result["writes"])
        self.assertFalse(result["ready_for_dispatch"])

    def test_unapproved_mapping_is_rejected(self):
        with self.assertRaisesRegex(DeliverooMappingError, "Unapproved"):
            reconcile_with_explicit_plu_map(self.payload, self.catalog, {})

    def test_cross_product_mapping_is_rejected(self):
        with self.assertRaisesRegex(DeliverooMappingError, "Invalid approved|Cross-product"):
            reconcile_with_explicit_plu_map(
                self.payload, self.catalog, {("MU11002", "OM21001"): "opt:OTHER:0:0"}
            )

    def test_legacy_mapping_cannot_silently_change_choice(self):
        catalog = deepcopy(self.catalog)
        catalog["products"][0]["options"][0]["options"].append({"name": "Cheddar"})
        with self.assertRaisesRegex(DeliverooMappingError, "label mismatch"):
            reconcile_with_explicit_plu_map(
                self.payload, catalog, {("MU11002", "OM21001"): "opt:MU11002:0:1"}
            )

    def test_legacy_mapping_requires_source_label(self):
        self.payload["body"]["order"]["items"][0]["modifiers"][0]["name"] = ""
        with self.assertRaisesRegex(DeliverooMappingError, "label mismatch"):
            reconcile_with_explicit_plu_map(
                self.payload, self.catalog, {("MU11002", "OM21001"): "opt:MU11002:0:0"}
            )

    def test_legacy_label_control_character_cannot_be_trimmed_into_match(self):
        # The old .strip() accepted a trailing newline as an exact label
        # match, even though it is unsafe to trust as kitchen text.
        for label in ("Guacamole\n", "Guacamole\x7f", "Guaca\x85mole"):
            with self.subTest(label=repr(label)):
                payload = deepcopy(self.payload)
                payload["body"]["order"]["items"][0]["modifiers"][0]["name"] = label
                with self.assertRaisesRegex(DeliverooMappingError, "Unsafe legacy"):
                    reconcile_with_explicit_plu_map(
                        payload, self.catalog,
                        {("MU11002", "OM21001"): "opt:MU11002:0:0"}
                    )

    def test_mapped_catalogue_label_and_group_must_be_printable(self):
        for location in ("choice", "group"):
            with self.subTest(location=location):
                payload = deepcopy(self.payload)
                catalog = deepcopy(self.catalog)
                if location == "choice":
                    catalog["products"][0]["options"][0]["options"][0]["name"] = "Guaca\nmole"
                    payload["body"]["order"]["items"][0]["modifiers"][0]["name"] = "Guacamole"
                else:
                    catalog["products"][0]["options"][0]["name"] = "Extras\n"
                # The strict reconciler now rejects unsafe labels before the
                # explicit translator performs its own final safety check.
                with self.assertRaisesRegex(DeliverooMappingError, "Unsafe (mapped|catalogue)"):
                    reconcile_with_explicit_plu_map(
                        payload, catalog,
                        {("MU11002", "OM21001"): "opt:MU11002:0:0"}
                    )

    def test_same_legacy_plu_with_conflicting_labels_is_rejected(self):
        modifiers = self.payload["body"]["order"]["items"][0]["modifiers"]
        conflicting = deepcopy(modifiers[0])
        conflicting["name"] = "Cheddar"
        modifiers.append(conflicting)
        with self.assertRaisesRegex(DeliverooMappingError, "Conflicting legacy modifier labels"):
            reconcile_with_explicit_plu_map(
                self.payload, self.catalog, {("MU11002", "OM21001"): "opt:MU11002:0:0"}
            )

    def test_same_legacy_plu_with_same_label_is_allowed(self):
        modifiers = self.payload["body"]["order"]["items"][0]["modifiers"]
        modifiers.append(deepcopy(modifiers[0]))
        result = reconcile_with_explicit_plu_map(
            self.payload, self.catalog, {("MU11002", "OM21001"): "opt:MU11002:0:0"}
        )
        self.assertEqual(len(result["mapped_items"][0]["options"]), 2)
        self.assertFalse(result["writes"])

    def test_invalid_unused_mapping_entry_is_rejected(self):
        mapping = {
            ("MU11002", "OM21001"): "opt:MU11002:0:0",
            ("OTHER", "OLD"): "opt:MU11002:0:0",
        }
        with self.assertRaisesRegex(DeliverooMappingError, "Invalid approved"):
            reconcile_with_explicit_plu_map(self.payload, self.catalog, mapping)

    def test_noncanonical_mapping_key_is_rejected(self):
        with self.assertRaisesRegex(DeliverooMappingError, "Invalid approved"):
            reconcile_with_explicit_plu_map(
                self.payload, self.catalog, {"MU11002:OM21001": "opt:MU11002:0:0"}
            )

    def test_two_legacy_ids_cannot_alias_same_choice(self):
        mapping = {
            ("MU11002", "OM21001"): "opt:MU11002:0:0",
            ("MU11002", "OM21002"): "opt:MU11002:0:0",
        }
        with self.assertRaisesRegex(DeliverooMappingError, "Ambiguous approved"):
            reconcile_with_explicit_plu_map(self.payload, self.catalog, mapping)

    def test_canonical_source_cannot_be_remapped_as_legacy(self):
        mapping = {
            ("MU11002", "OM21001"): "opt:MU11002:0:0",
            ("MU11002", "opt:MU11002:0:0"): "opt:MU11002:0:0",
        }
        with self.assertRaisesRegex(DeliverooMappingError, "Invalid approved"):
            reconcile_with_explicit_plu_map(self.payload, self.catalog, mapping)

    def test_padded_legacy_source_is_rejected(self):
        for source in (" OM21001", "OM21001 ", "\tOM21001"):
            with self.subTest(source=source):
                mapping = {("MU11002", source): "opt:MU11002:0:0"}
                with self.assertRaisesRegex(DeliverooMappingError, "Invalid approved"):
                    reconcile_with_explicit_plu_map(self.payload, self.catalog, mapping)

    def test_noncanonical_target_indices_are_rejected(self):
        for target in ("opt:MU11002:00:0", "opt:MU11002:0:01", "opt:MU11002:0:-1", "opt:MU11002:0:0:1"):
            with self.subTest(target=target):
                with self.assertRaises(DeliverooMappingError):
                    reconcile_with_explicit_plu_map(
                        self.payload, self.catalog, {("MU11002", "OM21001"): target}
                    )

    def test_invalid_target_is_rejected(self):
        with self.assertRaises(DeliverooMappingError):
            reconcile_with_explicit_plu_map(
                self.payload, self.catalog, {("MU11002", "OM21001"): 5}
            )


    def test_legacy_plu_inventory_is_read_only_and_never_approves(self):
        from clean_caisse.deliveroo_explicit_plu_map_phase6 import audit_modifier_plu_sources
        original = deepcopy(self.payload)
        self.payload["body"]["order"]["items"][0]["modifiers"].append(
            deepcopy(self.payload["body"]["order"]["items"][0]["modifiers"][0])
        )
        expected_payload = deepcopy(self.payload)
        audit = audit_modifier_plu_sources(self.payload)
        self.assertEqual(self.payload, expected_payload)
        self.assertEqual(audit["legacy_source_count"], 1)
        self.assertEqual(audit["legacy_sources"], [{
            "parent_pos_item_id": "MU11002",
            "legacy_modifier_pos_item_id": "OM21001",
            "source_labels": ["Guacamole"],
            "occurrences": 2,
            "conflicting_labels": False,
            "missing_label": False,
        }])
        self.assertTrue(audit["requires_explicit_mapping_review"])
        self.assertFalse(audit["mapping_approved"])
        self.assertFalse(audit["ready_for_dispatch"])
        self.assertFalse(audit["writes"])
        self.assertNotEqual(self.payload, original)

    def test_inventory_flags_conflicting_or_missing_legacy_labels(self):
        from clean_caisse.deliveroo_explicit_plu_map_phase6 import audit_modifier_plu_sources
        modifiers = self.payload["body"]["order"]["items"][0]["modifiers"]
        conflicting = deepcopy(modifiers[0])
        conflicting["name"] = "Cheddar"
        modifiers.append(conflicting)
        audit = audit_modifier_plu_sources(self.payload)
        self.assertEqual(audit["conflicting_label_sources"], [["MU11002", "OM21001"]])
        self.assertEqual(audit["missing_label_sources"], [])
        modifiers[1]["name"] = ""
        audit = audit_modifier_plu_sources(self.payload)
        self.assertEqual(audit["missing_label_sources"], [["MU11002", "OM21001"]])
        self.assertFalse(audit["mapping_approved"])

    def test_inventory_malformed_opt_prefix_is_not_canonical(self):
        from clean_caisse.deliveroo_explicit_plu_map_phase6 import audit_modifier_plu_sources
        modifiers = self.payload["body"]["order"]["items"][0]["modifiers"]
        for plu in ("opt:MU11002:00:0", "opt:OTHER:0:0", "opt:MU11002:0"):
            extra = deepcopy(modifiers[0])
            extra["pos_item_id"] = plu
            modifiers.append(extra)
        modifiers[0]["pos_item_id"] = "opt:MU11002:00:0"
        original = deepcopy(self.payload)
        audit = audit_modifier_plu_sources(self.payload)
        self.assertEqual(self.payload, original)
        self.assertEqual(audit["legacy_sources"], [])
        self.assertEqual(audit["canonical_modifier_occurrences_unverified"], 0)
        self.assertEqual(audit["malformed_prefixed_sources"], [
            {"parent_pos_item_id": "MU11002",
             "received_modifier_pos_item_id": "opt:MU11002:0",
             "occurrences": 1},
            {"parent_pos_item_id": "MU11002",
             "received_modifier_pos_item_id": "opt:MU11002:00:0",
             "occurrences": 2},
            {"parent_pos_item_id": "MU11002",
             "received_modifier_pos_item_id": "opt:OTHER:0:0",
             "occurrences": 1},
        ])
        self.assertTrue(audit["requires_explicit_mapping_review"])
        self.assertFalse(audit["mapping_approved"])
        self.assertFalse(audit["ready_for_dispatch"])
        self.assertFalse(audit["writes"])

    def test_inventory_oversized_prefixed_plu_requires_review(self):
        from clean_caisse.deliveroo_explicit_plu_map_phase6 import audit_modifier_plu_sources
        for plu in ("opt:MU11002:1234567890:0",
                    "opt:MU11002:0:" + "9" * 5000):
            with self.subTest(length=len(plu)):
                payload = deepcopy(self.payload)
                payload["body"]["order"]["items"][0]["modifiers"][0]["pos_item_id"] = plu
                result = audit_modifier_plu_sources(payload)
                self.assertEqual(result["canonical_modifier_occurrences_unverified"], 0)
                self.assertEqual(result["malformed_prefixed_sources"], [{
                    "parent_pos_item_id": "MU11002",
                    "received_modifier_pos_item_id": plu,
                    "occurrences": 1,
                }])
                self.assertTrue(result["requires_explicit_mapping_review"])
                self.assertFalse(result["ready_for_dispatch"])

    def test_inventory_separates_canonical_and_legacy(self):
        from clean_caisse.deliveroo_explicit_plu_map_phase6 import audit_modifier_plu_sources
        modifiers = self.payload["body"]["order"]["items"][0]["modifiers"]
        canonical = deepcopy(modifiers[0])
        canonical["pos_item_id"] = "opt:MU11002:0:0"
        modifiers.append(canonical)
        audit = audit_modifier_plu_sources(self.payload)
        self.assertEqual(audit["legacy_source_count"], 1)
        self.assertEqual(audit["canonical_modifier_occurrences_unverified"], 1)
        self.assertEqual(audit["malformed_prefixed_sources"], [])
        self.assertTrue(audit["requires_explicit_mapping_review"])
        self.assertFalse(audit["ready_for_dispatch"])

    def test_inventory_canonical_prefix_is_not_mapping_approval(self):
        from clean_caisse.deliveroo_explicit_plu_map_phase6 import audit_modifier_plu_sources
        modifier = self.payload["body"]["order"]["items"][0]["modifiers"][0]
        modifier["pos_item_id"] = "opt:MU11002:0:0"
        audit = audit_modifier_plu_sources(self.payload)
        self.assertEqual(audit["legacy_sources"], [])
        self.assertEqual(audit["canonical_modifier_occurrences_unverified"], 1)
        self.assertFalse(audit["requires_explicit_mapping_review"])
        self.assertFalse(audit["mapping_approved"])
        self.assertFalse(audit["ready_for_dispatch"])
        self.assertFalse(audit["writes"])


if __name__ == "__main__":
    unittest.main()
