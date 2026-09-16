"""Stabilisation UI Phase 3.5.

- L'historique ne se reconstruit plus automatiquement toutes les 8 secondes.
- L'écran Cuisine lit explicitement le tableau PostgreSQL complet /api/kitchen/board.
- Diagnostic runtime non destructif pour vérifier que wsgi_caisse sert bien /pos.

Correctif d'interface uniquement : aucune modification de schéma ni de données métier.
"""
from flask import jsonify, request


def register_phase35_ui_stability(app):
    @app.get("/api/pos/runtime-check")
    def pos_runtime_check_phase35():
        return jsonify({
            "ok": True,
            "runtime": "wsgi_caisse",
            "module": "phase35_ui_stability",
            "pos_design_expected": "v2",
        })

    @app.after_request
    def phase35_ui_stability(response):
        if request.path == "/pos":
            response.headers["X-Bechefaa-Pos-Runtime"] = "wsgi_caisse-phase35"

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
