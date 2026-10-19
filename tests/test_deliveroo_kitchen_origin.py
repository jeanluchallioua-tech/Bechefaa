import unittest

from clean_caisse.deliveroo_kitchen_origin_phase6 import (
    DELIVEROO_COLOR, kitchen_origin, kitchen_origin_html,
)


class DeliverooKitchenOriginTests(unittest.TestCase):
    def test_deliveroo_has_brand_color_and_print_header(self):
        origin = kitchen_origin("deliveroo", "7866")
        self.assertEqual(origin["color"], "#00CCBC")
        self.assertEqual(origin["print_header"], "COMMANDE DELIVEROO - 7866")
        self.assertEqual(DELIVEROO_COLOR, "#00CCBC")

    def test_other_channels_not_relabelled(self):
        for channel in ("SITE", "CAISSE", "UBER EATS", None):
            self.assertIsNone(kitchen_origin(channel, "7866"))
            self.assertEqual(kitchen_origin_html(channel, "7866"), "")

    def test_order_number_is_html_escaped(self):
        markup = kitchen_origin_html("DELIVEROO", '<img src=x onerror=alert(1)>')
        self.assertNotIn("<img", markup)
        self.assertIn("&lt;img", markup)


if __name__ == "__main__":
    unittest.main()
