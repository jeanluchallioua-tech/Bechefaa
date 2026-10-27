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

    def test_nested_customer_instructions_block_import_before_sql(self):
        for field in ("delivery", "customer"):
            with self.subTest(field=field):
                conn = FakeDB()
                event = payload()
                event["body"]["order"][field] = {
                    "delivery_instructions": "Interphone 4" if field == "delivery"
                    else "Sans allergenes"}
                with self.assertRaisesRegex(ValueError, "customer instructions"):
                    self.bridge(conn, event)
                self.assertEqual(conn.statements, [])
                self.assertEqual(conn.orders, {})

    def test_incomplete_instruction_scan_blocks_import_before_sql(self):
        conn = FakeDB()
        event = payload()
        current = event["body"]["order"]
        for _ in range(18):
            current["metadata"] = {}
            current = current["metadata"]
        current["instructions"] = "Instruction profonde"
        with self.assertRaisesRegex(ValueError, "audit incomplete"):
            self.bridge(conn, event)
        self.assertEqual(conn.statements, [])

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

    def test_deliveroo_delivery_customer_details_are_persisted(self):
        db = FakeDB()
        event = payload()
        event["body"]["order"]["customer"] = {
            "first_name": "Alice", "last_name": "Martin", "phone": "0600000000"}
        event["body"]["order"]["delivery"] = {
            "address": {"address_line_1": "12 rue Exemple",
                        "postcode": "75001", "city": "Paris"}}
        self.assertEqual(self.bridge(db, event), "created")
        saved = next(iter(db.orders.values()))
        self.assertEqual(saved[2:7], ("Alice Martin", "0600000000",
                                      "12 rue Exemple", "75001", "Paris"))
        insert_sql = next(sql for sql in db.statements if "INSERT INTO caisse_orders" in sql)
        self.assertIn("'LIVRAISON','DELIVEROO'", insert_sql)

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

    def test_prefixed_modifier_plu_must_match_parent_and_canonical_indices(self):
        # Fail before touching the database: a cross-product or malformed
        # option index could silently print a wrong kitchen selection.
        invalid_plu = (
            "opt:OTHER:0:0", "opt:MU11002:00:0",
            "opt:MU11002:0:01", "opt:MU11002:-1:0",
            "opt:MU11002:0:", "opt:MU11002:0:0:extra",
            "opt:MU11002:٠:0", "opt:MU11002:0:0 ",
        )
        for value in invalid_plu:
            with self.subTest(plu=value):
                db = FakeDB()
                event = payload()
                event["body"]["order"]["items"][0]["modifiers"][0]["pos_item_id"] = value
                with self.assertRaises(ValueError):
                    self.bridge(db, event)
                self.assertEqual(db.statements, [])

    def test_canonical_parent_scoped_modifier_plu_preserves_kitchen_option(self):
        db = FakeDB()
        event = payload()
        event["body"]["order"]["items"][0]["modifiers"][0]["pos_item_id"] = "opt:MU11002:0:1"
        self.assertEqual(self.bridge(db, event), "created")
        self.assertEqual(json.loads(db.items[0][6]), [
            {"name": "Guacamole", "plu": "opt:MU11002:0:1"}])
        self.assertEqual(self.bridge(db, copy.deepcopy(event)), "duplicate")
        self.assertEqual(len(db.orders), 1)
        self.assertEqual(len(db.items), 1)

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




