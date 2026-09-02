"""Validated Catalogue V2 HTTP API."""
from flask import Blueprint, jsonify, request

from catalog_core import normalize_catalogue, product_unit_price, validate_catalogue
from catalog_store import CatalogStore

catalog_v2 = Blueprint("catalog_v2", __name__, url_prefix="/api/v2/catalog")
store = CatalogStore()


def _empty_catalogue():
    return normalize_catalogue({"categories": [], "products": [], "optionLists": {}, "optionListDefs": {}})


def _load_catalogue():
    data, updated_at, schema_version = store.load()
    if data is None:
        return _empty_catalogue(), updated_at, schema_version
    return normalize_catalogue(data), updated_at, schema_version


@catalog_v2.get("/health")
def health():
    return jsonify({"ok": True, "backend": store.backend, "schemaVersion": 1})


@catalog_v2.get("/admin")
def admin_get():
    data, updated_at, schema_version = _load_catalogue()
    return jsonify({"data": data, "updatedAt": updated_at, "schemaVersion": schema_version, "backend": store.backend})


@catalog_v2.put("/admin")
def admin_put():
    payload = request.get_json(silent=True) or {}
    data = payload.get("data")
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "Catalogue invalide"}), 400
    normalized = normalize_catalogue(data)
    errors = validate_catalogue(normalized)
    if errors:
        return jsonify({"ok": False, "error": "Le catalogue contient des erreurs et n'a pas été enregistré.", "errors": errors}), 422
    updated_at = store.save(normalized, schema_version=normalized.get("schemaVersion", 1))
    return jsonify({"ok": True, "updatedAt": updated_at, "schemaVersion": normalized.get("schemaVersion", 1), "backend": store.backend})


@catalog_v2.post("/migrate-legacy")
def migrate_legacy():
    """Explicit, non-destructive copy from legacy catalog_admin to catalog_admin_v2."""
    payload = request.get_json(silent=True) or {}
    result = store.seed_from_legacy(force=bool(payload.get("force", False)))
    if not result.get("copied"):
        return jsonify({"ok": False, **result}), 409 if result.get("reason") == "v2_not_empty" else 404
    data, _, _ = _load_catalogue()
    errors = validate_catalogue(data)
    if errors:
        return jsonify({"ok": False, "copied": True, "error": "Migration copiée mais validation V2 en échec", "errors": errors, **result}), 422
    return jsonify({"ok": True, **result, "products": len(data.get("products") or []), "categories": len(data.get("categories") or [])})


@catalog_v2.get("/runtime")
def runtime_get():
    data, updated_at, schema_version = _load_catalogue()
    active_categories = [c for c in data["categories"] if c.get("active", True)]
    category_names = {c["name"] for c in active_categories}
    products = []
    for product in data["products"]:
        channels = product.get("channels") or {}
        if not product.get("active", True):
            continue
        if channels and not channels.get("caisse", True):
            continue
        if product.get("category") not in category_names:
            continue
        products.append(product)
    return jsonify({"categories": active_categories, "products": products, "updatedAt": updated_at, "schemaVersion": schema_version})


@catalog_v2.post("/price")
def price_preview():
    payload = request.get_json(silent=True) or {}
    product = payload.get("product")
    selections = payload.get("selections") or {}
    channel = payload.get("channel") or "CAISSE"
    if not isinstance(product, dict):
        return jsonify({"ok": False, "error": "Produit invalide"}), 400
    try:
        total = product_unit_price(product, selections, channel=channel)
    except (TypeError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "unitPrice": total, "channel": channel})
