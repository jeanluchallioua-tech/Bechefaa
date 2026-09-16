"""Stabilisation UI Phase 3.5.

- L'historique ne se reconstruit plus automatiquement toutes les 8 secondes.
- L'écran Cuisine lit explicitement le tableau PostgreSQL complet /api/kitchen/board.

Correctif d'interface uniquement : aucune modification de schéma ni de données métier.
"""
from flask import request


def register_phase35_ui_stability(app):
    @app.after_request
    def phase35_ui_stability(response):
        if response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        changed = False

        if request.path == "/historique-modification":
            old = "load();setInterval(load,8000);"
            if old in html:
                html = html.replace(old, "load();")
                changed = True

        if request.path == "/cuisine-preparation":
            old = "fetch('/api/kitchen/orders')"
            if old in html:
                html = html.replace(old, "fetch('/api/kitchen/board')")
                changed = True

        if changed:
            response.set_data(html)
            response.content_length = len(response.get_data())
        return response
