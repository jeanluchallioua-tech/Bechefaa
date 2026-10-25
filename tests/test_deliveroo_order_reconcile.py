import unittest
from clean_caisse.deliveroo_order_reconcile_phase6 import reconcile
from clean_caisse.deliveroo_order_mapping_phase6 import DeliverooMappingError


def sample():
    return {
        "event": "order.new",
        "body": {"order": {
            "id": "fr:test-7866",
            "display_id": "7866",
            "total_price": {"fractional": 895, "currency_code": "EUR"},
            "items": [{
                "pos_item_id": "MU11002",
                "name": "Veggie Burger",
                "quantity": 1,
                "unit_price": {"fractional": 800, "currency_code": "EUR"},
                "total_price": {"fractional": 895, "currency_code": "EUR"},
                "modifiers": [{
                    "pos_item_id": "opt:MU11002:0:0",
                    "name": "Guacamole",
                    "quantity": 1,
                    "unit_price": {"fractional": 95, "currency_code": "EUR"},
                }],
            }],
        }},
    }


class DeliverooReconcileTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"products": [{
            "id": "MU11002", "name": "Veggie Burger", "active": True,
            "options": [{"name": "Suppléments", "options": [{"name": "Guacamole", "price": 0.95}]}],
        }]}

    def test_valid_product_and_modifier(self):
        result = reconcile(sample(), self.catalog)
        self.assertEqual(result["mapped_items"][0]["options"], [
            {"group": "Suppléments", "name": "Guacamole", "quantity": 1}])
        self.assertFalse(result["writes"])
        self.assertTrue(result["requires_price_policy"])

    def test_repeated_modifier_lines_remain_distinct(self):
        payload = sample()
        first = payload["body"]["order"]["items"][0]["modifiers"][0]
        first["quantity"] = 2
        payload["body"]["order"]["items"][0]["modifiers"].append({
            **first, "quantity": 1,
        })
        result = reconcile(payload, self.catalog)
        self.assertEqual(
            [option["quantity"] for option in result["mapped_items"][0]["options"]],
            [2, 1],
        )
        self.assertEqual(
            [option["name"] for option in result["mapped_items"][0]["options"]],
            ["Guacamole", "Guacamole"],
        )
        self.assertFalse(result["writes"])

    def test_repeated_product_lines_preserve_individual_quantities(self):
        payload = sample()
        first = payload["body"]["order"]["items"][0]
        first["quantity"] = 2
        payload["body"]["order"]["items"].append({
            **first, "quantity": 1,
        })
        result = reconcile(payload, self.catalog)
        self.assertEqual(
            [item["qty"] for item in result["mapped_items"]], [2, 1]
        )
        self.assertEqual(len(result["mapped_items"]), 2)
        self.assertFalse(result["writes"])

    def test_multiple_modifier_units_preserved(self):
        payload = sample()
        payload["body"]["order"]["items"][0]["modifiers"][0]["quantity"] = 3
        result = reconcile(payload, self.catalog)
        self.assertEqual(result["mapped_items"][0]["options"], [
            {"group": "Suppléments", "name": "Guacamole", "quantity": 3}])
        self.assertFalse(result["writes"])

    def test_unknown_product_rejected(self):
        payload = sample()
        payload["body"]["order"]["items"][0]["pos_item_id"] = "UNKNOWN"
        with self.assertRaises(DeliverooMappingError):
            reconcile(payload, self.catalog)

    def test_blank_option_name_rejected(self):
        for bad in ("", "   ", "\t"):
            with self.subTest(bad=bad):
                self.catalog["products"][0]["options"][0]["options"][0]["name"] = bad
                with self.assertRaisesRegex(DeliverooMappingError, "Empty choice"):
                    reconcile(sample(), self.catalog)

    def test_option_name_is_trimmed(self):
        self.catalog["products"][0]["options"][0]["options"][0]["name"] = "  Guacamole  "
        result = reconcile(sample(), self.catalog)
        self.assertEqual(result["mapped_items"][0]["options"][0]["name"], "Guacamole")

    def test_inactive_option_group_rejected(self):
        self.catalog["products"][0]["options"][0]["active"] = False
        with self.assertRaisesRegex(DeliverooMappingError, "Inactive catalogue option group"):
            reconcile(sample(), self.catalog)

    def test_inactive_option_choice_rejected(self):
        self.catalog["products"][0]["options"][0]["options"][0]["active"] = False
        with self.assertRaisesRegex(DeliverooMappingError, "Inactive catalogue option choice"):
            reconcile(sample(), self.catalog)

    def test_integer_zero_disables_product_group_and_choice(self):
        from copy import deepcopy
        for kind in ("product", "group", "choice"):
            with self.subTest(kind=kind):
                catalog = deepcopy(self.catalog)
                product = catalog["products"][0]
                target = {
                    "product": product,
                    "group": product["options"][0],
                    "choice": product["options"][0]["options"][0],
                }[kind]
                target["active"] = 0
                with self.assertRaises(DeliverooMappingError):
                    reconcile(sample(), catalog)

    def test_malformed_active_flags_fail_closed(self):
        from copy import deepcopy
        for bad in ("false", "0", None, 2, -1, [], {}):
            for kind in ("product", "group", "choice"):
                with self.subTest(value=bad, kind=kind):
                    catalog = deepcopy(self.catalog)
                    product = catalog["products"][0]
                    target = {
                        "product": product,
                        "group": product["options"][0],
                        "choice": product["options"][0]["options"][0],
                    }[kind]
                    target["active"] = bad
                    with self.assertRaisesRegex(
                        DeliverooMappingError, "Invalid catalogue active flag"
                    ):
                        reconcile(sample(), catalog)

    def test_integer_one_remains_enabled(self):
        self.catalog["products"][0]["active"] = 1
        self.catalog["products"][0]["options"][0]["active"] = 1
        self.catalog["products"][0]["options"][0]["options"][0]["active"] = 1
        result = reconcile(sample(), self.catalog)
        self.assertEqual(result["mapped_items"][0]["product_id"], "MU11002")
        self.assertFalse(result["writes"])

    def test_active_option_choice_still_maps(self):
        self.catalog["products"][0]["options"][0]["active"] = True
        self.catalog["products"][0]["options"][0]["options"][0]["active"] = True
        result = reconcile(sample(), self.catalog)
        self.assertEqual(result["mapped_items"][0]["options"][0]["name"], "Guacamole")

    def test_padded_catalogue_product_id_rejected(self):
        for bad in (" MU11002", "MU11002 ", "\tMU11002"):
            with self.subTest(bad=bad):
                self.catalog["products"][0]["id"] = bad
                with self.assertRaisesRegex(DeliverooMappingError, "Non-canonical catalogue product ID"):
                    reconcile(sample(), self.catalog)

    def test_invalid_catalogue_container_rejected(self):
        for bad in (None, [], "catalogue", 7):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(DeliverooMappingError, "Invalid catalogue"):
                    reconcile(sample(), bad)

    def test_invalid_catalogue_product_entry_rejected(self):
        for bad in (None, "MU11002", [], 7):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(DeliverooMappingError, "Invalid catalogue product entry"):
                    reconcile(sample(), {"products": [bad]})

    def test_invalid_catalogue_product_collection_rejected(self):
        for bad in ({}, "products", 7, True):
            with self.subTest(bad=bad):
                with self.assertRaises(DeliverooMappingError):
                    reconcile(sample(), {"products": bad})

    def test_nonstring_catalogue_product_id_rejected(self):
        for bad in (12, True, None, ["MU11002"]):
            with self.subTest(bad=bad):
                self.catalog["products"][0]["id"] = bad
                with self.assertRaises(DeliverooMappingError):
                    reconcile(sample(), self.catalog)

    def test_missing_catalogue_product_id_rejected(self):
        self.catalog["products"][0]["id"] = "   "
        with self.assertRaises(DeliverooMappingError):
            reconcile(sample(), self.catalog)

    def test_invalid_catalogue_option_groups_rejected(self):
        for bad in ("options", {"name": "Suppléments"}, 12, True):
            with self.subTest(bad=bad):
                self.catalog["products"][0]["options"] = bad
                with self.assertRaises(DeliverooMappingError):
                    reconcile(sample(), self.catalog)

    def test_invalid_catalogue_option_group_entry_rejected(self):
        for bad in (None, "Suppléments", 7, []):
            with self.subTest(bad=bad):
                self.catalog["products"][0]["options"] = [bad]
                with self.assertRaises(DeliverooMappingError):
                    reconcile(sample(), self.catalog)

    def test_negative_or_noncanonical_option_indices_rejected(self):
        for plu in ("opt:MU11002:-1:0", "opt:MU11002:0:-1",
                    "opt:MU11002:+0:0", "opt:MU11002:00:0",
                    "opt:MU11002:0:00", "opt:MU11002:０:0"):
            with self.subTest(plu=plu):
                payload = sample()
                payload["body"]["order"]["items"][0]["modifiers"][0]["pos_item_id"] = plu
                with self.assertRaises(DeliverooMappingError):
                    reconcile(payload, self.catalog)

    def test_unrecognized_modifier_rejected(self):
        payload = sample()
        payload["body"]["order"]["items"][0]["modifiers"][0]["pos_item_id"] = "OM21001"
        with self.assertRaises(DeliverooMappingError):
            reconcile(payload, self.catalog)


if __name__ == "__main__":
    unittest.main()
