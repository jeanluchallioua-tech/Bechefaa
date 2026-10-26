"""BIS-only marketplace pricing defaults and non-destructive partial updates."""
import re
import unittest
from contextlib import nullcontext
from decimal import Decimal

from flask import Flask
from clean_caisse.marketplace_markup_phase6 import register_marketplace_markup_phase6
from clean_caisse.deliveroo_menu_builder_phase6 import _markup_percentage, _marked_price


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConn:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def transaction(self):
        return nullcontext()

    def execute(self, sql, params=()):
        if "CREATE TABLE IF NOT EXISTS marketplace_markup_settings" in sql:
            return Rows([])
        if "INSERT INTO marketplace_markup_settings" in sql:
            if "ON CONFLICT(channel) DO NOTHING" in sql:
                if params:
                    channel, percentage = params
                else:
                    match = re.search(r"VALUES\\('([^']+)',([0-9.]+)\\)", sql)
                    if not match:
                        raise AssertionError(sql)
                    channel, percentage = match.groups()
                self.values.setdefault(channel, Decimal(str(percentage)))
            elif "ON CONFLICT(channel) DO UPDATE" in sql:
                channel, percentage = params
                self.values[channel] = Decimal(str(percentage))
            else:
                raise AssertionError(sql)
            return Rows([])
        if "SELECT channel,percentage,updated_at" in sql:
            return Rows([
                {"channel": channel, "percentage": value, "updated_at": None}
                for channel, value in self.values.items()
            ])
        if "SELECT percentage FROM marketplace_markup_settings" in sql:
            return Rows(
                [{"percentage": self.values["DELIVEROO"]}]
                if "DELIVEROO" in self.values else []
            )
        raise AssertionError(sql)


class MarketplaceMarkupBisTests(unittest.TestCase):
    def client(self, conn):
        app = Flask(__name__)
        def db():
            return nullcontext(conn)
        register_marketplace_markup_phase6(app, db)
        return app.test_client()

    def test_new_settings_default_to_15_uber_and_20_deliveroo(self):
        conn = FakeConn()
        response = self.client(conn).get("/api/marketplace/markups-phase6")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["markups"], {"UBER_EATS": 15.0, "DELIVEROO": 20.0})

    def test_partial_deliveroo_update_preserves_existing_uber(self):
        conn = FakeConn({"UBER_EATS": Decimal("17.50"), "DELIVEROO": Decimal("15.00")})
        response = self.client(conn).post(
            "/api/marketplace/markups-phase6",
            json={"markups": {"DELIVEROO": 20}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["markups"], {"UBER_EATS": 17.5, "DELIVEROO": 20.0})
        self.assertEqual(conn.values["UBER_EATS"], Decimal("17.50"))

    def test_menu_builder_uses_20_only_for_new_deliveroo_settings(self):
        conn = FakeConn()
        self.assertEqual(_markup_percentage(conn), Decimal("20.00"))
        self.assertEqual(_marked_price(Decimal("10.00"), Decimal("20.00")), Decimal("12.00"))
        self.assertEqual(_marked_price(Decimal("0.00"), Decimal("20.00")), Decimal("0.00"))

    def test_menu_builder_preserves_existing_configured_percentage(self):
        conn = FakeConn({"DELIVEROO": Decimal("22.50")})
        self.assertEqual(_markup_percentage(conn), Decimal("22.50"))
        self.assertEqual(conn.values["DELIVEROO"], Decimal("22.50"))


if __name__ == "__main__":
    unittest.main()
