"""Pont public isolé vers le catalogue V2 existant.

Étape d'isolation uniquement : ce module expose GET /api/public/catalog et
renvoie directement la structure du catalogue V2 attendue par BÉCHÉFAA-Site
(categories/products), sans modifier le catalogue ni sa persistance.
"""

from flask import jsonify


def _public_catalog_response(payload, status=200):
    response = jsonify(payload)
    response.status_code = status
    # Catalogue volontairement public : aucune donnée privée ni authentification.
    # Autorise le navigateur du site à le lire directement sans passer par un
    # deuxième relais HTTP côté serveur.
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET"
    response.headers["Cache-Control"] = "no-store"
    return response


def register_public_catalog_bridge_isolated_phase6(app, load_catalog):
    @app.get("/api/public/catalog")
    def public_catalog_phase6():
        data, updated_at = load_catalog()
        if not isinstance(data, dict):
            return _public_catalog_response({
                "categories": [],
                "products": [],
                "error": "Catalogue V2 indisponible",
                "updatedAt": updated_at,
                "source": "catalog_admin_v2",
            }, 404)

        payload = dict(data)
        payload.setdefault("categories", [])
        payload.setdefault("products", [])
        payload["updatedAt"] = updated_at
        payload["source"] = "catalog_admin_v2"
        return _public_catalog_response(payload, 200)
