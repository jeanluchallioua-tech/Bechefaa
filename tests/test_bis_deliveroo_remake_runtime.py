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
    def __init__(self, events=(), imported=(), displays=(), fail_events=False, fail_lookup=False, fail_displays=False):
        self.events = list(events)
        self.imported = set(imported)
        self.displays = list(displays)
        self.fail_events = fail_events
        self.fail_lookup = fail_lookup
        self.fail_displays = fail_displays

    def execute(self, sql, params=()):
        if "remake_details,parent_order_id" in sql:
            if self.fail_events:
                raise RuntimeError("sandbox events unavailable")
            return Rows(self.events)
        if "id = ANY(%s)" in sql:
            if self.fail_lookup:
                raise RuntimeError("POS replacement lookup unavailable")
            return Rows([{"id": oid} for oid in params[0] if oid in self.imported])
        if "display_id" in sql:
            if self.fail_displays:
                raise RuntimeError("display references unavailable")
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

    def test_blank_display_id_keeps_external_reference(self):
        conn = FakeConn(events=[{"order_id": "child", "parent_id": "parent"}],
                        imported=[pos_id("child")],
                        displays=[{"order_id": "child", "display_id": ""}])
        result = self.render(conn, self.orders())
        child = next(o for o in result if o["id"] == pos_id("child"))
        self.assertEqual(child["platform_reference"], "child")

    def test_missing_display_id_keeps_external_reference(self):
        conn = FakeConn(events=[{"order_id": "child", "parent_id": "parent"}],
                        imported=[pos_id("child")],
                        displays=[{"order_id": "child", "display_id": None}])
        result = self.render(conn, self.orders())
        child = next(o for o in result if o["id"] == pos_id("child"))
        self.assertEqual(child["platform_reference"], "child")

    def test_multiple_independent_remakes_only_hide_their_own_parents(self):
        now = int(time.time() * 1000) - 20000
        orders = [
            {"id": pos_id(external), "source": "DELIVEROO", "created_at": now}
            for external in ("parent", "child", "parent2", "child2", "unrelated")
        ]
        conn = FakeConn(
            events=[
                {"order_id": "child", "parent_id": "parent"},
                {"order_id": "child2", "parent_id": "parent2"},
            ],
            imported=[pos_id("child")],
        )
        result = self.render(conn, orders)
        self.assertEqual(
            {o["id"] for o in result},
            {pos_id("child"), pos_id("parent2"), pos_id("child2"), pos_id("unrelated")},
        )
        self.assertTrue(next(o for o in result if o["id"] == pos_id("child"))["is_deliveroo_remake"])
        self.assertFalse(next(o for o in result if o["id"] == pos_id("child2")).get("is_deliveroo_remake", False))

    def test_replacement_is_held_without_reexposing_parent(self):
        now = int(time.time() * 1000)
        orders = [
            {"id": pos_id("parent"), "source": "DELIVEROO",
             "created_at": now - 30000},
            {"id": pos_id("child"), "source": "DELIVEROO",
             "created_at": now - 2000},
            {"id": "local", "source": "EMPORTER", "created_at": now - 2000},
        ]
        conn = FakeConn(events=[{"order_id": "child", "parent_id": "parent"}],
                        imported=[pos_id("child")])
        result = self.render(conn, orders)
        self.assertEqual([o["id"] for o in result], ["local"])

    def test_replacement_appears_after_hold_without_parent(self):
        now = int(time.time() * 1000)
        orders = [
            {"id": pos_id("parent"), "source": "DELIVEROO",
             "created_at": now - 30000},
            {"id": pos_id("child"), "source": "DELIVEROO",
             "created_at": now - 16000},
        ]
        conn = FakeConn(events=[{"order_id": "child", "parent_id": "parent"}],
                        imported=[pos_id("child")])
        result = self.render(conn, orders)
        self.assertEqual([o["id"] for o in result], [pos_id("child")])
        self.assertTrue(result[0]["is_deliveroo_remake"])

    def test_duplicate_remake_events_do_not_duplicate_orders(self):
        event = {"order_id": "child", "parent_id": "parent"}
        conn = FakeConn(events=[event, dict(event), dict(event)],
                        imported=[pos_id("child")],
                        displays=[{"order_id": "child", "display_id": "D-123"}] * 3)
        result = self.render(conn, self.orders())
        self.assertEqual([o["id"] for o in result], [pos_id("child"), "local"])
        self.assertEqual(result[0]["platform_reference"], "D-123")

    def test_multiple_remake_generations_hide_imported_ancestors(self):
        now = int(time.time() * 1000) - 20000
        orders = [
            {"id": pos_id(external), "source": "DELIVEROO", "created_at": now}
            for external in ("parent", "child", "grandchild")
        ]
        conn = FakeConn(
            events=[
                {"order_id": "child", "parent_id": "parent"},
                {"order_id": "grandchild", "parent_id": "child"},
            ],
            imported=[pos_id("child"), pos_id("grandchild")],
        )
        result = self.render(conn, orders)
        self.assertEqual([o["id"] for o in result], [pos_id("grandchild")])
        self.assertTrue(result[0]["is_deliveroo_remake"])

    def test_invalid_remake_links_cannot_hide_orders(self):
        conn = FakeConn(
            events=[
                {"order_id": "parent", "parent_id": "parent"},
                {"order_id": "", "parent_id": "parent"},
                {"order_id": "child", "parent_id": ""},
            ],
            imported=[pos_id("parent"), pos_id("child")],
        )
        result = self.render(conn, self.orders())
        self.assertEqual({o["id"] for o in result},
                         {pos_id("parent"), pos_id("child"), "local"})

    def test_new_deliveroo_orders_held_but_local_orders_visible(self):
        result = self.render(FakeConn(), self.orders(age_ms=1000))
        self.assertEqual([o["id"] for o in result], ["local"])

    def test_presentation_does_not_mutate_source_orders(self):
        orders = self.orders()
        original = copy.deepcopy(orders)
        conn = FakeConn(events=[{"order_id": "child", "parent_id": "parent"}],
                        imported=[pos_id("child")])
        env = {"CC_APP_ID": "app_fad0809f-954d-47e7-983d-afb7c3867cd0",
               "BECHEFAA_DELIVEROO_ORDER_BRIDGE_ENABLED": "1"}
        with patch.dict(os.environ, env):
            visible = self.namespace["_deliveroo_remake_view"](conn, orders)
        self.assertEqual(orders, original)
        self.assertTrue(next(o for o in visible if o["id"] == pos_id("child"))["is_deliveroo_remake"])

    def test_repeated_render_is_idempotent(self):
        conn = FakeConn(events=[{"order_id": "child", "parent_id": "parent"}],
                        imported=[pos_id("child")],
                        displays=[{"order_id": "child", "display_id": "D-123"}])
        first = self.render(conn, self.orders())
        second = self.render(conn, first)
        self.assertEqual(second, first)

    def test_regular_deliveroo_order_keeps_own_customer_and_reference(self):
        conn = FakeConn(displays=[{"order_id": "parent", "display_id": "D-100"}])
        orders = self.orders()
        orders[0]["customer_name"] = "Client initial"
        result = self.render(conn, orders)
        original = next(o for o in result if o["id"] == pos_id("parent"))
        self.assertEqual(original["customer_name"], "Client initial")
        self.assertEqual(original["platform_reference"], "D-100")
        self.assertFalse(original.get("is_deliveroo_remake", False))

    def test_non_deliveroo_order_keeps_payment_and_service(self):
        orders = self.orders()
        orders[2].update({"payment": "ESPÈCES", "service_mode": "Emporter",
                          "customer_name": "Client caisse"})
        result = self.render(FakeConn(), orders)
        local = next(o for o in result if o["id"] == "local")
        self.assertEqual(local, orders[2])

    def test_deliveroo_payment_labels_are_consistent(self):
        orders = self.orders()
        orders[0].update({"payment": "CB", "payment_label": "CB",
                          "ticket_type": "Sur place", "service_mode": "Sur place"})
        result = self.render(FakeConn(), orders)
        item = next(o for o in result if o["id"] == pos_id("parent"))
        self.assertEqual(item["payment"], "PAYÉ EN LIGNE")
        self.assertEqual(item["payment_label"], "PAYÉ EN LIGNE")
        self.assertEqual(item["ticket_type"], "Livraison")
        self.assertEqual(item["service_mode"], "Livraison")
        self.assertEqual(orders[0]["payment"], "CB")

    def test_missing_display_rows_keep_remake_reference(self):
        conn = FakeConn(events=[{"order_id": "child", "parent_id": "parent"}],
                        imported=[pos_id("child")], displays=[])
        result = self.render(conn, self.orders())
        child = next(o for o in result if o["id"] == pos_id("child"))
        self.assertEqual(child["platform_reference"], "child")

    def test_invalid_creation_timestamps_do_not_break_display(self):
        for invalid in ("not-a-date", [], {}, float("inf")):
            with self.subTest(invalid=invalid):
                orders = self.orders(age_ms=20000)
                orders[0]["created_at"] = invalid
                result = self.render(FakeConn(), orders)
                self.assertEqual(len(result), 3)

    def test_failed_replacement_lookup_keeps_parent_visible(self):
        conn = FakeConn(events=[{"order_id": "child", "parent_id": "parent"}],
                        imported=[pos_id("child")], fail_lookup=True)
        result = self.render(conn, self.orders())
        self.assertEqual({o["id"] for o in result},
                         {pos_id("parent"), pos_id("child"), "local"})
        self.assertFalse(any(o.get("is_deliveroo_remake") for o in result))

    def test_failed_display_lookup_keeps_external_reference(self):
        conn = FakeConn(events=[{"order_id": "child", "parent_id": "parent"}],
                        imported=[pos_id("child")], fail_displays=True)
        result = self.render(conn, self.orders())
        child = next(o for o in result if o["id"] == pos_id("child"))
        self.assertEqual(child["platform_reference"], "child")
        self.assertTrue(child["is_deliveroo_remake"])

    def test_unavailable_event_store_preserves_orders(self):
        orders = self.orders()
        result = self.render(FakeConn(fail_events=True), orders)
        self.assertEqual(result, orders)


if __name__ == "__main__":
    unittest.main()
