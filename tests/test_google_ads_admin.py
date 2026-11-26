import unittest
from flask import Flask
from clean_caisse.google_ads_admin import register_google_ads_admin

class GoogleAdsAdminTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.secret_key = "test-only"
        @app.get("/administration")
        def admin():
            return '<a class="card" href="/administration/publicite-site">Publicité</a>'
        register_google_ads_admin(app)
        self.client = app.test_client()

    def login(self):
        with self.client.session_transaction() as session:
            session["caisse_auth"] = True

    def test_requires_authentication(self):
        self.assertEqual(self.client.get("/administration/google-ads").status_code, 303)
        self.assertNotIn(b"/administration/google-ads", self.client.get("/administration").data)

    def test_dashboard(self):
        self.login()
        response = self.client.get("/administration/google-ads")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn(b"GTM-5CLSV6BG", response.data)
        self.assertIn(b"/sandwichs-shawarma", response.data)
        self.assertIn("API non connectée".encode(), response.data)

    def test_card(self):
        self.login()
        self.assertEqual(self.client.get("/administration").data.count(b'href="/administration/google-ads"'), 1)

if __name__ == "__main__":
    unittest.main()
