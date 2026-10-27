"""Static guards for sandbox-only Deliveroo remake filtering."""
import ast
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "clean_caisse" / "app.py"


class BisDeliverooRemakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = APP.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.function = next(node for node in cls.tree.body
                            if isinstance(node, ast.FunctionDef)
                            and node.name == "_deliveroo_remake_view")
        cls.code = ast.get_source_segment(cls.source, cls.function)

    def test_isolated_to_bis_app(self):
        self.assertIn("app_fad0809f-954d-47e7-983d-afb7c3867cd0", self.code)
        self.assertIn("BECHEFAA_DELIVEROO_ORDER_BRIDGE_ENABLED", self.code)

    def test_parent_hidden_only_after_child_import(self):
        self.assertIn("if child_pos in imported_replacements:", self.code)
        self.assertIn("hidden.add(parent_pos)", self.code)
        self.assertIn("SELECT id FROM caisse_orders WHERE id = ANY(%s)", self.code)

    def test_remake_reference_and_payment(self):
        for marker in ('item["is_deliveroo_remake"] = True',
                       'item["platform"] = "Deliveroo"',
                       'item["payment"] = "PAYÉ EN LIGNE"'):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.code)

    def test_short_hold_and_safe_fallback(self):
        self.assertIn("15000", self.code)
        self.assertIn("return orders", self.code)
        self.assertIn("preserving all orders", self.code)

    def test_deliveroo_channel_and_fulfillment_visible_on_bis_screens(self):
        # A marketplace channel must not replace the operational pickup/delivery mode.
        self.assertIn("?'DELIVEROO · '+esc(o.ticket_type):esc(o.ticket_type)", self.source)
        self.assertIn("?'Deliveroo · '+esc(o.ticket_type):esc(o.ticket_type)", self.source)
        self.assertIn("o.sales_channel", self.source)

    def test_filter_used_by_kitchen_and_history(self):
        self.assertGreaterEqual(self.source.count("_deliveroo_remake_view(conn, orders)"), 2)


if __name__ == "__main__":
    unittest.main()
