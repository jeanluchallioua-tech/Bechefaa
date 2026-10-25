"""Non-regression guards for the isolated BIS integration branch.

Run with: python -m unittest discover -s tests -p 'test_bis_integration_guard.py'
These are structural guards, not a fiscal compliance certificate.
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "clean_caisse" / "app.py"


class BisIntegrationGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = APP.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_deliveroo_bridge_preserved(self):
        functions = {node.name for node in ast.walk(self.tree)
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertIn("_deliveroo_remake_view", functions)
        self.assertIn("create_order", functions)
        self.assertIn("orders_history", functions)

    def test_discount_fields_present(self):
        for field in ("manual_discount_percent", "discount_amount",
                      "subtotal_before_discount"):
            with self.subTest(field=field):
                self.assertIn("ADD COLUMN IF NOT EXISTS " + field, self.source)

    def test_order_creation_uses_server_side_discount(self):
        self.assertIn("order_discount(subtotal, payload, source)", self.source)
        self.assertIn(
            "SET discount_amount=%s,subtotal_before_discount=%s,manual_discount_percent=%s",
            self.source,
        )
        self.assertIn("manual_discount_percent:manualDiscountForCart()", self.source)

    def test_offline_replay_preserves_saved_discount(self):
        self.assertIn(
            "SELECT id,num,total,status,source,discount_amount,"
            "manual_discount_percent,subtotal_before_discount "
            "FROM caisse_orders WHERE offline_sync_key=%s",
            self.source,
        )

    def test_discount_ui_and_deliveroo_poll_coexist(self):
        self.assertIn("function chooseManualDiscount()", self.source)
        self.assertIn("checkDeliveroo();setInterval(checkDeliveroo,5000)", self.source)


if __name__ == "__main__":
    unittest.main()
