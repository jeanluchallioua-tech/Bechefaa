import unittest
from clean_caisse.deliveroo_order_pricing_phase6 import net_item_cents, cents


def money(value):
    return {'fractional': value, 'currency_code': 'EUR'}


class PricingTests(unittest.TestCase):
    def test_actual_9034_discount(self):
        order = {'total_price': money(1100), 'offer_discount': money(100),
                 'items': [{'total_price': money(1200), 'discount_amount': money(100)}]}
        self.assertEqual(net_item_cents(order), [1100])

    def test_already_discounted_lines_not_discounted_twice(self):
        self.assertEqual(net_item_cents({'total_price': money(1100), 'offer_discount': money(100),
            'items': [{'total_price': money(1100), 'discount_amount': money(100)}]}), [1100])

    def test_basket_discount_preserves_total_to_the_cent(self):
        result = net_item_cents({'total_price': money(1001), 'offer_discount': money(199),
            'items': [{'total_price': money(600)}, {'total_price': money(600)}]})
        self.assertEqual(result, [501, 500])

    def test_mixed_item_and_basket_offer_not_applied_twice(self):
        self.assertEqual(net_item_cents({'total_price': money(900), 'offer_discount': money(300),
            'items': [{'total_price': money(600), 'discount_amount': money(100)}, {'total_price': money(600)}]}), [409, 491])

    def test_no_promotion_unchanged(self):
        self.assertEqual(net_item_cents({'items': [{'total_price': money(1200)}]}), [1200])

    def test_inconsistent_total_refused(self):
        with self.assertRaises(ValueError):
            net_item_cents({'total_price': money(999), 'offer_discount': money(100),
                'items': [{'total_price': money(1200)}]})

    def test_missing_discounted_total_refused(self):
        with self.assertRaises(ValueError):
            net_item_cents({'offer_discount': money(100), 'items': [{'total_price': money(1200)}]})

    def test_invalid_money_refused(self):
        for amount in (True, -1, 'NaN', 'Infinity', 1.5, None):
            with self.assertRaises(ValueError):
                cents(money(amount))
        with self.assertRaises(ValueError):
            cents({'fractional': 100, 'currency_code': 'GBP'})


if __name__ == '__main__':
    unittest.main()