class PostgresDeliverooConcurrencyTests(unittest.TestCase):
    """Real PostgreSQL transaction test; only the isolated GitHub CI database.

    No HTTP/webhook, restaurant sandbox, kitchen, printer or production database.
    The test is skipped unless an explicit local CI DSN is supplied.
    """

    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ.get("BECHEFAA_BIS_TEST_PG_DSN")
        if not cls.dsn:
            raise unittest.SkipTest("isolated PostgreSQL CI DSN not configured")
        import psycopg
        from psycopg.rows import dict_row
        cls.psycopg = psycopg
        cls.dict_row = dict_row
        BisDeliverooBridgeRuntimeTests.setUpClass()
        cls.bridge_code = BisDeliverooBridgeRuntimeTests.code
        with cls.connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS caisse_orders (
                id TEXT PRIMARY KEY, num INTEGER NOT NULL UNIQUE,
                customer_name TEXT, source TEXT, sales_channel TEXT,
                payment TEXT, status TEXT, total NUMERIC(12,2),
                created_at BIGINT, updated_at BIGINT
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS caisse_order_items (
                order_id TEXT NOT NULL REFERENCES caisse_orders(id),
                line_id TEXT NOT NULL, product_id TEXT, name TEXT,
                qty INTEGER, unit_price NUMERIC(12,2), options_json JSONB,
                options_text TEXT, prepared BOOLEAN, position INTEGER,
                PRIMARY KEY(order_id,line_id)
            )""")

    @classmethod
    def connect(cls):
        return cls.psycopg.connect(cls.dsn, row_factory=cls.dict_row)

    def setUp(self):
        with self.connect() as conn:
            conn.execute("TRUNCATE caisse_order_items, caisse_orders")

    def import_in_parallel(self, first, second):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        barrier = Barrier(2)
        stub_app = SimpleNamespace(ensure_order_schema=lambda conn: None)

        def import_one(event):
            namespace = {
                "os": os, "json": json,
                "db": lambda: self.connect(),
            }
            exec(self.bridge_code, namespace)
            barrier.wait(timeout=15)
            try:
                return ("ok", namespace["_bridge_order_new"](copy.deepcopy(event)))
            except ValueError as exc:
                return ("conflict", str(exc))

        env = {
            "CC_APP_ID": "app_fad0809f-954d-47e7-983d-afb7c3867cd0",
            "BECHEFAA_DELIVEROO_ORDER_BRIDGE_ENABLED": "1",
        }
        with patch.dict(os.environ, env), patch.dict(
            sys.modules, {"clean_caisse.app": stub_app}
        ):
            with ThreadPoolExecutor(max_workers=2) as pool:
                left = pool.submit(import_one, first)
                right = pool.submit(import_one, second)
                return [left.result(timeout=40), right.result(timeout=40)]

    def test_concurrent_identical_order_id_creates_one_complete_kitchen_order(self):
        event = payload()
        outcomes = self.import_in_parallel(event, event)
        self.assertCountEqual(outcomes, [("ok", "created"), ("ok", "duplicate")])
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM caisse_orders").fetchone()["n"], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM caisse_order_items").fetchone()["n"], 1)
            row = conn.execute("SELECT status, sales_channel, total FROM caisse_orders").fetchone()
            self.assertEqual(row["status"], "À préparer")
            self.assertEqual(row["sales_channel"], "DELIVEROO")
            self.assertEqual(str(row["total"]), "17.90")

    def test_concurrent_conflicting_replay_never_overwrites_first_order(self):
        event = payload()
        changed = copy.deepcopy(event)
        changed["body"]["order"]["items"][0]["total_price"]["fractional"] = 1990
        outcomes = self.import_in_parallel(event, changed)
        self.assertEqual(sum(outcome == ("ok", "created") for outcome in outcomes), 1)
        self.assertEqual(sum(kind == "conflict" and "replay content conflict" in value
                             for kind, value in outcomes), 1)
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM caisse_orders").fetchone()["n"], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM caisse_order_items").fetchone()["n"], 1)
            total = conn.execute("SELECT total FROM caisse_orders").fetchone()["total"]
            self.assertIn(str(total), ("17.90", "19.90"))

    def test_postgres_second_item_constraint_failure_rolls_back_and_retry_is_safe(self):
        """A real PostgreSQL error must not leave a partial kitchen order."""
        event = payload()
        second = copy.deepcopy(event["body"]["order"]["items"][0])
        second.update({
            "pos_item_id": "MU_BLOCKED",
            "name": "Second item",
            "quantity": 1,
            "total_price": {"fractional": 500, "currency_code": "EUR"},
            "modifiers": [],
        })
        event["body"]["order"]["items"].append(second)
        namespace = {"os": os, "json": json, "db": lambda: self.connect()}
        exec(self.bridge_code, namespace)
        bridge = namespace["_bridge_order_new"]
        stub_app = SimpleNamespace(ensure_order_schema=lambda conn: None)
        env = {
            "CC_APP_ID": "app_fad0809f-954d-47e7-983d-afb7c3867cd0",
            "BECHEFAA_DELIVEROO_ORDER_BRIDGE_ENABLED": "1",
        }
        # Only the disposable CI database gets this temporary constraint.
        with self.connect() as conn:
            conn.execute("""ALTER TABLE caisse_order_items
                ADD CONSTRAINT bis_reject_second_item
                CHECK (product_id <> 'MU_BLOCKED')""")
        try:
            with patch.dict(os.environ, env), patch.dict(
                sys.modules, {"clean_caisse.app": stub_app}
            ):
                with self.assertRaises(self.psycopg.errors.CheckViolation):
                    bridge(copy.deepcopy(event))
                with self.connect() as conn:
                    self.assertEqual(
                        conn.execute("SELECT COUNT(*) AS n FROM caisse_orders").fetchone()["n"], 0
                    )
                    self.assertEqual(
                        conn.execute("SELECT COUNT(*) AS n FROM caisse_order_items").fetchone()["n"], 0
                    )
        finally:
            with self.connect() as conn:
                conn.execute(
                    "ALTER TABLE caisse_order_items DROP CONSTRAINT bis_reject_second_item"
                )
        with patch.dict(os.environ, env), patch.dict(
            sys.modules, {"clean_caisse.app": stub_app}
        ):
            self.assertEqual(bridge(copy.deepcopy(event)), "created")
            self.assertEqual(bridge(copy.deepcopy(event)), "duplicate")
        with self.connect() as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS n FROM caisse_orders").fetchone()["n"], 1
            )
            rows = conn.execute(
                "SELECT product_id, qty FROM caisse_order_items ORDER BY position"
            ).fetchall()
            self.assertEqual(
                [(row["product_id"], row["qty"]) for row in rows],
                [("MU11002", 2), ("MU_BLOCKED", 1)],
            )
            self.assertEqual(
                conn.execute("SELECT status FROM caisse_orders").fetchone()["status"],
                "À préparer",
            )

    def test_concurrent_distinct_order_ids_receive_unique_pos_numbers(self):
        first = payload()
        second = copy.deepcopy(first)
        second["body"]["order"]["id"] = "fr:test-order-2"
        outcomes = self.import_in_parallel(first, second)
        self.assertCountEqual(outcomes, [("ok", "created"), ("ok", "created")])
        with self.connect() as conn:
            rows = conn.execute("SELECT num FROM caisse_orders ORDER BY num").fetchall()
            self.assertEqual([row["num"] for row in rows], [1, 2])
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM caisse_order_items").fetchone()["n"], 2)


if __name__ == "__main__":
    unittest.main()
