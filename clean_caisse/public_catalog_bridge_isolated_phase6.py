"""Pont public isolé vers le catalogue V2 existant.

Étape d'isolation uniquement : ce module n'est pas enregistré dans wsgi_caisse.py.
Il expose, lorsqu'il sera activé, GET /api/public/catalog et renvoie directement
la structure du catalogue V2 attendue par BÉCHÉFAA-Site (categories/products),
sans modifier le catalogue ni sa persistance.
"""

from flask import jsonify


def register_public_catalog_bridge_isolated_phase6(app, load_catalog):
    @app.get("/api/public/catalog")
    def public_catalog_phase6():
        data, updated_at = load_catalog()
        if not isinstance(data, dict):
            return jsonify({
                "categories": [],
                "products": [],
                "error": "Catalogue V2 indisponible",
                "updatedAt": updated_at,
                "source": "catalog_admin_v2",
            }), 404

        payload = dict(data)
        payload.setdefault("categories", [])
        payload.setdefault("products", [])
        payload["updatedAt"] = updated_at
        payload["source"] = "catalog_admin_v2"
        return jsonify(payload), 200
