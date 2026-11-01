"""Tests du calcul de la promotion identique, sans caisse ni base de données."""
import unittest
from clean_caisse.promo_identical_preprod import calculate_identical_second_half_off as calc


class IdenticalPromotionTests(unittest.TestCase):
    def test_two_shawarmas(self):
        self.assertEqual(calc([{"product_id": "shaw", "quantity": 2, "unit_price_cents": 1400}], ["shaw"])["total_discount_cents"], 700)

    def test_mixed_items_not_a_pair(self):
        lines = [{"product_id": "shaw", "quantity": 1, "unit_price_cents": 1400},
                 {"product_id": "bzh", "quantity": 1, "unit_price_cents": 1500}]
        self.assertEqual(calc(lines, ["shaw", "bzh"])["total_discount_cents"], 0)

    def test_four_burgers(self):
        self.assertEqual(calc([{"product_id": "bzh", "quantity": 4, "unit_price_cents": 1500}], ["bzh"])["total_discount_cents"], 1500)

    def test_three_burgers(self):
        self.assertEqual(calc([{"product_id": "bzh", "quantity": 3, "unit_price_cents": 1500}], ["bzh"])["total_discount_cents"], 750)

    def test_formula_excluded(self):
        lines = [{"product_id": "bzh", "quantity": 1, "unit_price_cents": 1500},
                 {"product_id": "bzh", "quantity": 1, "unit_price_cents": 1500, "is_formula": True}]
        self.assertEqual(calc(lines, ["bzh"])["total_discount_cents"], 0)

    def test_extras_not_discounted(self):
        lines = [{"product_id": "shaw", "quantity": 2, "unit_price_cents": 1400, "extras_total_cents": 400}]
        self.assertEqual(calc(lines, ["shaw"])["total_discount_cents"], 700)

    def test_disabled(self):
        self.assertEqual(calc([{"product_id": "shaw", "quantity": 2, "unit_price_cents": 1400}], ["shaw"], enabled=False)["total_discount_cents"], 0)


if __name__ == "__main__":
    unittest.main()
