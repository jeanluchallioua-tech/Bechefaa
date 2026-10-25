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

    def test_malformed_hidden_catalogue_entry_blocks_preview(self):
        preview = self.preview([self.product("MU11002"), None])
        self.assert_blocked(preview, "invalid_catalog_product")


if __name__ == "__main__":
    unittest.main()
