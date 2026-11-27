import ast
import unittest
from pathlib import Path

# Load the exact pure functions without requiring Flask or a database.
source = Path(__file__).resolve().parents[1] / "clean_caisse" / "deliveroo_menu_builder_phase6.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
names = {"compare_deliveroo_prices", "prepare_deliveroo_price_patch"}
module = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[])
namespace = {}
exec(compile(module, str(source), "exec"), namespace)
compare = namespace["compare_deliveroo_prices"]
prepare = namespace["prepare_deliveroo_price_patch"]

def menu(price):
    return {"menu": {"items": [{"id": "salade", "plu": "42", "price_info": {"price": price, "overrides": []}, "modifier_ids": ["sauce"]}], "categories": [{"id": "salades"}]}}

class PriceSyncTests(unittest.TestCase):
    def test_price(self):
        old = menu(840)
        result = prepare(menu(900), old)
        self.assertEqual(result["candidate"], menu(900))
        self.assertEqual(old, menu(840))
        self.assertFalse(result["upload_performed"])

    def test_unchanged(self):
        self.assertEqual(compare(menu(900), menu(900))["changes"], [])

    def test_missing(self):
        with self.assertRaises(ValueError):
            prepare(menu(900), {"menu": {"items": []}})

    def test_override(self):
        old = menu(840)
        old["menu"]["items"][0]["price_info"]["overrides"] = [{"price": 800}]
        with self.assertRaises(ValueError):
            prepare(menu(900), old)

    def test_invalid_price(self):
        with self.assertRaises(ValueError):
            compare(menu(True), menu(840))

    def test_duplicate(self):
        old = menu(840)
        old["menu"]["items"] *= 2
        with self.assertRaises(ValueError):
            compare(menu(900), old)

if __name__ == "__main__":
    unittest.main()
