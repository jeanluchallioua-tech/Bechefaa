"""Runtime regression tests for sandbox-only Deliveroo remake presentation."""
import ast
import copy
import logging
import os
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "clean_caisse" / "app.py"


def pos_id(external):
    return "deliveroo-" + uuid.uuid5(uuid.NAMESPACE_URL, external).hex


class FakeConn:
    def __init__(self, events=(), imported=(), displays=(), fail_events=False):
        self.events = list(events)
        self.imported = set(imported)
        self.displays = list(displays)
        self.fail_events = fail_events

    def execute(self, sql, params=()):
        if "remake_details,parent_order_id" in sql:
            if self.fail_events:
                raise RuntimeError("sandbox events unavailable")
            return Rows(self.events)
        if "id = ANY(%s)" in sql:
            return Rows([{"id": oid} for oid in params[0] if oid in self.imported])
        if "display_id" in sql:
            return Rows(self.displays)
        raise AssertionError(sql)


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class DeliverooRemakeRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ast.parse(SOURCE.read_text(encoding="utf-8"))
        node = next(n for n in source.body if isinstance(n, ast.FunctionDef)
                    and n.name == "_deliveroo_remake_view")
        cls.namespace = {"app": type("App", (), {"logger": logging.getLogger(__name__)})()}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"),
             cls.namespace)

    def render(self, conn, orders, *, enabled=True, app_id=True):
        env = {"CC_APP_ID": "app_fad0809f-954d-47e7-983d-afb7c3867cd0"
               if app_id else "production-app",
               "BECHEFAA_DELIVEROO_ORDER_BRIDGE_ENABLED": "1" if enabled else "0"}
        with patch.dict(os.environ, env):
            return self.namespace["_deliveroo_remake_view"](conn, copy.deepcopy(orders))

    def orders(self, age_ms=20000):
        created = int(time.time() * 1000) - age_ms
        return [{"id": pos_id("parent"), "source": "DELIVEROO", "created_at": created},
                {"id": pos_id("child"), "source": "DELIVEROO", "created_at": created},
                {"id": "local", "source": "EMPORTER", "created_at": created}]

    def test_production_and_disabled_flag_never_filter(self):
        for kwargs in ({"app_id": False}, {"enabled": False}):
            with self.subTest(kwargs=kwargs):
                result = self.render(FakeConn(fail_events=True), self.orders(), **kwargs)
                self.assertEqual(len(result), 3)

    def test_remake_event_alone_does_not_hide_original(self):
        conn = FakeConn(events=[{"order_id": "child", "parent_id": "parent"}])
        result = self.render(conn, self.orders())
        self.assertEqual({o["id"] for o in result},
                         {pos_id("parent"), pos_id("child"), "local"})

    def test_imported_remake_hides_parent_and_labels_child(self):
        conn = FakeConn(events=[{"order_id": "child", "parent_id": "parent"}],
                        imported=[pos_id("child")],
                        displays=[{"order_id": "child", "display_id": "D-123"}])
        result = self.render(conn, self.orders())
        self.assertEqual({o["id"] for o in result}, {pos_id("child"), "local"})
        child = next(o for o in result if o["id"] == pos_id("child"))
        self.assertTrue(child["is_deliveroo_remake"])
        self.assertEqual(child["platform"], "Deliveroo")
        self.assertEqual(child["payment"], "PAYÉ EN LIGNE")
        self.assertEqual(child["platform_reference"], "D-123")

    def test_new_deliveroo_orders_held_but_local_orders_visible(self):
        result = self.render(FakeConn(), self.orders(age_ms=1000))
        self.assertEqual([o["id"] for o in result], ["local"])

    def test_unavailable_event_store_preserves_orders(self):
        orders = self.orders()
        result = self.render(FakeConn(fail_events=True), orders)
        self.assertEqual(result, orders)


if __name__ == "__main__":
    unittest.main()
