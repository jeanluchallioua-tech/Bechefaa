"""Runtime regression: classic send-kitchen must print at most once per order.

Only the isolated AST function is executed with an in-memory DB double;
no database, Epson printer, sandbox or production side effects.
"""
import ast
import contextlib
import time
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "clean_caisse" / "app.py"


class FakeDB:
    def __init__(self, status="Enregistrée"):
        self.row = {"id": "order-1", "num": 12, "total": 17.5,
                    "source": "EMPORTER", "status": status}
        self.updates = 0
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def transaction(self):
        return contextlib.nullcontext()

    def execute(self, sql, params=()):
        self.queries.append(sql)
        if "SELECT id, num, status, total, source" in sql:
            if "FOR UPDATE" not in sql:
                raise AssertionError("Missing row lock")
            return self
        if "UPDATE caisse_orders SET status" in sql:
            self.updates += 1
            self.row["status"] = params[0]
            return self
        raise AssertionError("Unexpected SQL: " + sql)

    def fetchone(self):
        return self.row


class BisClassicKitchenIdempotencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ast.parse(APP.read_text(encoding="utf-8"))
        node = next(n for n in source.body
                    if isinstance(n, ast.FunctionDef)
                    and n.name == "send_order_to_kitchen_classic")
        node.decorator_list = []
        cls.code = compile(ast.fix_missing_locations(
            ast.Module(body=[node], type_ignores=[])), str(APP), "exec")

    def run_send(self, db):
        namespace = {
            "db": lambda: db,
            "time": time,
            "redirect": lambda url, code: (url, code),
        }
        exec(self.code, namespace)
        return namespace["send_order_to_kitchen_classic"]("order-1")

    def test_first_send_transitions_once_and_prints(self):
        db = FakeDB()
        self.assertEqual(
            self.run_send(db), ("/epson/print-order-pack/order-1", 303))
        self.assertEqual(db.updates, 1)
        self.assertEqual(db.row["status"], "À préparer")

    def test_replayed_post_never_reprints(self):
        db = FakeDB()
        first = self.run_send(db)
        second = self.run_send(db)
        third = self.run_send(db)
        self.assertEqual(first, ("/epson/print-order-pack/order-1", 303))
        self.assertEqual(second, ("/?kitchen=already-sent", 303))
        self.assertEqual(third, second)
        self.assertEqual(db.updates, 1)
        self.assertEqual(len([q for q in db.queries if "FOR UPDATE" in q]), 3)

    def test_previously_prepared_order_does_not_print(self):
        db = FakeDB(status="À préparer")
        self.assertEqual(self.run_send(db), ("/?kitchen=already-sent", 303))
        self.assertEqual(db.updates, 0)

    def test_in_progress_order_cannot_reprint(self):
        db = FakeDB(status="En préparation")
        self.assertEqual(
            self.run_send(db),
            ("Cette commande ne peut pas être envoyée en cuisine", 409))
        self.assertEqual(db.updates, 0)


if __name__ == "__main__":
    unittest.main()
