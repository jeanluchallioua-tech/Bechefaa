"""Pont public isolé vers le catalogue V2 existant.

Expose GET /api/public/catalog sans modifier le catalogue ni sa persistance.
Les photos encodées en data: sont sorties du JSON principal et servies via une
route dédiée afin d'alléger fortement le chargement du catalogue côté site.
Les avis Google et les zones de livraison administrées sont aussi exposés en
lecture seule pour éviter les valeurs codées en dur côté Site.
"""

import base64
import hashlib
from io import BytesIO
from urllib.parse import quote

from PIL import Image, ImageOps
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


def _delivery_zones_snapshot():
    """Lit uniquement les zones existantes ; aucune création de table au boot."""
    try:
        from clean_caisse.app import db
        with db() as conn:
            zones = conn.execute(
                "SELECT code,minimum_order,active FROM caisse_delivery_zones ORDER BY code"
            ).fetchall()
            cities = conn.execute(
                "SELECT zone_code,postal_code,city,active FROM caisse_delivery_cities "
                "ORDER BY zone_code,postal_code,city"
            ).fetchall()
        return [
            {
                "code": str(zone["code"]),
                "minimum_order": float(zone["minimum_order"]),
                "active": bool(zone["active"]),
                "cities": [
                    {
                        "postal_code": str(city["postal_code"]),
                        "city": str(city["city"]),
                        "active": bool(city["active"]),
                    }
                    for city in cities
                    if str(city["zone_code"]) == str(zone["code"])
                ],
            }
            for zone in zones
        ]
    except Exception:
        return []


def register_public_catalog_bridge_isolated_phase6(app, load_catalog):
    @app.get("/api/public/catalog")
    def public_catalog_phase6():
        data, updated_at = load_catalog()
        if not isinstance(data, dict):
            return _public_catalog_response({
                "categories": [],
                "products": [],
                "google_reviews": read_google_reviews(),
                "deliveryZones": _delivery_zones_snapshot(),
                "error": "Catalogue V2 indisponible",
                "updatedAt": updated_at,
                "source": "catalog_admin_v2",
            }, 404)

        payload = dict(data)
        payload.setdefault("categories", [])
        payload.setdefault("products", [])

        light_products = []
        for product in payload.get("products") or []:
            if isinstance(product, dict) and product.get("site_visible", True) is False:
                continue
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
        payload["deliveryZones"] = _delivery_zones_snapshot()
        payload["updatedAt"] = updated_at
        payload["source"] = "catalog_admin_v2"
        return _public_catalog_response(payload, 200)

    def _marketplace_photo(product_id, channel):
        data, updated_at = load_catalog()
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
        _mime, encoded = parsed
        try:
            raw = base64.b64decode(encoded, validate=False)
            source = Image.open(BytesIO(raw))
            source.load()
            source = source.convert("RGB")
        except Exception:
            return Response(status=404)

        channel = str(channel or "").strip().lower()
        if channel == "deliveroo":
            # Menu API: normalisation stricte 16:9 / 1920x1080, sans découper le plat.
            target = (1920, 1080)
        elif channel in {"uber", "uber-eats", "ubereats"}:
            # Uber Eats accepte notamment le 4:3; nos sources BÉCHÉFAA sont 1200x900.
            target = (1200, 900)
        else:
            return Response(status=404)

        fitted = ImageOps.contain(source, target, method=Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", target, (245, 245, 245))
        x = (target[0] - fitted.width) // 2
        y = (target[1] - fitted.height) // 2
        canvas.paste(fitted, (x, y))

        out = BytesIO()
        canvas.save(out, format="JPEG", quality=92, optimize=True)
        body = out.getvalue()
        etag = hashlib.sha256(
            (channel + ":" + str(product_id) + ":").encode("utf-8") + raw
        ).hexdigest()

        response = Response(body, status=200, mimetype="image/jpeg")
        response.headers["Cache-Control"] = "public, max-age=3600, must-revalidate"
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.set_etag(etag)
        if updated_at:
            try:
                response.last_modified = updated_at
            except Exception:
                pass
        return response

    @app.get("/api/public/catalog/photo-marketplace/<channel>/<path:product_id>")
    def public_catalog_photo_marketplace_phase6(channel, product_id):
        return _marketplace_photo(product_id, channel)

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
