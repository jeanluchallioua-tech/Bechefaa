"""Pont public isolé vers le catalogue V2 existant.

Expose GET /api/public/catalog sans modifier le catalogue ni sa persistance.
Les photos encodées en data: sont sorties du JSON principal et servies via une
route dédiée afin d'alléger fortement le chargement du catalogue côté site.
"""

import base64
from urllib.parse import quote

from flask import Response, jsonify, request
from .google_reviews_phase6 import read_google_reviews


def _public_catalog_response(payload, status=200):
    response = jsonify(payload)
    response.status_code = status
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET"
    response.headers["Cache-Control"] = "no-store"
    return response


def _absolute_photo_url(product_id, version=None):
    forwarded = request.headers.get("X-Forwarded-Proto", "")
    scheme = (forwarded.split(",")[0].strip() if forwarded else request.scheme) or "https"
    url = f"{scheme}://{request.host}/api/public/catalog/photo/{quote(str(product_id), safe='')}"
    if version not in (None, ""):
        url += f"?v={quote(str(version), safe='')}"
    return url


def _split_data_uri(value):
    if not isinstance(value, str) or not value.startswith("data:"):
        return None
    try:
        header, encoded = value.split(",", 1)
        if ";base64" not in header:
            return None
        mime = header[5:].split(";", 1)[0] or "application/octet-stream"
        return mime, encoded
    except ValueError:
        return None


def register_public_catalog_bridge_isolated_phase6(app, load_catalog):
    @app.get("/api/public/catalog")
    def public_catalog_phase6():
        data, updated_at = load_catalog()
        if not isinstance(data, dict):
            return _public_catalog_response({
                "categories": [],
                "products": [],
                "google_reviews": read_google_reviews(),
                "error": "Catalogue V2 indisponible",
                "updatedAt": updated_at,
                "source": "catalog_admin_v2",
            }, 404)

        payload = dict(data)
        payload.setdefault("categories", [])
        payload.setdefault("products", [])

        # Copie légère des produits : on ne renvoie plus les gros blobs Base64
        # dans le JSON. Le front continue d'utiliser p.photo sans autre changement.
        # L'updated_at du catalogue versionne désormais l'URL de la photo : quand
        # une image est remplacée, le navigateur reçoit une nouvelle URL et ne peut
        # plus conserver l'ancienne image dans son cache pendant 24 heures.
        light_products = []
        for product in payload.get("products") or []:
            if not isinstance(product, dict):
                light_products.append(product)
                continue
            item = dict(product)
            photo = item.get("photo")
            if _split_data_uri(photo):
                product_id = item.get("id")
                item["photo"] = _absolute_photo_url(product_id, updated_at) if product_id is not None else ""
            light_products.append(item)

        payload["products"] = light_products
        payload["google_reviews"] = read_google_reviews()
        payload["updatedAt"] = updated_at
        payload["source"] = "catalog_admin_v2"
        return _public_catalog_response(payload, 200)

    @app.get("/api/public/catalog/photo/<path:product_id>")
    def public_catalog_photo_phase6(product_id):
        data, _updated_at = load_catalog()
        if not isinstance(data, dict):
            return Response(status=404)

        product = next(
            (
                p for p in (data.get("products") or [])
                if isinstance(p, dict) and str(p.get("id")) == str(product_id)
            ),
            None,
        )
        if not product:
            return Response(status=404)

        parsed = _split_data_uri(product.get("photo"))
        if not parsed:
            return Response(status=404)

        mime, encoded = parsed
        try:
            raw = base64.b64decode(encoded, validate=False)
        except Exception:
            return Response(status=404)

        response = Response(raw, status=200, mimetype=mime)
        response.headers["Cache-Control"] = "public, max-age=86400"
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response
