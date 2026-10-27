"""Isolated regression for immutable Deliveroo sequence-GUID audit events.

Executes the actual nested persistence function with a deterministic SQL double.
No network, PostgreSQL, webhook endpoint, kitchen or printer is contacted.
"""
import ast
import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1] / "clean_caisse" / "deliveroo_sandbox_phase6.py"


class Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=()):
        if "CREATE TABLE IF NOT EXISTS deliveroo_sandbox_events" in sql:
            self.row = None
        elif "INSERT INTO deliveroo_sandbox_events" in sql:
            assert "ON CONFLICT (sequence_guid) DO NOTHING" in sql
            assert "RETURNING sequence_guid" in sql
            guid, event, order_id, accepted, body = params
            if guid in self.conn.events:
                self.row = None
            else:
                self.conn.events[guid] = {
                    "event": event, "order_id": order_id,
                    "accepted": accepted, "payload": json.loads(body),
                }
                self.row = {"sequence_guid": guid}
        elif "SELECT payload = %s::jsonb AS same_payload" in sql:
            body, guid = params
            stored = self.conn.events.get(guid)
            self.row = ({"same_payload": stored["payload"] == json.loads(body)}
                        if stored else None)
        else:
            raise AssertionError("Unexpected SQL: " + sql)

    def fetchone(self):
        return self.row


class Connection:
    def __init__(self):
        self.events = {}
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return Cursor(self)

    def commit(self):
        self.commits += 1


class DeliverooGuidReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        register = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == "register_deliveroo_sandbox_phase6")
        persist = next(n for n in register.body if isinstance(n, ast.FunctionDef)
                       and n.name == "_persist_order_event")
        cls.code = compile(ast.fix_missing_locations(
            ast.Module(body=[persist], type_ignores=[])), str(SOURCE), "exec")

    def persist(self, conn, guid, payload):
        namespace = {
            "db": lambda: conn, "json": json,
            "request": SimpleNamespace(headers={"X-Deliveroo-Sequence-Guid": guid}),
            "_extract_order_id": lambda p: p["body"]["order"]["id"],
            "_accepted_in_status_log": lambda p: False,
        }
        exec(self.code, namespace)
        namespace["_persist_order_event"](payload)

    def sample(self):
        return {"event": "order.new", "body": {"order": {
            "id": "fr:one", "items": [{"pos_item_id": "MU11002", "quantity": 1}]
        }}}

    def test_same_guid_and_same_payload_are_idempotent(self):
        conn = Connection()
        event = self.sample()
        self.persist(conn, "guid-a", event)
        self.persist(conn, "guid-a", copy.deepcopy(event))
        self.assertEqual(len(conn.events), 1)
        self.assertEqual(conn.commits, 2)
        self.assertEqual(conn.events["guid-a"]["payload"], event)

    def test_same_guid_with_different_order_rejected_and_first_preserved(self):
        conn = Connection()
        event = self.sample()
        self.persist(conn, "guid-a", event)
        changed = copy.deepcopy(event)
        changed["body"]["order"]["id"] = "fr:two"
        with self.assertRaisesRegex(ValueError, "replay payload conflict"):
            self.persist(conn, "guid-a", changed)
        self.assertEqual(conn.commits, 1)
        self.assertEqual(conn.events["guid-a"]["payload"], event)
        self.assertNotIn("guid-b", conn.events)

    def test_different_guids_are_distinct_events(self):
        conn = Connection()
        first = self.sample()
        second = copy.deepcopy(first)
        second["body"]["order"]["id"] = "fr:two"
        self.persist(conn, "guid-a", first)
        self.persist(conn, "guid-b", second)
        self.assertEqual(len(conn.events), 2)
        self.assertEqual(conn.commits, 2)

    def test_two_guids_for_same_order_remain_distinct_audit_events(self):
        # A retried Deliveroo order can arrive with a fresh event GUID.
        # The event ledger must retain both; the POS bridge separately
        # enforces uniqueness by external order ID.
        conn = Connection()
        event = self.sample()
        self.persist(conn, "guid-a", event)
        self.persist(conn, "guid-b", copy.deepcopy(event))
        self.assertEqual(set(conn.events), {"guid-a", "guid-b"})
        self.assertEqual(
            {record["order_id"] for record in conn.events.values()}, {"fr:one"})
        self.assertEqual(conn.commits, 2)

    def test_json_object_key_order_does_not_change_replay_identity(self):
        conn = Connection()
        first = self.sample()
        second = {"body": first["body"], "event": "order.new"}
        self.persist(conn, "guid-a", first)
        self.persist(conn, "guid-a", second)
        self.assertEqual(len(conn.events), 1)


class DeliverooAcceptedStatusGuardTests(unittest.TestCase):
    """Read-only test of the actual status-log detector; no sync HTTP calls."""

    @classmethod
    def setUpClass(cls):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        register = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == "register_deliveroo_sandbox_phase6")
        detector = next(n for n in register.body if isinstance(n, ast.FunctionDef)
                        and n.name == "_accepted_in_status_log")
        namespace = {}
        exec(compile(ast.fix_missing_locations(
            ast.Module(body=[detector], type_ignores=[])), str(SOURCE), "exec"), namespace)
        cls.detect = staticmethod(namespace["_accepted_in_status_log"])

    def test_explicit_nested_status_is_accepted(self):
        payload = {"event": "order.status_update", "body": {
            "order": {"status_log": [{"status": " Accepted "}]}}}
        self.assertTrue(self.detect(payload))

    def test_unrelated_accepted_text_does_not_trigger_sync(self):
        for field in ("order_notes", "customer_note", "description", "status_log"):
            with self.subTest(field=field):
                payload = {"event": "order.status_update", "body": {
                    "order": {field: "accepted"}}}
                self.assertFalse(self.detect(payload))

    def test_order_new_never_triggers_status_sync(self):
        self.assertFalse(self.detect({"event": "order.new", "body": {
            "order": {"status": "accepted"}}}))

    def test_untrusted_deep_payload_fails_closed(self):
        node = {"status": "accepted"}
        for _ in range(20):
            node = {"nested": node}
        self.assertFalse(self.detect({"event": "order.status_update", "body": node}))

    def test_other_status_does_not_trigger_sync(self):
        self.assertFalse(self.detect({"event": "order.status_update", "body": {
            "order": {"status_log": [{"status": "pending"}],
                      "order_notes": "accepted"}}}))


if __name__ == "__main__":
    unittest.main()
