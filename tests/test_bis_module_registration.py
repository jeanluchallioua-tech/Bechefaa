"""Verify that staged production modules are wired into the BIS WSGI entrypoint."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "wsgi_caisse.py"

MODULES = {
    "table_core_phase36": "register_table_core_phase36",
    "religious_calendar_phase6": "register_religious_calendar_phase6",
    "offline_mode_phase6": "register_offline_mode_phase6",
    "history_modifier": "register_history_modifier",
    "pos_quantity_phase38": "register_pos_quantity_phase38",
    "service_mode_ui_phase42": "register_service_mode_ui_phase42",
    "epson_epos_network_phase6": "register_epson_epos_network_phase6",
    "clients_management_isolated_phase6": "register_clients_management_isolated_phase6",
}


class BisModuleRegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ENTRYPOINT.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_module_imports_and_registrations(self):
        imports = {}
        calls = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom):
                imports.setdefault(node.module, set()).update(
                    alias.name for alias in node.names)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                calls.add(node.func.id)
        for module, function in MODULES.items():
            with self.subTest(module=module):
                self.assertIn(function, imports.get("clean_caisse." + module, set()))
                self.assertIn(function, calls)
                self.assertTrue((ROOT / "clean_caisse" / (module + ".py")).is_file())


if __name__ == "__main__":
    unittest.main()
