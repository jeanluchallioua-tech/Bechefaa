"""Pure discount calculation and scope tests; no database or deployment required."""
import unittest
from decimal import Decimal
from clean_caisse.manual_discount import order_discount


class BisDiscountRulesTests(unittest.TestCase):
    def test_percentage_and_total(self):
        amount, total, percent = order_discount(
            Decimal("30.00"), {"manual_discount_percent": 10}, "EMPORTER")
        self.assertEqual((amount, total, percent),
                         (Decimal("3.00"), Decimal("27.00"), Decimal("10.00")))

    def test_decimal_comma_and_rounding(self):
        amount, total, percent = order_discount(
            Decimal("19.99"), {"manual_discount_percent": "12,5"}, "COMPTOIR")
        self.assertEqual((amount, total, percent),
                         (Decimal("2.50"), Decimal("17.49"), Decimal("12.50")))

    def test_invalid_percentages(self):
        for value in (-1, 100, "NaN", "Infinity", "bad"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                order_discount(Decimal("30.00"),
                               {"manual_discount_percent": value}, "EMPORTER")

    def test_restricted_service(self):
        for mode in ("LIVRAISON", "SALLE"):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                order_discount(Decimal("30.00"),
                               {"manual_discount_percent": 10}, mode)

    def test_online_channel_and_coupon_not_cumulative(self):
        for extras in ({"sales_channel": "DELIVEROO"},
                       {"sales_channel": "SITE"},
                       {"coupon_code": "YARON10"}):
            with self.subTest(extras=extras), self.assertRaises(ValueError):
                order_discount(Decimal("30.00"),
                               {"manual_discount_percent": 10, **extras},
                               "EMPORTER")

    def test_invalid_subtotal_rejected(self):
        for subtotal in ("NaN", "Infinity", "-1", "invalid", None):
            with self.subTest(subtotal=subtotal), self.assertRaises(ValueError):
                order_discount(subtotal, {"manual_discount_percent": 10}, "EMPORTER")

    def test_string_subtotal_supported(self):
        self.assertEqual(
            order_discount("30.00", {"manual_discount_percent": 10}, "EMPORTER"),
            (Decimal("3.00"), Decimal("27.00"), Decimal("10.00")))

    def test_zero_discount_allowed(self):
        amount, total, percent = order_discount(
            Decimal("30.00"), {"manual_discount_percent": 0}, "SALLE")
        self.assertEqual((amount, total, percent),
                         (Decimal("0.00"), Decimal("30.00"), Decimal("0.00")))

    def test_existing_percentage_recalculated(self):
        amount, total, percent = order_discount(
            Decimal("45.00"), {}, "EMPORTER",
            existing={"manual_discount_percent": Decimal("10.00")})
        self.assertEqual((amount, total, percent),
                         (Decimal("4.50"), Decimal("40.50"), Decimal("10.00")))


if __name__ == "__main__":
    unittest.main()
