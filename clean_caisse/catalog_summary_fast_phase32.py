"""Phase 3.2 — chargement rapide du catalogue POS.

Intercepte uniquement GET /api/catalog/summary afin d'éviter d'envoyer les photos
base64 lourdes dans le JSON initial. Les photos restent disponibles via un endpoint
léger dédié et sont chargées séparément par le navigateur.
"""
import base64

from flask import Response, jsonify, request


_PHOTO_CACHE = {}


def _photo_response(value):
    if not isinstance(value, str) or not value.startswith("data:") or ";base64," not in value:
        return None
    try:
        header, encoded = value.split(",", 1)
        mime = header[5:].split(";", 1)[0] or "image/jpeg"
        payload = base64.b64decode(encoded, validate=False)
    except Exception:
        return None
    return Response(payload, content_type=mime, headers={"Cache-Control": "public, max-age=3600"})


def register_catalog_summary_fast_phase32(app, load_catalog):
    @app.before_request
    def phase32_fast_catalog_summary():
        if request.method != "GET" or request.path != "/api/catalog/summary":
            return None

        data, updated_at = load_catalog()
        if not isinstance(data, dict):
            return jsonify({
                "ok": False,
                "source": "catalog_admin_v2",
                "categories": 0,
                "products": 0,
                "items": [],
                "updatedAt": updated_at,
            }), 404

        raw_categories = data.get("categories") or []
        raw_products = data.get("products") or []

        categories = []
        for category in raw_categories:
            if isinstance(category, str):
                name, active = category.strip(), True
            elif isinstance(category, dict):
                name = str(category.get("name") or category.get("label") or "").strip()
                active = category.get("active", True) is not False
            else:
                continue
            if name and active:
                categories.append(name)

        items = []
        for product in raw_products:
            if not isinstance(product, dict) or product.get("active", True) is False:
                continue
            name = str(product.get("name") or "").strip()
            if not name:
                continue

            product_id = str(product.get("id") or "")
            direct_options = product.get("options") if isinstance(product.get("options"), list) else []
            selection_groups = product.get("optionSelections") if isinstance(product.get("optionSelections"), dict) else {}
            active_selection_groups = [
                key for key, values in selection_groups.items()
                if isinstance(values, list) and values
            ]

            photo = product.get("photo") or ""
            photo_out = photo
            if product_id and isinstance(photo, str) and photo.startswith("data:") and ";base64," in photo:
                _PHOTO_CACHE[product_id] = photo
                photo_out = f"/api/catalog/photo-phase32/{product_id}"

            items.append({
                "id": product.get("id"),
                "name": name,
                "category": product.get("category") or product.get("cat") or "",
                "price": product.get("price", 0),
                "optionGroups": len(direct_options) if direct_options else len(active_selection_groups),
                "hasDirectOptions": bool(direct_options),
                "photo": photo_out,
            })

        return jsonify({
            "ok": True,
            "source": "catalog_admin_v2",
            "categories": len(categories),
            "categoryNames": categories,
            "products": len(items),
            "items": items,
            "updatedAt": updated_at,
            "phase32FastSummary": True,
        })

    @app.get("/api/catalog/photo-phase32/<product_id>")
    def phase32_catalog_photo(product_id):
        photo = _PHOTO_CACHE.get(str(product_id))
        if photo:
            response = _photo_response(photo)
            if response is not None:
                return response

        data, _ = load_catalog()
        if isinstance(data, dict):
            for product in data.get("products") or []:
                if isinstance(product, dict) and str(product.get("id") or "") == str(product_id):
                    photo = product.get("photo") or ""
                    if photo:
                        _PHOTO_CACHE[str(product_id)] = photo
                        response = _photo_response(photo)
                        if response is not None:
                            return response
                    break
        return "Photo introuvable", 404
