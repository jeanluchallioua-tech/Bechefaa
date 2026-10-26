"""Isolated runtime tests of the real Deliveroo order.new POS bridge.

Execute only the nested bridge function against an in-memory SQL double.
No webhook, PostgreSQL, sandbox, kitchen or printer is contacted.
"""
import ast
import contextlib
import copy
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "clean_caisse" / "deliveroo_sandbox_phase6.py"


class Rows:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class FakeDB:
    def __init__(self):
        self.orders = {}
        self.items = []
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def transaction(self):
        return contextlib.nullcontext()

    def execute(self, sql, params=()):
        self.statements.append(sql)
        if "LOCK TABLE caisse_orders IN EXCLUSIVE MODE" in sql:
            return Rows()
        if "SELECT id FROM caisse_orders WHERE id=%s" in sql:
            return Rows({"id": params[0]} if params[0] in self.orders else None)
        if "SELECT COALESCE(MAX(num),0)+1" in sql:
            return Rows({"n": len(self.orders) + 1})
        if "INSERT INTO caisse_orders" in sql:
            self.orders[params[0]] = params
            return Rows()
        if "INSERT INTO caisse_order_items" in sql:
            self.items.append(params)
            return Rows()
        raise AssertionError("Unexpected SQL: " + sql)


def payload():
    return {
        "event": "order.new",
        "body": {"order": {
            "id": "fr:test-order-1",
            "items": [{
                "pos_item_id": "MU11002",
                "name": "Veggie Burger",
                "quantity": 2,
                "total_price": {"fractional": 1790, "currency_code": "EUR"},
                "modifiers": [{
                    "pos_item_id": "OM21001",
                    "name": "Guacamole",
                    "quantity": 1,
                }],
            }],
        }},
    }


class BisDeliverooBridgeRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        register = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == "register_deliveroo_sandbox_phase6")
        bridge = next(n for n in register.body if isinstance(n, ast.FunctionDef)
                      and n.name == "_bridge_order_new")
        cls.code = compile(ast.fix_missing_locations(
            ast.Module(body=[bridge], type_ignores=[])), str(SOURCE), "exec")

    def bridge(self, conn, order_payload, *, enabled=True, sandbox=True):
        namespace = {"os": os, "db": lambda: conn, "json": json}
        exec(self.code, namespace)
        env = {
            "CC_APP_ID": "app_fad0809f-954d-47e7-983d-afb7c3867cd0"
            if sandbox else "production-app",
            "BECHEFAA_DELIVEROO_ORDER_BRIDGE_ENABLED": "1" if enabled else "0",
        }
        stub_app = SimpleNamespace(ensure_order_schema=lambda conn: None)
        with patch.dict(os.environ, env), patch.dict(sys.modules, {"clean_caisse.app": stub_app}):
            return namespace["_bridge_order_new"](order_payload)

    def test_first_import_and_repeated_delivery_create_only_one_pos_order(self):
        db = FakeDB()
        event = payload()
        self.assertEqual(self.bridge(db, event), "created")
        self.assertEqual(self.bridge(db, copy.deepcopy(event)), "duplicate")
        self.assertEqual(len(db.orders), 1)
        self.assertEqual(len(db.items), 1)
        self.assertEqual(db.items[0][2], "MU11002")
        self.assertEqual(db.items[0][4], 2)
        self.assertEqual(str(db.items[0][5]), "8.95")
        self.assertEqual(db.items[0][6], json.dumps(
            [{"name": "Guacamole", "plu": "OM21001"}],
            ensure_ascii=False))
        self.assertEqual(sum("LOCK TABLE" in sql for sql in db.statements), 2)

    def test_different_external_order_ids_remain_distinct(self):
        db = FakeDB()
        first, second = payload(), payload()
        second["body"]["order"]["id"] = "fr:test-order-2"
        self.assertEqual(self.bridge(db, first), "created")
        self.assertEqual(self.bridge(db, second), "created")
        self.assertEqual(len(db.orders), 2)
        self.assertEqual(len(db.items), 2)

    def test_invalid_order_ids_rejected_before_database_access(self):
        for invalid in ("", " fr:test-order-1", "fr:test-order-1 ",
                        "fr:\ttest", "fr:\x1btest", 123, True, []):
            with self.subTest(invalid=repr(invalid)):
                db = FakeDB()
                event = payload()
                event["body"]["order"]["id"] = invalid
                with self.assertRaises(ValueError):
                    self.bridge(db, event)
                self.assertEqual(db.statements, [])

    def test_invalid_item_quantities_rejected_without_truncation(self):
        for invalid in (True, False, 1.5, "2", 0, -1, None):
            with self.subTest(invalid=repr(invalid)):
                db = FakeDB()
                event = payload()
                event["body"]["order"]["items"][0]["quantity"] = invalid
                with self.assertRaises(ValueError):
                    self.bridge(db, event)
                self.assertEqual(db.statements, [])

    def test_money_must_be_nonnegative_integer_eur_cents(self):
        for amount, currency in ((True, "EUR"), (12.5, "EUR"), ("1790", "EUR"),
                                 (-1, "EUR"), (None, "EUR"), (1790, "USD")):
            with self.subTest(amount=repr(amount), currency=currency):
                db = FakeDB()
                event = payload()
                event["body"]["order"]["items"][0]["total_price"] = {
                    "fractional": amount, "currency_code": currency}
                with self.assertRaises(ValueError):
                    self.bridge(db, event)
                self.assertEqual(db.statements, [])

    def test_unmapped_or_noncanonical_plu_rejected_before_database(self):
        for invalid in (None, "", " MU11002", "MU11002 ", 123):
            with self.subTest(invalid=repr(invalid)):
                db = FakeDB()
                event = payload()
                event["body"]["order"]["items"][0]["pos_item_id"] = invalid
                with self.assertRaises(ValueError):
                    self.bridge(db, event)
                self.assertEqual(db.statements, [])

    def test_invalid_modifier_is_not_silently_discarded(self):
        for invalid in (None, "Guacamole", {"name": "Guacamole"},
                        {"name": "Guacamole", "pos_item_id": "OM21001", "quantity": 1.5}):
            with self.subTest(invalid=repr(invalid)):
                db = FakeDB()
                event = payload()
                event["body"]["order"]["items"][0]["modifiers"] = [invalid]
                with self.assertRaises(ValueError):
                    self.bridge(db, event)
                self.assertEqual(db.statements, [])

    def test_disabled_and_nonpreproduction_never_touch_database(self):
        for flags in ({"enabled": False}, {"sandbox": False}):
            with self.subTest(flags=flags):
                db = FakeDB()
                self.assertIn(self.bridge(db, payload(), **flags),
                              ("disabled", "not_preproduction"))
                self.assertEqual(db.statements, [])


if __name__ == "__main__":
    unittest.main()
