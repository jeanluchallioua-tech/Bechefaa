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


if __name__ == "__main__":
    unittest.main()
