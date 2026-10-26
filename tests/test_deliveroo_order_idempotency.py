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

    def test_nonstring_order_ids_cannot_be_hashed(self):
        for invalid in (None, 123, True, ["fr:7866"], {"id": "fr:7866"}):
            with self.subTest(invalid=invalid):
                with self.assertRaises(DeliverooMappingError):
                    external_order_key(invalid)

    def test_new_order_classification_rejects_invalid_incoming_id(self):
        for invalid in (None, "", "   ", 123, True):
            with self.subTest(invalid=invalid):
                with self.assertRaises(DeliverooMappingError):
                    classify_replay(None, invalid)

    def test_new_order_classification_rejects_invalid_environment(self):
        with self.assertRaises(DeliverooMappingError):
            classify_replay(None, "fr:7866", environment="staging")

    def test_replay_key_rejects_noncanonical_ids_like_webhook_parser(self):
        for invalid in (" fr:7866", "fr:7866 ", "fr:\t7866",
                        "fr:7866\n", "fr:7866\x1b[2J", "fr:7866\x9b[2J"):
            with self.subTest(invalid=repr(invalid)):
                with self.assertRaises(DeliverooMappingError):
                    external_order_key(invalid)
                with self.assertRaises(DeliverooMappingError):
                    classify_replay(None, invalid)
                with self.assertRaises(DeliverooMappingError):
                    classify_replay(invalid, "fr:7866")

    def test_empty_id_rejected(self):
        with self.assertRaises(DeliverooMappingError):
            external_order_key("")


if __name__ == "__main__":
    unittest.main()
