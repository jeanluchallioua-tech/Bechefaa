"""Phase 6 — diagnostic non sensible des variables d'environnement.

Cette route n'expose jamais les valeurs secrètes. Elle indique uniquement si
les variables attendues sont présentes dans le runtime Clever Cloud.
"""
import os
from flask import jsonify


def register_env_diagnostic_isolated_phase6(app):
    @app.get("/api/env-diagnostic-phase6")
    def env_diagnostic_phase6():
        test_value = str(os.getenv("BECHEFAA_TEST_ENV") or "").strip()
        return jsonify({
            "ok": True,
            "test_env_present": bool(test_value),
            "test_env_matches": test_value == "OK123",
            "mollie_api_key_present": bool(str(os.getenv("MOLLIE_API_KEY") or "").strip()),
            "mollie_return_url_present": bool(str(os.getenv("BECHEFAA_MOLLIE_RETURN_URL") or "").strip()),
            "mollie_site_enabled_present": os.getenv("BECHEFAA_MOLLIE_SITE_ENABLED") is not None,
        })
