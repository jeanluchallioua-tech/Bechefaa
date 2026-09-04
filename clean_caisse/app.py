import json
import os

from flask import Flask, jsonify
import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("POSTGRESQL_ADDON_URI") or os.getenv("DATABASE_URL")

app = Flask(__name__)


def db():
    if not DATABASE_URL:
        raise RuntimeError("POSTGRESQL_ADDON_URI/DATABASE_URL manquant")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def load_catalog():
    with db() as conn:
        row = conn.execute(
            "SELECT data_json::text AS data_json, updated_at FROM catalog_admin_v2 WHERE id=1"
        ).fetchone()

    if not row:
        return None, 0

    try:
        data = json.loads(row["data_json"] or "{}")
    except Exception:
        data = None
    return data, row["updated_at"]


@app.get("/api/health")
def health():
    database = "unconfigured"
    try:
        with db() as conn:
            conn.execute("SELECT 1").fetchone()
        database = "postgresql"
    except Exception:
        database = "error"
    return jsonify({
        "ok": database == "postgresql",
        "service": "BECHEFAA-Caisse",
        "database": database,
        "catalogue": "catalog_admin_v2",
        "orders": "caisse_orders",
        "clients": "caisse_clients",
    }), (200 if database == "postgresql" else 503)


@app.get("/api/catalog")
def catalog():
    data, updated_at = load_catalog()
    return jsonify({
        "data": data,
        "updatedAt": updated_at,
        "source": "catalog_admin_v2",
    })


@app.get("/api/catalog/summary")
def catalog_summary():
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
    for c in raw_categories:
        if isinstance(c, str):
            name = c.strip()
            active = True
        elif isinstance(c, dict):
            name = str(c.get("name") or c.get("label") or "").strip()
            active = c.get("active", True) is not False
        else:
            continue
        if name and active:
            categories.append(name)

    items = []
    for p in raw_products:
        if not isinstance(p, dict) or p.get("active", True) is False:
            continue
        name = str(p.get("name") or "").strip()
        if not name:
            continue
        direct_options = p.get("options") if isinstance(p.get("options"), list) else []
        selection_groups = p.get("optionSelections") if isinstance(p.get("optionSelections"), dict) else {}
        active_selection_groups = [
            key for key, value in selection_groups.items()
            if isinstance(value, list) and len(value) > 0
        ]
        items.append({
            "id": p.get("id"),
            "name": name,
            "category": p.get("category") or p.get("cat") or "",
            "price": p.get("price", 0),
            "optionGroups": len(direct_options) if direct_options else len(active_selection_groups),
            "hasDirectOptions": bool(direct_options),
        })

    return jsonify({
        "ok": True,
        "source": "catalog_admin_v2",
        "categories": len(categories),
        "categoryNames": categories,
        "products": len(items),
        "items": items,
        "updatedAt": updated_at,
    })


@app.get("/")
def root():
    return "BÉCHÉFAA-Caisse clean backend", 200, {"Content-Type": "text/plain; charset=utf-8"}
