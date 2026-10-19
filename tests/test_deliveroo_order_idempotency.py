import unittest
from clean_caisse.deliveroo_order_idempotency_phase6 import (
    external_order_key, classify_replay,
)
from clean_caisse.deliveroo_order_mapping_phase6 import DeliverooMappingError


class DeliverooIdempotencyTests(unittest.TestCase):
    def test_same_order_has_same_key(self):
        self.assertEqual(external_order_key("fr:7866"), external_order_key("fr:7866"))

    def test_environment_isolated(self):
        self.assertNotEqual(
            external_order_key("fr:7866", "sandbox"),
            external_order_key("fr:7866", "production"),
        )

    def test_replay(self):
        self.assertEqual(classify_replay("fr:7866", "fr:7866"), "replay")

    def test_new_order(self):
        self.assertEqual(classify_replay(None, "fr:7866"), "create")

    def test_conflict(self):
        self.assertEqual(classify_replay("fr:1234", "fr:7866"), "conflict")

    def test_empty_id_rejected(self):
        with self.assertRaises(DeliverooMappingError):
            external_order_key("")


if __name__ == "__main__":
    unittest.main()
