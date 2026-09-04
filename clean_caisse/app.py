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
    with db() as conn:
        row = conn.execute(
            "SELECT data_json::text AS data_json, updated_at FROM catalog_admin_v2 WHERE id=1"
        ).fetchone()

    if not row:
        return jsonify({"data": None, "updatedAt": 0, "source": "catalog_admin_v2"})

    try:
        data = json.loads(row["data_json"] or "{}")
    except Exception:
        data = None

    return jsonify({
        "data": data,
        "updatedAt": row["updated_at"],
        "source": "catalog_admin_v2",
    })


@app.get("/")
def root():
    return "BÉCHÉFAA-Caisse clean backend", 200, {"Content-Type": "text/plain; charset=utf-8"}
