import unittest
from contextlib import contextmanager
from datetime import date
from unittest.mock import patch
from flask import Flask
from clean_caisse.google_ads_site_sales import period_bounds, site_sales
from clean_caisse.google_ads_admin import register_google_ads_admin

class SiteSalesTests(unittest.TestCase):
    def test_periods(self):
        today = date(2026, 11, 26)
        self.assertEqual(period_bounds("LAST_7_DAYS", today=today), (date(2026,11,19), date(2026,11,25)))
        self.assertEqual(period_bounds("TODAY", today=today), (today,today))

    def test_receipts_and_refunds(self):
        class Connection:
            def execute(self, query, params):
                assert "sales_channel" in query and "SUCCEEDED" in query
                return self
            def fetchall(self):
                return [{"day":date(2026,11,25),"order_id":"a","paid":20,"refunded":0},
                        {"day":date(2026,11,26),"order_id":"a","paid":29.5,"refunded":5},
                        {"day":date(2026,11,26),"order_id":"b","paid":0,"refunded":4}]
        @contextmanager
        def db():
            yield Connection()
        result = site_sales(db,"CUSTOM","2026-11-25","2026-11-26")
        self.assertEqual(result["count"],1)
        self.assertEqual(result["paid"],49.5)
        self.assertEqual(result["refunds"],9)
        self.assertEqual(result["net"],40.5)
        self.assertEqual(result["average"],49.5)
        self.assertEqual(result["days"][1]["net"],20.5)

    def test_dashboard_independent_of_ads(self):
        app = Flask(__name__)
        app.secret_key = "test"
        register_google_ads_admin(app, lambda: None)
        with app.test_client() as client:
            with client.session_transaction() as session:
                session["caisse_auth"] = True
            sales = {"count":1,"paid":49.5,"refunds":0,"net":49.5,"average":49.5,
                     "days":[{"date":"2026-11-26","net":49.5}]}
            with patch("clean_caisse.google_ads_admin.site_sales",return_value=sales), patch("clean_caisse.google_ads_admin.report",return_value=("Indisponible",None)):
                r = client.get("/administration/google-ads")
                self.assertEqual(r.status_code,200)
                self.assertIn(b"49,50",r.data)
                self.assertIn(b"Net encaiss",r.data)

if __name__ == "__main__":
    unittest.main()
