"""Validated Catalogue V2 HTTP API."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Blueprint, jsonify, request

from catalog_core import normalize_catalogue, product_unit_price, validate_catalogue
from catalog_store import CatalogStore

catalog_v2 = Blueprint("catalog_v2", __name__, url_prefix="/api/v2/catalog")
store = CatalogStore()

DEFAULT_LEGACY_CATALOG_URL = (
    "https://app-9962269e-7030-47ba-b908-28eb434e3752.cleverapps.io/api/catalog-admin"
)


def _empty_catalogue():
    return normalize_catalogue({"categories": [], "products": [], "optionLists": {}, "optionListDefs": {}})


def _load_catalogue():
    data, updated_at, schema_version = store.load()
    if data is None:
        return _empty_catalogue(), updated_at, schema_version
    return normalize_catalogue(data), updated_at, schema_version


def _fetch_legacy_catalogue():
    url = os.getenv("BECHEFAA_LEGACY_CATALOG_URL", DEFAULT_LEGACY_CATALOG_URL).strip()
    if not url.startswith("https://") or not url.endswith("/api/catalog-admin"):
        raise ValueError("URL du catalogue historique non autorisée")
    req = Request(url, headers={"User-Agent": "Bechefaa-Catalogue-V2-Migration/1.0"})
    try:
        with urlopen(req, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Impossible de lire le catalogue de production: {exc}") from exc
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise RuntimeError("Le catalogue de production est vide ou invalide")
    return data


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
    """Non-destructive copy of the current catalogue into the isolated V2 store."""
    payload = request.get_json(silent=True) or {}
    force = bool(payload.get("force", False))

    current, _, _ = store.load()
    if current is not None and not force:
        return jsonify({"ok": False, "reason": "v2_not_empty", "error": "Le catalogue V2 contient déjà des données."}), 409

    # First try the legacy table on the same backend (useful for local/transition setups).
    data, legacy_updated_at = store.load_legacy()
    source = "same-backend"

    # Production still stores the legacy catalogue in its own SQLite database, so the
    # PostgreSQL test app cannot see that table directly. In that case read the existing
    # read-only catalogue API over HTTPS and copy it into catalog_admin_v2.
    if not isinstance(data, dict):
        try:
            data = _fetch_legacy_catalogue()
            legacy_updated_at = 0
            source = "production-api"
        except (ValueError, RuntimeError) as exc:
            return jsonify({"ok": False, "reason": "legacy_missing", "error": str(exc)}), 502

    normalized = normalize_catalogue(data)
    errors = validate_catalogue(normalized)
    if errors:
        return jsonify({"ok": False, "error": "Le catalogue source contient des erreurs et n'a pas été copié.", "errors": errors}), 422

    updated_at = store.save(normalized, schema_version=normalized.get("schemaVersion", 1))
    return jsonify({
        "ok": True,
        "copied": True,
        "source": source,
        "legacyUpdatedAt": legacy_updated_at,
        "updatedAt": updated_at,
        "backend": store.backend,
        "products": len(normalized.get("products") or []),
        "categories": len(normalized.get("categories") or []),
    })


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
