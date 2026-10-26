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
        if "ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS deliveroo_import_fingerprint" in sql:
            return Rows()
        if "SELECT id, deliveroo_import_fingerprint FROM caisse_orders WHERE id=%s" in sql:
            stored = self.orders.get(params[0])
            return Rows({"id": params[0], "deliveroo_import_fingerprint": stored[-1]}
                        if stored is not None else None)
        if "SELECT COALESCE(MAX(num),0)+1" in sql:
            return Rows({"n": len(self.orders) + 1})
        if "INSERT INTO caisse_orders" in sql:
            self.orders[params[0]] = params
            return Rows()
        if "INSERT INTO caisse_order_items" in sql:
            self.items.append(params)
            return Rows()
        raise AssertionError("Unexpected SQL: " + sql)



class TransactionalFailureDB(FakeDB):
    """Model rollback after a failed item INSERT; never contacts PostgreSQL."""

    def __init__(self):
        super().__init__()
        self.fail_second_item_once = True

    @contextlib.contextmanager
    def transaction(self):
        previous_orders = copy.deepcopy(self.orders)
        previous_items = copy.deepcopy(self.items)
        try:
            yield
        except Exception:
            self.orders = previous_orders
            self.items = previous_items
            raise

    def execute(self, sql, params=()):
        if ("INSERT INTO caisse_order_items" in sql
                and self.fail_second_item_once and len(self.items) == 1):
            self.fail_second_item_once = False
            raise RuntimeError("simulated second item INSERT failure")
        return super().execute(sql, params)


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

    def test_same_external_id_with_changed_price_is_rejected_not_silently_replayed(self):
        db = FakeDB()
        first = payload()
        changed = copy.deepcopy(first)
        changed["body"]["order"]["items"][0]["total_price"]["fractional"] = 1990
        self.assertEqual(self.bridge(db, first), "created")
        with self.assertRaisesRegex(ValueError, "order ID replay content conflict"):
            self.bridge(db, changed)
        self.assertEqual(len(db.orders), 1)
        self.assertEqual(len(db.items), 1)
        self.assertEqual(str(db.items[0][5]), "8.95")

    def test_same_external_id_with_changed_options_is_rejected(self):
        db = FakeDB()
        first = payload()
        changed = copy.deepcopy(first)
        changed["body"]["order"]["items"][0]["modifiers"][0]["name"] = "Sans oignons"
        self.assertEqual(self.bridge(db, first), "created")
        with self.assertRaisesRegex(ValueError, "order ID replay content conflict"):
            self.bridge(db, changed)
        self.assertEqual(len(db.orders), 1)
        self.assertEqual(len(db.items), 1)

    def test_declared_order_total_matching_lines_is_imported_once(self):
        db = FakeDB()
        event = payload()
        event["body"]["order"]["total_price"] = {
            "fractional": 1790, "currency_code": "EUR"}
        self.assertEqual(self.bridge(db, event), "created")
        self.assertEqual(self.bridge(db, copy.deepcopy(event)), "duplicate")
        self.assertEqual(len(db.orders), 1)
        self.assertEqual(len(db.items), 1)

    def test_non_divisible_line_cents_require_review_before_database(self):
        # Three units for EUR 10.00 cannot be represented as one POS
        # cent-denominated unit price without changing the charged total.
        for cents, qty in ((1000, 3), (1, 2), (1790, 3)):
            with self.subTest(cents=cents, qty=qty):
                db = FakeDB()
                event = payload()
                line = event["body"]["order"]["items"][0]
                line["quantity"] = qty
                line["total_price"]["fractional"] = cents
                with self.assertRaisesRegex(ValueError, "exact cent unit price"):
                    self.bridge(db, event)
                self.assertEqual(db.statements, [])
                self.assertEqual(db.orders, {})
                self.assertEqual(db.items, [])

    def test_divisible_line_cents_keep_exact_pos_unit_price(self):
        db = FakeDB()
        event = payload()
        line = event["body"]["order"]["items"][0]
        line["quantity"] = 3
        line["total_price"]["fractional"] = 1200
        self.assertEqual(self.bridge(db, event), "created")
        self.assertEqual(str(db.items[0][5]), "4")
        self.assertEqual(self.bridge(db, copy.deepcopy(event)), "duplicate")
        self.assertEqual(len(db.orders), 1)
        self.assertEqual(len(db.items), 1)

    def test_order_total_difference_requires_financial_review_before_database(self):
        # Fees, discounts and modifier totals need an approved policy.
        for cents in (1791, 0, 1800):
            with self.subTest(cents=cents):
                db = FakeDB()
                event = payload()
                event["body"]["order"]["total_price"] = {
                    "fractional": cents, "currency_code": "EUR"}
                with self.assertRaisesRegex(ValueError, "financial review required"):
                    self.bridge(db, event)
                self.assertEqual(db.statements, [])

    def test_malformed_declared_order_and_unit_prices_fail_before_database(self):
        for field in ("total_price", "unit_price"):
            for invalid in (None, {"fractional": True, "currency_code": "EUR"},
                            {"fractional": -1, "currency_code": "EUR"},
                            {"fractional": 1790, "currency_code": "USD"},
                            {"fractional": "1790", "currency_code": "EUR"}):
                with self.subTest(field=field, invalid=invalid):
                    db = FakeDB()
                    event = payload()
                    target = (event["body"]["order"] if field == "total_price"
                              else event["body"]["order"]["items"][0])
                    target[field] = invalid
                    with self.assertRaises(ValueError):
                        self.bridge(db, event)
                    self.assertEqual(db.statements, [])

    def test_unexplained_unit_price_mismatch_without_modifiers_is_blocked_before_db(self):
        # No modifier can explain the discrepancy; a discount or fee needs
        # a reviewed accounting policy before the POS may import the order.
        for unit_cents, line_cents, qty in ((800, 1790, 2), (900, 1790, 2),
                                             (0, 100, 1)):
            with self.subTest(unit=unit_cents, total=line_cents, qty=qty):
                conn = FakeDB()
                event = payload()
                item = event["body"]["order"]["items"][0]
                item["quantity"] = qty
                item["modifiers"] = []
                item["unit_price"] = {"fractional": unit_cents, "currency_code": "EUR"}
                item["total_price"]["fractional"] = line_cents
                with self.assertRaisesRegex(ValueError, "unit and line prices differ"):
                    self.bridge(conn, event)
                self.assertEqual(conn.statements, [])
                self.assertEqual(conn.orders, {})
                self.assertEqual(conn.items, [])

    def test_exact_unit_price_without_modifiers_still_imports_once(self):
        conn = FakeDB()
        event = payload()
        item = event["body"]["order"]["items"][0]
        item["modifiers"] = []
        item["unit_price"] = {"fractional": 895, "currency_code": "EUR"}
        self.assertEqual(self.bridge(conn, event), "created")
        self.assertEqual(self.bridge(conn, copy.deepcopy(event)), "duplicate")
        self.assertEqual(len(conn.orders), 1)
        self.assertEqual(len(conn.items), 1)

    def test_declared_modifier_price_is_fingerprinted_but_not_added_to_pos_options(self):
        db = FakeDB()
        event = payload()
        event["body"]["order"]["items"][0]["modifiers"][0]["unit_price"] = {
            "fractional": 95, "currency_code": "EUR"}
        self.assertEqual(self.bridge(db, event), "created")
        self.assertEqual(self.bridge(db, copy.deepcopy(event)), "duplicate")
        # The kitchen/POS options_json contract must remain unchanged.
        self.assertEqual(json.loads(db.items[0][6]), [
            {"name": "Guacamole", "plu": "OM21001"}])
        replay = copy.deepcopy(event)
        replay["body"]["order"]["items"][0]["modifiers"][0]["unit_price"]["fractional"] = 100
        with self.assertRaisesRegex(ValueError, "order ID replay content conflict"):
            self.bridge(db, replay)
        self.assertEqual(len(db.orders), 1)
        self.assertEqual(len(db.items), 1)

    def test_new_modifier_price_field_cannot_silently_change_replay(self):
        db = FakeDB()
        first = payload()  # No modifier price in the legacy payload.
        self.assertEqual(self.bridge(db, first), "created")
        changed = copy.deepcopy(first)
        changed["body"]["order"]["items"][0]["modifiers"][0]["unit_price"] = {
            "fractional": 95, "currency_code": "EUR"}
        with self.assertRaisesRegex(ValueError, "order ID replay content conflict"):
            self.bridge(db, changed)
        self.assertEqual(len(db.orders), 1)
        self.assertEqual(len(db.items), 1)

    def test_malformed_modifier_price_fails_before_database_access(self):
        for invalid in (None, {"fractional": True, "currency_code": "EUR"},
                        {"fractional": -1, "currency_code": "EUR"},
                        {"fractional": 95, "currency_code": "USD"},
                        {"fractional": "95", "currency_code": "EUR"}):
            with self.subTest(invalid=invalid):
                db = FakeDB()
                event = payload()
                event["body"]["order"]["items"][0]["modifiers"][0]["unit_price"] = invalid
                with self.assertRaises(ValueError):
                    self.bridge(db, event)
                self.assertEqual(db.statements, [])

    def test_changed_reported_unit_price_cannot_replay_same_order_id(self):
        db = FakeDB()
        event = payload()
        event["body"]["order"]["items"][0]["unit_price"] = {
            "fractional": 895, "currency_code": "EUR"}
        self.assertEqual(self.bridge(db, event), "created")
        replay = copy.deepcopy(event)
        replay["body"]["order"]["items"][0]["unit_price"]["fractional"] = 900
        with self.assertRaisesRegex(ValueError, "order ID replay content conflict"):
            self.bridge(db, replay)
        self.assertEqual(len(db.orders), 1)
        self.assertEqual(len(db.items), 1)

    def test_changed_declared_order_total_cannot_replay_same_order_id(self):
        db = FakeDB()
        event = payload()
        self.assertEqual(self.bridge(db, event), "created")
        replay = copy.deepcopy(event)
        replay["body"]["order"]["total_price"] = {
            "fractional": 1790, "currency_code": "EUR"}
        with self.assertRaisesRegex(ValueError, "order ID replay content conflict"):
            self.bridge(db, replay)
        self.assertEqual(len(db.orders), 1)
        self.assertEqual(len(db.items), 1)

    def test_legacy_existing_order_without_fingerprint_requires_review(self):
        db = FakeDB()
        first = payload()
        self.assertEqual(self.bridge(db, first), "created")
        order_id = next(iter(db.orders))
        db.orders[order_id] = db.orders[order_id][:-1] + (None,)
        with self.assertRaisesRegex(ValueError, "order ID replay content conflict"):
            self.bridge(db, copy.deepcopy(first))
        self.assertEqual(len(db.orders), 1)
        self.assertEqual(len(db.items), 1)

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

    def test_modifier_quantity_survives_pos_json_and_kitchen_text(self):
        db = FakeDB()
        event = payload()
        event["body"]["order"]["items"][0]["modifiers"][0]["quantity"] = 3
        self.assertEqual(self.bridge(db, event), "created")
        self.assertEqual(json.loads(db.items[0][6]), [
            {"name": "Guacamole", "plu": "OM21001", "quantity": 3}])
        self.assertEqual(db.items[0][7], "Guacamole ×3")
        self.assertEqual(self.bridge(db, copy.deepcopy(event)), "duplicate")
        self.assertEqual(len(db.items), 1)

    def test_invalid_modifier_containers_rejected_without_database_access(self):
        for invalid in ("", {}, False, 0, "Guacamole"):
            with self.subTest(invalid=repr(invalid)):
                db = FakeDB()
                event = payload()
                event["body"]["order"]["items"][0]["modifiers"] = invalid
                with self.assertRaises(ValueError):
                    self.bridge(db, event)
                self.assertEqual(db.statements, [])

    def test_unmapped_customer_notes_are_not_silently_dropped(self):
        for scope, field in (("order", "order_notes"),
                             ("order", "cutlery_notes"),
                             ("order", "special_instructions"),
                             ("item", "instructions"),
                             ("modifier", "customer_note")):
            with self.subTest(scope=scope, field=field):
                db = FakeDB()
                event = payload()
                order = event["body"]["order"]
                target = (order if scope == "order" else
                          order["items"][0] if scope == "item" else
                          order["items"][0]["modifiers"][0])
                target[field] = "Sans oignons"
                with self.assertRaisesRegex(ValueError, "instructions require"):
                    self.bridge(db, event)
                self.assertEqual(db.statements, [])

    def test_empty_customer_note_does_not_block_import(self):
        db = FakeDB()
        event = payload()
        event["body"]["order"]["order_notes"] = "   "
        self.assertEqual(self.bridge(db, event), "created")

    def test_other_event_cannot_enter_order_new_bridge(self):
        db = FakeDB()
        event = payload()
        event["event"] = "order.status_update"
        with self.assertRaisesRegex(ValueError, "order.new"):
            self.bridge(db, event)
        self.assertEqual(db.statements, [])

    def test_disabled_and_nonpreproduction_never_touch_database(self):
        for flags in ({"enabled": False}, {"sandbox": False}):
            with self.subTest(flags=flags):
                db = FakeDB()
                self.assertIn(self.bridge(db, payload(), **flags),
                              ("disabled", "not_preproduction"))
                self.assertEqual(db.statements, [])


    def test_failed_second_item_rolls_back_then_retry_creates_one_complete_order(self):
        # A partial kitchen order must never survive a failed transaction.
        # This verifies the bridge's transaction boundary with a rollback
        # double, not real PostgreSQL concurrency or printer behavior.
        conn = TransactionalFailureDB()
        event = payload()
        second = copy.deepcopy(event["body"]["order"]["items"][0])
        second.update(pos_item_id="MU11003", name="Second Burger",
                      quantity=1, total_price={"fractional": 895, "currency_code": "EUR"})
        event["body"]["order"]["items"].append(second)
        with self.assertRaisesRegex(RuntimeError, "simulated second item INSERT failure"):
            self.bridge(conn, event)
        self.assertEqual(conn.orders, {})
        self.assertEqual(conn.items, [])
        self.assertEqual(self.bridge(conn, copy.deepcopy(event)), "created")
        self.assertEqual(len(conn.orders), 1)
        self.assertEqual(len(conn.items), 2)
        self.assertEqual(self.bridge(conn, copy.deepcopy(event)), "duplicate")
        self.assertEqual(len(conn.orders), 1)
        self.assertEqual(len(conn.items), 2)



if __name__ == "__main__":
    unittest.main()
