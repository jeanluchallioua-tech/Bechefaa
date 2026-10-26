"""Read-only regression tests for the Deliveroo menu identifier contract."""
import unittest
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch

from clean_caisse.deliveroo_menu_builder_phase6 import build_deliveroo_menu_preview


class _FakeConnection:
    def commit(self):
        pass


@contextmanager
def _fake_db():
    yield _FakeConnection()


class DeliverooMenuIdentifierTests(unittest.TestCase):
    def preview(self, products):
        data = {"categories": [{"id": "c1", "name": "Burgers"}],
                "products": products}
        with patch("clean_caisse.deliveroo_menu_builder_phase6._catalog", return_value=data), \
             patch("clean_caisse.deliveroo_menu_builder_phase6._markup_percentage",
                   return_value=Decimal("15.00")):
            return build_deliveroo_menu_preview(_fake_db)

    @staticmethod
    def product(identifier, *, active=True, options=None):
        return {"id": identifier, "name": "Burger", "category": "Burgers",
                "price": 8, "active": active, "options": options or []}

    def assert_blocked(self, preview, expected_type):
        self.assertFalse(preview["plu_contract_ready"])
        self.assertIn(expected_type,
                      [x["type"] for x in preview["plu_contract_blockers"]])
        self.assertFalse(preview["upload_performed"])

    def test_clean_catalogue_is_not_blocked(self):
        preview = self.preview([self.product("MU11002")])
        self.assertTrue(preview["plu_contract_ready"])
        self.assertEqual(preview["plu_contract_blockers"], [])
        self.assertFalse(preview["upload_performed"])

    def test_generated_choice_plu_roundtrips_to_strict_reconciler(self):
        from clean_caisse.deliveroo_order_reconcile_phase6 import reconcile
        from tests.test_deliveroo_order_reconcile import sample

        options = [{"name": "Extras", "options": [
            {"id": "extra-1", "name": "Guacamole", "price": 0.95},
        ]}]
        product = self.product("MU11002", options=options)
        preview = self.preview([product])
        self.assertTrue(preview["plu_contract_ready"])
        items = preview["payload"]["menu"]["items"]
        choice = next(item for item in items if item["type"] == "CHOICE")
        main = next(item for item in items if item["type"] == "ITEM")
        self.assertEqual(main["plu"], "MU11002")
        self.assertEqual(choice["plu"], "opt:MU11002:0:0")
        payload = sample()
        payload["body"]["order"]["items"][0]["modifiers"][0]["pos_item_id"] = choice["plu"]
        result = reconcile(payload, {"products": [product]})
        self.assertEqual(result["mapped_items"][0]["options"], [
            {"group": "Extras", "name": "Guacamole", "quantity": 1}
        ])
        self.assertFalse(result["writes"])

    def test_explicit_zero_choice_price_beats_legacy_fallbacks(self):
        options = [{"name": "Sauces", "options": [
            {"name": "Mayo", "price": 0, "extraPrice": 0.95,
             "supplement": 1.50},
        ]}]
        preview = self.preview([self.product("MU11002", options=options)])
        choice = next(
            item for item in preview["payload"]["menu"]["items"]
            if item["type"] == "CHOICE"
        )
        self.assertEqual(choice["price_info"]["price"], 0)
        self.assertFalse(preview["upload_performed"])

    def test_duplicate_hidden_product_id_blocks_reconciliation(self):
        preview = self.preview([
            self.product("MU11002"),
            self.product("MU11002", active=False),
        ])
        self.assert_blocked(preview, "duplicate_catalog_product_plu")

    def test_padded_product_id_blocks_reconciliation(self):
        preview = self.preview([self.product(" MU11002 ")])
        self.assert_blocked(preview, "noncanonical_catalog_product_plu")

    def test_generated_item_id_collision_blocks_preview(self):
        preview = self.preview([self.product("A-B"), self.product("A_B")])
        self.assert_blocked(preview, "generated_item_id_collision")

    def test_duplicate_generated_choice_id_blocks_preview(self):
        options = [{"name": "Sauces", "options": [
            {"id": "sauce", "name": "Mayo", "price": 0},
            {"id": "sauce", "name": "Mayo", "price": 0},
        ]}]
        preview = self.preview([self.product("MU11002", options=options)])
        self.assert_blocked(preview, "generated_choice_id_collision")

    def test_inactive_modifier_group_is_not_considered_reconcilable(self):
        options = [{"name": "Sauces", "active": False, "options": [
            {"id": "sauce", "name": "Mayo"},
        ]}]
        preview = self.preview([self.product("MU11002", options=options)])
        self.assert_blocked(preview, "inactive_modifier_group_exposed")

    def test_inactive_modifier_choice_is_not_considered_reconcilable(self):
        options = [{"name": "Sauces", "options": [
            {"id": "sauce", "name": "Mayo", "active": False},
        ]}]
        preview = self.preview([self.product("MU11002", options=options)])
        self.assert_blocked(preview, "inactive_modifier_choice_exposed")

    def test_malformed_hidden_catalogue_entry_blocks_preview(self):
        preview = self.preview([self.product("MU11002"), None])
        self.assert_blocked(preview, "invalid_catalog_product")


if __name__ == "__main__":
    unittest.main()
