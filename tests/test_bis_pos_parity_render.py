"""BIS-only HTML rendering guards for cashier controls.

These are integration smoke checks of Flask's response injection, NOT evidence
that a deployed tablet has the same assets or works end to end.
"""
import unittest
from pathlib import Path

from flask import Flask, Response

from clean_caisse.pos_quantity_phase38 import register_pos_quantity_phase38
from clean_caisse.pos_options_modal_final import register_pos_options_modal_final

ROOT = Path(__file__).resolve().parents[1]
REMOVE_LINE = '<button class="remove" data-action="remove-line" data-index="${i}">Retirer</button>'


class BisPosParityRenderTests(unittest.TestCase):
    def make_client(self):
        app = Flask(__name__)

        @app.get("/pos")
        def pos():
            return Response(
                "<!doctype html><html><body><div class='cart'>"
                + REMOVE_LINE + "</div></body></html>",
                mimetype="text/html",
            )

        @app.get("/health")
        def health():
            return Response("<html><body>" + REMOVE_LINE + "</body></html>",
                            mimetype="text/html")

        # Same registration order is not assumed by the test: the wrappers
        # must coexist without removing one another's response modifications.
        register_pos_options_modal_final(app)
        register_pos_quantity_phase38(app)
        return app.test_client()

    def test_real_pos_template_contains_cart_injection_anchor(self):
        source = (ROOT / "clean_caisse/app.py").read_text(encoding="utf-8")
        self.assertIn(REMOVE_LINE, source,
                      "The cart markup changed; the Modifier/quantity injection may no longer work")

    def test_pos_response_contains_visible_edit_button_and_handler(self):
        response = self.make_client().get("/pos")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('class="cart-edit-line" data-action="edit-line"', html)
        self.assertIn('data-index="${i}">Modifier</button>', html)
        self.assertIn('data-qminus="${i}"', html)
        self.assertIn('data-qplus="${i}"', html)
        self.assertIn("const button=e.target.closest('[data-action=\"edit-line\"]')", html)
        self.assertIn("Enregistrer les modifications", html)
        self.assertEqual(html.count('class="cart-edit-line"'), 1)

    def test_non_pos_route_is_not_modified(self):
        response = self.make_client().get("/health")
        html = response.get_data(as_text=True)
        self.assertNotIn('class="cart-edit-line"', html)
        self.assertNotIn('pos-options-modal-final-style', html)


if __name__ == "__main__":
    unittest.main()
