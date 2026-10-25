"""Ensure unsafe menu previews never reach an outbound Deliveroo request."""
import unittest
from unittest.mock import patch

from flask import Flask

from clean_caisse.deliveroo_menu_upload_phase6 import (
    _menu_plu_preflight_error, register_deliveroo_menu_upload_phase6,
)


class DeliverooMenuUploadGuardTests(unittest.TestCase):
    def test_preflight_fails_closed_for_missing_contract(self):
        for preview in (
            None, {}, {"plu_contract_ready": False},
            {"plu_contract_ready": True},
            {"plu_contract_ready": True, "plu_contract_blockers": [
                {"type": "duplicate_catalog_product_plu"}
            ]},
        ):
            with self.subTest(preview=preview):
                result = _menu_plu_preflight_error(preview)
                self.assertFalse(result["ok"])
                self.assertFalse(result["upload_performed"])
                self.assertEqual(result["stage"], "plu_contract")

    def test_preflight_accepts_explicitly_valid_contract(self):
        self.assertIsNone(_menu_plu_preflight_error({
            "plu_contract_ready": True, "plu_contract_blockers": []
        }))

    def test_every_menu_upload_route_blocks_before_network(self):
        app = Flask(__name__)
        app.testing = True
        register_deliveroo_menu_upload_phase6(app, lambda: None)
        preview = {
            "plu_contract_ready": False,
            "plu_contract_blockers": [{
                "type": "duplicate_catalog_product_plu",
                "product_id": "MU11002",
            }],
        }
        routes = (
            "/api/deliveroo/menu-upload-phase6",
            "/api/deliveroo/scenario5-identical-menu-phase6",
            "/api/deliveroo/scenario13-upload-phase6",
            "/api/deliveroo/scenario15-v3-async-upload-phase6",
        )
        with patch(
            "clean_caisse.deliveroo_menu_upload_phase6.build_deliveroo_menu_preview",
            return_value=preview,
        ) as build, patch(
            "clean_caisse.deliveroo_menu_upload_phase6._oauth_token",
            side_effect=AssertionError("Unexpected outbound OAuth request"),
        ) as oauth, patch(
            "clean_caisse.deliveroo_menu_upload_phase6._api_json",
            side_effect=AssertionError("Unexpected outbound API request"),
        ) as api:
            for route in routes:
                with self.subTest(route=route):
                    response = app.test_client().post(
                        route, json={"site_id": "sandbox-site", "menu_id": "menu-01"}
                    )
                    self.assertEqual(response.status_code, 409)
                    body = response.get_json()
                    self.assertEqual(body["stage"], "plu_contract")
                    self.assertFalse(body["upload_performed"])
                    self.assertEqual(
                        body["blockers"][0]["type"], "duplicate_catalog_product_plu"
                    )
            self.assertEqual(build.call_count, len(routes))
            oauth.assert_not_called()
            api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
