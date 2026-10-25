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
        with self.assertRaisesRegex(DeliverooMappingError, "Cross-product"):
            reconcile_with_explicit_plu_map(
                self.payload, self.catalog, {("MU11002", "OM21001"): "opt:OTHER:0:0"}
            )

    def test_invalid_target_is_rejected(self):
        with self.assertRaises(DeliverooMappingError):
            reconcile_with_explicit_plu_map(
                self.payload, self.catalog, {("MU11002", "OM21001"): 5}
            )


if __name__ == "__main__":
    unittest.main()
