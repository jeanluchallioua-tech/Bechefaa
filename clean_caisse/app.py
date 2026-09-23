import json
import os
import base64
import time
import uuid
from decimal import Decimal, InvalidOperation

from flask import Flask, jsonify, Response, request, send_from_directory
from PIL import Image, ImageFile
import io

ImageFile.LOAD_TRUNCATED_IMAGES = True
import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("POSTGRESQL_ADDON_URI") or os.getenv("DATABASE_URL")

app = Flask(__name__)

CAISSE_ICON_B64 = """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"""

def ensure_pwa_static_assets():
    """Crée de vrais fichiers PWA statiques pour Chrome / Samsung."""
    pwa_dir = os.path.join(app.root_path, "static", "pwa")
    os.makedirs(pwa_dir, exist_ok=True)

    source = Image.open(io.BytesIO(base64.b64decode(CAISSE_ICON_B64))).convert("RGBA")

    icon_192 = source.resize((192, 192), Image.Resampling.LANCZOS)
    icon_192.save(os.path.join(pwa_dir, "icon-192.png"), format="PNG", optimize=True)

    icon_512 = source.resize((512, 512), Image.Resampling.LANCZOS)
    icon_512.save(os.path.join(pwa_dir, "icon-512.png"), format="PNG", optimize=True)

    source.save(
        os.path.join(pwa_dir, "favicon.ico"),
        format="ICO",
        sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)],
    )

    manifest = {
        "id": "/",
        "name": "BÉCHÉFAA Caisse",
        "short_name": "Caisse",
        "description": "Accès direct à la caisse BÉCHÉFAA",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "landscape",
        "background_color": "#0b0b0b",
        "theme_color": "#0b0b0b",
        "icons": [
            {"src": "/static/pwa/icon-192.png?v=9", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "/static/pwa/icon-512.png?v=9", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        ],
    }
    with open(os.path.join(pwa_dir, "manifest.webmanifest"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False)

ensure_pwa_static_assets()


@app.get("/caisse-icon.png")
def caisse_icon_png():
    response = Response(base64.b64decode(CAISSE_ICON_B64), mimetype="image/png")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response

@app.get("/caisse-icon-512.png")
def caisse_icon_512_png():
    source = Image.open(io.BytesIO(base64.b64decode(CAISSE_ICON_B64))).convert("RGBA")
    source = source.resize((512, 512), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    source.save(output, format="PNG", optimize=True)
    response = Response(output.getvalue(), mimetype="image/png")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response

@app.get("/favicon.ico")
def caisse_favicon():
    response = send_from_directory(
        os.path.join(app.root_path, "static", "pwa"),
        "favicon.ico",
        mimetype="image/x-icon",
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response

@app.get("/caisse-manifest.webmanifest")
def caisse_manifest():
    manifest = {
        "id": "/",
        "name": "BÉCHÉFAA Caisse",
        "short_name": "Caisse",
        "description": "Accès direct à la caisse BÉCHÉFAA",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "landscape",
        "background_color": "#0b0b0b",
        "theme_color": "#0b0b0b",
        "icons": [
            {"src": "/caisse-icon.png?v=7", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "/caisse-icon-512.png?v=7", "sizes": "512x512", "type": "image/png", "purpose": "any"}
        ]
    }
    response = Response(json.dumps(manifest, ensure_ascii=False), content_type="application/manifest+json; charset=utf-8")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response

@app.get("/caisse-sw.js")
def caisse_service_worker():
    js = r'''const CACHE="bechefaa-caisse-pwa-v3";
self.addEventListener("install",event=>{self.skipWaiting();});
self.addEventListener("activate",event=>{event.waitUntil(self.clients.claim());});
self.addEventListener("fetch",event=>{
  if(event.request.method!=="GET") return;
  event.respondWith(fetch(event.request).catch(()=>caches.match(event.request)));
});'''
    response = Response(js, content_type="application/javascript; charset=utf-8")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Service-Worker-Allowed"] = "/"
    return response


def db():
    if not DATABASE_URL:
        raise RuntimeError("POSTGRESQL_ADDON_URI/DATABASE_URL manquant")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def ensure_order_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS caisse_clients (
        id TEXT PRIMARY KEY,
        first_name TEXT NOT NULL DEFAULT '',
        last_name TEXT NOT NULL DEFAULT '',
        display_name TEXT NOT NULL DEFAULT '',
        phone TEXT NOT NULL DEFAULT '',
        email TEXT NOT NULL DEFAULT '',
        address TEXT NOT NULL DEFAULT '',
        postal_code TEXT NOT NULL DEFAULT '',
        city TEXT NOT NULL DEFAULT '',
        door_intercom TEXT NOT NULL DEFAULT '',
        notes TEXT NOT NULL DEFAULT '',
        created_at BIGINT NOT NULL,
        updated_at BIGINT NOT NULL
    )""")
    conn.execute("ALTER TABLE caisse_clients ADD COLUMN IF NOT EXISTS door_intercom TEXT NOT NULL DEFAULT ''")
    conn.execute("""CREATE TABLE IF NOT EXISTS caisse_orders (
        id TEXT PRIMARY KEY,
        num BIGINT NOT NULL UNIQUE,
        customer_id TEXT NULL REFERENCES caisse_clients(id),
        customer_name TEXT NOT NULL DEFAULT 'Client comptoir',
        phone TEXT NOT NULL DEFAULT '',
        email TEXT NOT NULL DEFAULT '',
        address TEXT NOT NULL DEFAULT '',
        postal_code TEXT NOT NULL DEFAULT '',
        city TEXT NOT NULL DEFAULT '',
        offline_sync_key TEXT NULL,
        source TEXT NOT NULL DEFAULT 'CAISSE',
        payment TEXT NOT NULL DEFAULT 'À ENCAISSER',
        status TEXT NOT NULL DEFAULT 'Enregistrée',
        total NUMERIC(12,2) NOT NULL DEFAULT 0,
        modification_flag BOOLEAN NOT NULL DEFAULT FALSE,
        change_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at BIGINT NOT NULL,
        updated_at BIGINT NOT NULL,
        modified_at BIGINT NULL
    )""")
    conn.execute("ALTER TABLE caisse_orders ADD COLUMN IF NOT EXISTS offline_sync_key TEXT NULL")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_caisse_orders_offline_sync_key ON caisse_orders(offline_sync_key) WHERE offline_sync_key IS NOT NULL")
    conn.execute("""CREATE TABLE IF NOT EXISTS caisse_order_items (
        id BIGSERIAL PRIMARY KEY,
        order_id TEXT NOT NULL REFERENCES caisse_orders(id) ON DELETE CASCADE,
        line_id TEXT NOT NULL,
        product_id TEXT NULL,
        name TEXT NOT NULL,
        qty INTEGER NOT NULL CHECK (qty > 0),
        unit_price NUMERIC(12,2) NOT NULL DEFAULT 0,
        options_json JSONB NOT NULL DEFAULT '[]'::jsonb,
        options_text TEXT NOT NULL DEFAULT '',
        prepared BOOLEAN NOT NULL DEFAULT FALSE,
        position INTEGER NOT NULL DEFAULT 0,
        UNIQUE(order_id, line_id)
    )""")


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


def ticket_type(source):
    return "Livraison" if str(source or "").upper() in {"LIVRAISON", "DELIVERY"} else "Comptoir"


def order_payload(conn, order_row):
    items = conn.execute(
        """SELECT line_id, product_id, name, qty, unit_price,
                  options_json::text AS options_json, options_text, prepared, position
           FROM caisse_order_items
           WHERE order_id = %s
           ORDER BY position, id""",
        (order_row["id"],),
    ).fetchall()
    clean_items = []
    for item in items:
        try:
            options = json.loads(item["options_json"] or "[]")
        except Exception:
            options = []
        clean_items.append({
            "line_id": item["line_id"],
            "product_id": item["product_id"],
            "name": item["name"],
            "qty": item["qty"],
            "unit_price": float(item["unit_price"]),
            "options": options,
            "options_text": item["options_text"],
            "prepared": bool(item["prepared"]),
            "position": item["position"],
        })
    return {
        "id": order_row["id"],
        "num": order_row["num"],
        "customer_name": order_row["customer_name"],
        "source": order_row["source"],
        "ticket_type": ticket_type(order_row["source"]),
        "payment": order_row["payment"],
        "status": order_row["status"],
        "total": float(order_row["total"]),
        "created_at": order_row["created_at"],
        "updated_at": order_row["updated_at"],
        "items": clean_items,
    }


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
    return jsonify({"data": data, "updatedAt": updated_at, "source": "catalog_admin_v2"})


@app.get("/api/catalog/summary")
def catalog_summary():
    data, updated_at = load_catalog()
    if not isinstance(data, dict):
        return jsonify({"ok": False, "source": "catalog_admin_v2", "categories": 0, "products": 0, "items": [], "updatedAt": updated_at}), 404
    raw_categories = data.get("categories") or []
    raw_products = data.get("products") or []
    categories = []
    for c in raw_categories:
        if isinstance(c, str):
            name, active = c.strip(), True
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
        active_selection_groups = [k for k, v in selection_groups.items() if isinstance(v, list) and v]
        items.append({
            "id": p.get("id"),
            "name": name,
            "category": p.get("category") or p.get("cat") or "",
            "price": p.get("price", 0),
            "optionGroups": len(direct_options) if direct_options else len(active_selection_groups),
            "hasDirectOptions": bool(direct_options),
            "photo": p.get("photo") or "",
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


@app.get("/api/catalog/product/<product_id>/options")
def product_options(product_id):
    data, updated_at = load_catalog()
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "Catalogue V2 indisponible", "updatedAt": updated_at}), 404
    for p in data.get("products") or []:
        if not isinstance(p, dict) or str(p.get("id") or "") != str(product_id):
            continue
        direct_options = p.get("options") if isinstance(p.get("options"), list) else []
        selections = p.get("optionSelections") if isinstance(p.get("optionSelections"), dict) else {}
        groups = direct_options
        if not groups:
            groups = [
                {"name": group_name, "options": values}
                for group_name, values in selections.items()
                if isinstance(values, list) and values
            ]
        return jsonify({
            "ok": True,
            "readOnly": True,
            "source": "catalog_admin_v2",
            "product": {"id": p.get("id"), "name": p.get("name"), "price": p.get("price", 0)},
            "groups": groups,
            "updatedAt": updated_at,
        })
    return jsonify({"ok": False, "error": "Produit introuvable", "updatedAt": updated_at}), 404


@app.post("/api/orders")
def create_order():
    payload = request.get_json(silent=True) or {}
    offline_sync_key = str(request.headers.get("X-BECHEFAA-OFFLINE-ID") or "").strip() or None
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        return jsonify({"ok": False, "error": "Commande vide"}), 400

    normalized = []
    total = Decimal("0.00")
    for position, item in enumerate(raw_items):
        if not isinstance(item, dict):
            return jsonify({"ok": False, "error": "Ligne de commande invalide"}), 400
        name = str(item.get("name") or "").strip()
        product_id = str(item.get("product_id") or "").strip() or None
        try:
            qty = int(item.get("qty") or 1)
            unit_price = Decimal(str(item.get("unit_price") or 0)).quantize(Decimal("0.01"))
        except (ValueError, TypeError, InvalidOperation):
            return jsonify({"ok": False, "error": "Prix ou quantité invalide"}), 400
        if not name or qty <= 0 or unit_price < 0:
            return jsonify({"ok": False, "error": "Ligne de commande invalide"}), 400
        options = item.get("options") if isinstance(item.get("options"), list) else []
        option_names = []
        for option in options:
            if isinstance(option, dict):
                label = str(option.get("name") or option.get("label") or "").strip()
                group = str(option.get("group") or "").strip()
                if label:
                    option_names.append((group + ": " if group else "") + label)
            elif option is not None:
                option_names.append(str(option))
        line_id = str(item.get("line_id") or uuid.uuid4().hex)
        normalized.append({
            "line_id": line_id,
            "product_id": product_id,
            "name": name,
            "qty": qty,
            "unit_price": unit_price,
            "options": options,
            "options_text": " • ".join(option_names),
            "position": position,
        })
        total += unit_price * qty

    now = int(time.time() * 1000)
    order_id = "caisse-" + uuid.uuid4().hex
    source = "LIVRAISON" if str(payload.get("ticket_type") or "").lower() == "livraison" else "CAISSE"
    customer_name = "Client livraison" if source == "LIVRAISON" else "Client comptoir"
    try:
        with db() as conn:
            with conn.transaction():
                ensure_order_schema(conn)
                conn.execute("LOCK TABLE caisse_orders IN EXCLUSIVE MODE")
                if offline_sync_key:
                    existing = conn.execute(
                        "SELECT id,num,total,status,source FROM caisse_orders WHERE offline_sync_key=%s LIMIT 1",
                        (offline_sync_key,),
                    ).fetchone()
                    if existing:
                        return jsonify({
                            "ok": True,
                            "id": existing["id"],
                            "num": existing["num"],
                            "total": float(existing["total"]),
                            "status": existing["status"],
                            "ticket_type": ticket_type(existing["source"]),
                            "duplicate": True,
                            "offline_sync_key": offline_sync_key,
                        }), 200
                row = conn.execute("SELECT COALESCE(MAX(num), 0) + 1 AS next_num FROM caisse_orders").fetchone()
                order_num = int(row["next_num"])
                conn.execute(
                    """INSERT INTO caisse_orders
                       (id, num, customer_name, offline_sync_key, source, payment, status, total, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (order_id, order_num, customer_name, offline_sync_key, source, "À ENCAISSER", "Enregistrée", total, now, now),
                )
                for line in normalized:
                    conn.execute(
                        """INSERT INTO caisse_order_items
                           (order_id, line_id, product_id, name, qty, unit_price, options_json, options_text, prepared, position)
                           VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, FALSE, %s)""",
                        (
                            order_id,
                            line["line_id"],
                            line["product_id"],
                            line["name"],
                            line["qty"],
                            line["unit_price"],
                            json.dumps(line["options"], ensure_ascii=False),
                            line["options_text"],
                            line["position"],
                        ),
                    )
    except Exception as exc:
        return jsonify({"ok": False, "error": "Enregistrement PostgreSQL impossible", "detail": str(exc)}), 500

    return jsonify({
        "ok": True,
        "id": order_id,
        "num": order_num,
        "total": float(total),
        "status": "Enregistrée",
        "ticket_type": ticket_type(source),
    }), 201


@app.post("/api/orders/<order_id>/send-kitchen")
def send_order_to_kitchen(order_id):
    now = int(time.time() * 1000)
    try:
        with db() as conn:
            with conn.transaction():
                row = conn.execute(
                    "SELECT id, num, status, total, source FROM caisse_orders WHERE id = %s FOR UPDATE",
                    (order_id,),
                ).fetchone()
                if not row:
                    return jsonify({"ok": False, "error": "Commande introuvable"}), 404
                if row["status"] == "À préparer":
                    return jsonify({
                        "ok": True,
                        "id": row["id"],
                        "num": row["num"],
                        "total": float(row["total"]),
                        "status": "À préparer",
                        "ticket_type": ticket_type(row["source"]),
                    }), 200
                if row["status"] != "Enregistrée":
                    return jsonify({
                        "ok": False,
                        "error": "Cette commande ne peut pas être envoyée en cuisine",
                        "status": row["status"],
                    }), 409
                conn.execute(
                    "UPDATE caisse_orders SET status = %s, updated_at = %s WHERE id = %s",
                    ("À préparer", now, order_id),
                )
    except Exception as exc:
        return jsonify({"ok": False, "error": "Envoi cuisine impossible", "detail": str(exc)}), 500

    return jsonify({
        "ok": True,
        "id": order_id,
        "num": row["num"],
        "total": float(row["total"]),
        "status": "À préparer",
        "ticket_type": ticket_type(row["source"]),
    }), 200


@app.get("/api/orders/history")
def orders_history():
    try:
        with db() as conn:
            ensure_order_schema(conn)
            conn.commit()
            rows = conn.execute(
                """SELECT id, num, customer_name, source, payment, status, total, created_at, updated_at
                   FROM caisse_orders
                   ORDER BY created_at DESC
                   LIMIT 150"""
            ).fetchall()
            orders = [order_payload(conn, row) for row in rows]
    except Exception as exc:
        return jsonify({"ok": False, "error": "Historique indisponible", "detail": str(exc)}), 500
    return jsonify({"ok": True, "orders": orders, "count": len(orders)})


@app.get("/api/kitchen/orders")
def kitchen_orders():
    try:
        with db() as conn:
            ensure_order_schema(conn)
            conn.commit()
            rows = conn.execute(
                """SELECT id, num, customer_name, source, payment, status, total, created_at, updated_at
                   FROM caisse_orders
                   WHERE status IN ('À préparer', 'En préparation')
                   ORDER BY updated_at ASC, num ASC
                   LIMIT 100"""
            ).fetchall()
            orders = [order_payload(conn, row) for row in rows]
    except Exception as exc:
        return jsonify({"ok": False, "error": "Cuisine indisponible", "detail": str(exc)}), 500
    return jsonify({"ok": True, "orders": orders, "count": len(orders)})


@app.get("/api/catalog/diagnostic/classic-burger")
def classic_burger_diagnostic():
    data, updated_at = load_catalog()
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "Catalogue V2 indisponible", "updatedAt": updated_at}), 404
    for p in data.get("products") or []:
        if not isinstance(p, dict):
            continue
        if str(p.get("name") or "").strip().lower() == "classic burger":
            interesting = {}
            for key, value in p.items():
                lk = str(key).lower()
                if any(token in lk for token in ("photo", "image", "picture", "media", "thumbnail")):
                    interesting[key] = value
            return jsonify({
                "ok": True,
                "source": "catalog_admin_v2",
                "name": p.get("name"),
                "id": p.get("id"),
                "category": p.get("category") or p.get("cat"),
                "price": p.get("price"),
                "imageFields": interesting,
                "allKeys": sorted([str(k) for k in p.keys()]),
                "updatedAt": updated_at,
                "readOnly": True,
            })
    return jsonify({"ok": False, "error": "Classic Burger introuvable", "updatedAt": updated_at}), 404


NAV_STYLE = """
.navlink{color:white;text-decoration:none;background:#263244;padding:9px 12px;border-radius:8px;font-weight:700;font-size:13px}
.navlink.active{background:#d97706}.navspacer{flex:1}
"""


@app.get("/pos")
def pos():
    html = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BÉCHÉFAA Caisse</title><meta name="theme-color" content="#0b0b0b"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><meta name="apple-mobile-web-app-title" content="BÉCHÉFAA Caisse"><link rel="manifest" href="/static/pwa/manifest.webmanifest?v=9"><link rel="icon" type="image/png" href="/favicon.ico?v=7"><link rel="apple-touch-icon" href="/favicon.ico?v=7"><style>
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#f4f5f7;color:#17191c}.top{min-height:64px;background:#111827;color:white;display:flex;align-items:center;padding:10px 22px;gap:10px;flex-wrap:wrap}.top b{font-size:22px}.status{font-size:13px}.navlink{color:white;text-decoration:none;background:#263244;padding:9px 12px;border-radius:8px;font-weight:700;font-size:13px}.navlink.active{background:#14804a}.navspacer{flex:1}.layout{display:grid;grid-template-columns:190px 1fr 370px;height:calc(100vh - 64px)}.cats{background:#fff;border-right:1px solid #ddd;padding:12px;overflow:auto}.cat{width:100%;padding:13px 10px;margin:4px 0;border:0;border-radius:8px;background:#f0f1f3;text-align:left;font-weight:700;cursor:pointer}.cat.active{background:#111827;color:#fff}.main{padding:18px;overflow:auto}.title{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px}.product{background:#fff;border:1px solid #ddd;border-radius:12px;padding:14px;min-height:118px;cursor:pointer;display:flex;flex-direction:column}.product:hover{box-shadow:0 2px 10px #0002}.product-photo{width:100%;height:120px;object-fit:cover;border-radius:8px;margin-bottom:10px}.name{font-weight:800;font-size:16px}.meta{font-size:12px;color:#666;margin-top:7px}.price{font-size:20px;font-weight:800;margin-top:auto;padding-top:10px}.cart{background:#fff;border-left:1px solid #ddd;padding:18px;overflow:auto}.cart h2{margin:0 0 10px}.empty{color:#777;padding:24px 0;text-align:center}.badge{font-size:11px;background:#e8eefc;border-radius:20px;padding:4px 8px;margin-top:8px;display:inline-block;width:max-content}.note{font-size:12px;color:#666;margin-top:20px;border-top:1px solid #eee;padding-top:12px}.opt-group{border-top:1px solid #eee;padding-top:12px;margin-top:12px}.opt-head{display:flex;justify-content:space-between;gap:8px;align-items:center;margin-bottom:7px}.opt-head b{display:block}.rule{font-size:11px;color:#777}.opt-value{width:100%;font-size:13px;background:#f4f5f7;border:1px solid #e3e5e8;border-radius:8px;padding:9px;margin:5px 0;cursor:pointer;text-align:left;display:flex;justify-content:space-between;gap:8px}.opt-value:hover{background:#eceff3}.opt-value.selected{background:#111827;color:#fff;border-color:#111827}.selection-summary{background:#f7f8fa;border:1px solid #e5e7eb;border-radius:10px;padding:10px;margin-bottom:10px;font-size:13px}.selection-summary b{display:block;margin-bottom:5px}.selection-price{font-size:18px;font-weight:800;margin-top:8px}.action{width:100%;border:0;border-radius:9px;padding:12px 10px;font-weight:800;cursor:pointer}.add{background:#111827;color:white;margin-top:12px}.save{background:#14804a;color:white;margin-top:12px}.kitchen{background:#d97706;color:white;margin-top:10px}.order-box{border-top:2px solid #111827;margin-top:18px;padding-top:16px}.order-line{border-bottom:1px solid #eee;padding:9px 0}.order-line-head{display:flex;justify-content:space-between;gap:8px;font-weight:700}.order-opts{font-size:11px;color:#666;margin-top:4px}.remove{border:0;background:transparent;color:#b42318;cursor:pointer;padding:3px 0;font-size:12px}.order-total{display:flex;justify-content:space-between;font-size:20px;font-weight:800;margin-top:12px}.success{background:#e8f7ee;border:1px solid #b9e2c8;border-radius:9px;padding:10px;margin:10px 0;font-size:13px}.error{background:#fff0ee;border:1px solid #f3c0ba;border-radius:9px;padding:10px;margin:10px 0;font-size:13px;color:#9d261d}.ticket-choice{display:flex;gap:8px;margin:8px 0 12px}.ticket-choice button{flex:1;border:1px solid #ccd1d8;background:#fff;border-radius:8px;padding:9px;cursor:pointer;font-weight:700}.ticket-choice button.active{background:#111827;color:#fff;border-color:#111827}@media(max-width:900px){.layout{grid-template-columns:150px 1fr}.cart{display:none}}
</style></head><body><div class="top"><b>BÉCHÉFAA-Caisse</b><a class="navlink active" href="/pos">Caisse</a><a class="navlink" href="/cuisine">Cuisine</a><a class="navlink" href="/historique">Historique</a><span class="navspacer"></span><span class="status" id="status">Chargement…</span></div><div class="layout"><aside class="cats" id="cats"></aside><main class="main"><div class="title"><h2 id="title">Catalogue</h2><span id="count"></span></div><div class="grid" id="grid"></div></main><aside class="cart"><h2 id="side-title">Options produit</h2><div class="ticket-choice"><button class="active" data-ticket="Comptoir">Comptoir</button><button data-ticket="Livraison">Livraison</button></div><div id="options"><div class="empty">Cliquez sur un produit pour sélectionner ses options.</div></div><div class="order-box"><h2>Commande</h2><div id="order-message"></div><div id="order"><div class="empty">Commande vide</div></div></div><div class="note">Phase 1 • Étape 4A : accès <b>Cuisine</b> et <b>Historique</b>. Les commandes restent uniquement dans PostgreSQL.</div></aside></div>
<script>
let DATA=null,current=null,currentProduct=null,currentGroups=[],selections={},ORDER=[],LAST_SAVED_ORDER=null,TICKET_TYPE='Comptoir';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function optionInfo(v){if(v===null||v===undefined)return{name:'',price:0};if(Array.isArray(v))return{name:String(v[0]??''),price:Number(v[1]||0)};if(typeof v==='string'||typeof v==='number')return{name:String(v),price:0};if(typeof v==='object')return{name:String(v.name||v.label||v.title||v.value||v.id||''),price:Number(v.price||v.extraPrice||v.supplement||0)};return{name:String(v),price:0}}
function groupInfo(g,i){let name=(g&&typeof g==='object'&&!Array.isArray(g)?(g.name||g.label||g.title):'')||('Groupe '+(i+1));let vals=(g&&typeof g==='object'&&!Array.isArray(g)?(g.options||g.values||g.items||g.choices):null);if(!Array.isArray(vals))vals=Array.isArray(g)?g:[];let max=0,required=false;if(g&&typeof g==='object'&&!Array.isArray(g)){max=Number(g.max??g.maxChoices??g.maximum??0)||0;required=Boolean(g.required)}return{name,vals,max,required}}
function selectionKey(gi,vi){return gi+':'+vi}
function selectedForGroup(gi){return Object.keys(selections).filter(k=>k.startsWith(gi+':')&&selections[k])}
function totalExtra(){let total=0;currentGroups.forEach((g,gi)=>{let info=groupInfo(g,gi);info.vals.forEach((v,vi)=>{if(selections[selectionKey(gi,vi)])total+=optionInfo(v).price})});return total}
function selectedOptions(){let out=[];currentGroups.forEach((g,gi)=>{let info=groupInfo(g,gi);info.vals.forEach((v,vi)=>{if(selections[selectionKey(gi,vi)]){let oi=optionInfo(v);out.push({group:info.name,name:oi.name,price:oi.price})}})});return out}
function requiredMissing(){return currentGroups.some((g,gi)=>{let info=groupInfo(g,gi);return info.required&&selectedForGroup(gi).length===0})}
function renderOptions(){if(!currentProduct)return;let base=Number(currentProduct.price||0),extra=totalExtra();let picked=selectedOptions();let summary=`<div class="selection-summary"><b>Sélection en cours</b>${picked.length?esc(picked.map(x=>x.name).join(' • ')):'Aucune option sélectionnée'}<div class="selection-price">${(base+extra).toFixed(2).replace('.',',')} €</div></div>`;let groups=currentGroups.map((g,gi)=>{let info=groupInfo(g,gi);let rule=[];if(info.required)rule.push('obligatoire');if(info.max===1)rule.push('1 choix');else if(info.max>1)rule.push(info.max+' choix max');let vals=info.vals.map((v,vi)=>{let oi=optionInfo(v),key=selectionKey(gi,vi),sel=!!selections[key];return `<button class="opt-value ${sel?'selected':''}" data-gi="${gi}" data-vi="${vi}"><span>${sel?'✓ ':''}${esc(oi.name)}</span><span>${oi.price?('+'+oi.price.toFixed(2).replace('.',',')+' €'):''}</span></button>`}).join('');return `<div class="opt-group"><div class="opt-head"><b>${esc(info.name)}</b><span class="rule">${esc(rule.join(' • '))}</span></div>${vals||'<div class="empty">Aucune valeur</div>'}</div>`}).join('');document.getElementById('options').innerHTML=summary+groups+`<button class="action add" data-action="add-current">Ajouter à la commande</button>`}
function toggleOption(gi,vi){let info=groupInfo(currentGroups[gi],gi),key=selectionKey(gi,vi),was=!!selections[key];if(was){delete selections[key];renderOptions();return}if(info.max===1){selectedForGroup(gi).forEach(k=>delete selections[k])}else if(info.max>1&&selectedForGroup(gi).length>=info.max){return}selections[key]=true;renderOptions()}
function showOptions(id,name){document.getElementById('side-title').textContent='Options • '+name;document.getElementById('options').innerHTML='<div class="empty">Chargement…</div>';selections={};fetch('/api/catalog/product/'+encodeURIComponent(id)+'/options').then(r=>r.json()).then(d=>{if(!d.ok){document.getElementById('options').innerHTML='<div class="empty">Produit introuvable.</div>';return}currentProduct=d.product||{id:id,name:name,price:0};currentGroups=Array.isArray(d.groups)?d.groups:[];renderOptions()}).catch(()=>{document.getElementById('options').innerHTML='<div class="empty">Impossible de lire les options.</div>'})}
function addCurrent(){if(!currentProduct)return;if(requiredMissing()){document.getElementById('order-message').innerHTML='<div class="error">Sélectionnez les options obligatoires.</div>';return}let opts=selectedOptions(),unit=Number(currentProduct.price||0)+totalExtra();ORDER.push({line_id:'line-'+Date.now()+'-'+Math.random().toString(16).slice(2),product_id:String(currentProduct.id||''),name:String(currentProduct.name||''),qty:1,unit_price:Number(unit.toFixed(2)),options:opts});document.getElementById('order-message').innerHTML='';selections={};renderOptions();renderOrder()}
function renderOrder(){let el=document.getElementById('order');if(!ORDER.length){el.innerHTML='<div class="empty">Commande vide</div>';return}let total=ORDER.reduce((s,l)=>s+Number(l.unit_price||0)*Number(l.qty||1),0);el.innerHTML=ORDER.map((l,i)=>`<div class="order-line"><div class="order-line-head"><span>${esc(l.name)}</span><span>${Number(l.unit_price).toFixed(2).replace('.',',')} €</span></div>${l.options.length?`<div class="order-opts">${esc(l.options.map(o=>o.name).join(' • '))}</div>`:''}<button class="remove" data-action="remove-line" data-index="${i}">Retirer</button></div>`).join('')+`<div class="order-total"><span>Total</span><span>${total.toFixed(2).replace('.',',')} €</span></div><button class="action save" data-action="save-order">Enregistrer la commande ${esc(TICKET_TYPE)}</button>`}
function saveOrder(){if(!ORDER.length)return;let btn=document.querySelector('[data-action="save-order"]');if(btn){btn.disabled=true;btn.textContent='Enregistrement…'}document.getElementById('order-message').innerHTML='';fetch('/api/orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items:ORDER,ticket_type:TICKET_TYPE})}).then(async r=>{let d=await r.json();if(!r.ok||!d.ok)throw new Error(d.detail||d.error||'Erreur');LAST_SAVED_ORDER=d;ORDER=[];renderOrder();document.getElementById('order-message').innerHTML=`<div class="success"><b>Commande #${esc(d.num)} enregistrée • ${esc(d.ticket_type)}</b><br>Total ${Number(d.total||0).toFixed(2).replace('.',',')} € • ${esc(d.status)}</div><button class="action kitchen" data-action="send-kitchen" data-order-id="${esc(d.id)}" data-order-num="${esc(d.num)}">Envoyer en cuisine</button>`}).catch(err=>{document.getElementById('order-message').innerHTML=`<div class="error"><b>Commande non enregistrée.</b><br>${esc(err.message)}</div>`;renderOrder()})}
function sendKitchen(orderId,orderNum){if(!orderId)return;let btn=document.querySelector('[data-action="send-kitchen"]');if(btn){btn.disabled=true;btn.textContent='Envoi en cuisine…'}fetch('/api/orders/'+encodeURIComponent(orderId)+'/send-kitchen',{method:'POST'}).then(async r=>{let d=await r.json();if(!r.ok||!d.ok)throw new Error(d.detail||d.error||'Erreur');LAST_SAVED_ORDER=d;document.getElementById('order-message').innerHTML=`<div class="success"><b>Commande #${esc(d.num||orderNum)} envoyée en cuisine</b><br>${esc(d.ticket_type)} • Statut : ${esc(d.status)}<br><a href="/cuisine">Ouvrir l’écran cuisine</a></div>`}).catch(err=>{document.getElementById('order-message').innerHTML=`<div class="error"><b>Envoi cuisine impossible.</b><br>${esc(err.message)}</div><button class="action kitchen" data-action="send-kitchen" data-order-id="${esc(orderId)}" data-order-num="${esc(orderNum)}">Réessayer l’envoi en cuisine</button>`})}
function render(){let items=DATA.items.filter(p=>!current||p.category===current);document.getElementById('title').textContent=current||'Tous les produits';document.getElementById('count').textContent=items.length+' produit(s)';document.getElementById('grid').innerHTML=items.map(p=>`<div class="product" data-id="${esc(p.id)}" data-name="${esc(p.name)}">${p.photo?`<img class="product-photo" src="${esc(p.photo)}" alt="${esc(p.name)}">`:''}<div class="name">${esc(p.name)}</div><div class="meta">${esc(p.category)}</div>${p.optionGroups?`<span class="badge">${p.optionGroups} groupe(s) d’options</span>`:''}<div class="price">${Number(p.price||0).toFixed(2).replace('.',',')} €</div></div>`).join('');document.querySelectorAll('.cat').forEach(b=>b.classList.toggle('active',b.dataset.cat===(current||'')))}
document.querySelector('.ticket-choice').onclick=e=>{let b=e.target.closest('[data-ticket]');if(!b)return;TICKET_TYPE=b.dataset.ticket;document.querySelectorAll('[data-ticket]').forEach(x=>x.classList.toggle('active',x===b));renderOrder()};
fetch('/api/catalog/summary').then(r=>r.json()).then(d=>{DATA=d;document.getElementById('status').textContent=d.products+' produits • PostgreSQL';let cats=['',...d.categoryNames];document.getElementById('cats').innerHTML=cats.map(c=>`<button class="cat" data-cat="${esc(c)}">${esc(c||'Tous les produits')}</button>`).join('');document.getElementById('cats').onclick=e=>{let b=e.target.closest('.cat');if(!b)return;current=b.dataset.cat||null;render()};document.getElementById('grid').onclick=e=>{let p=e.target.closest('.product');if(!p)return;showOptions(p.dataset.id,p.dataset.name)};document.querySelector('.cart').onclick=e=>{let b=e.target.closest('[data-action]');if(!b)return;let action=b.dataset.action;if(action==='add-current')addCurrent();else if(action==='remove-line'){ORDER.splice(Number(b.dataset.index),1);renderOrder()}else if(action==='save-order')saveOrder();else if(action==='send-kitchen')sendKitchen(b.dataset.orderId,b.dataset.orderNum);let opt=e.target.closest('.opt-value');if(opt)toggleOption(Number(opt.dataset.gi),Number(opt.dataset.vi))};document.getElementById('options').onclick=e=>{let b=e.target.closest('.opt-value');if(!b)return;toggleOption(Number(b.dataset.gi),Number(b.dataset.vi))};render();renderOrder()}).catch(()=>{document.getElementById('status').textContent='Erreur catalogue';document.getElementById('grid').innerHTML='<p>Impossible de charger le catalogue.</p>'});
if('serviceWorker' in navigator){
  window.addEventListener('load',()=>navigator.serviceWorker.register('/caisse-sw.js',{scope:'/'}).catch(()=>{}));
}
</script></body></html>'''
    return Response(html, content_type="text/html; charset=utf-8")


@app.get("/cuisine")
def cuisine():
    html = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Cuisine</title><style>
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#101318;color:#fff}.top{min-height:64px;background:#111827;display:flex;align-items:center;gap:10px;padding:10px 20px;flex-wrap:wrap}.top b{font-size:24px}.navlink{color:#fff;text-decoration:none;background:#263244;padding:9px 12px;border-radius:8px;font-weight:700;font-size:13px}.navlink.active{background:#d97706}.spacer{flex:1}.wrap{padding:18px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}.ticket{background:#fff;color:#17191c;border-radius:14px;overflow:hidden;border:3px solid #d97706}.head{background:#fff3df;padding:14px;display:flex;justify-content:space-between;gap:10px;align-items:start}.num{font-size:28px;font-weight:900}.kind{font-size:12px;font-weight:800;background:#111827;color:#fff;padding:5px 8px;border-radius:20px}.meta{font-size:12px;color:#666;margin-top:5px}.items{padding:10px 14px 16px}.item{padding:10px 0;border-bottom:1px solid #eee}.item:last-child{border-bottom:0}.item b{font-size:18px}.opts{font-size:13px;color:#555;margin-top:4px}.empty{padding:50px;text-align:center;color:#b8bec8}.error{background:#4b1616;padding:14px;border-radius:10px}.count{font-weight:800}
</style></head><body><div class="top"><b>BÉCHÉFAA • CUISINE</b><a class="navlink" href="/pos">Caisse</a><a class="navlink active" href="/cuisine">Cuisine</a><a class="navlink" href="/historique">Historique</a><span class="spacer"></span><span class="count" id="count">Chargement…</span></div><div class="wrap"><div id="error"></div><div class="grid" id="grid"></div></div><script>
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function clock(ms){if(!ms)return '';return new Date(Number(ms)).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})}
async function load(){try{let r=await fetch('/api/kitchen/orders',{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw new Error(d.detail||d.error||'Erreur');document.getElementById('count').textContent=d.count+' commande(s)';document.getElementById('error').innerHTML='';document.getElementById('grid').innerHTML=d.orders.length?d.orders.map(o=>`<article class="ticket"><div class="head"><div><div class="num">#${esc(o.num)}</div><div class="meta">${esc(clock(o.updated_at))} • ${esc(o.status)}</div></div><span class="kind">${esc(o.ticket_type)}</span></div><div class="items">${o.items.map(i=>`<div class="item"><b>${esc(i.qty)} × ${esc(i.name)}</b>${i.options_text?`<div class="opts">${esc(i.options_text)}</div>`:''}</div>`).join('')}</div></article>`).join(''):'<div class="empty">Aucune commande à préparer.</div>'}catch(e){document.getElementById('error').innerHTML=`<div class="error">Cuisine indisponible : ${esc(e.message)}</div>`}}load();setInterval(load,5000);
</script></body></html>'''
    return Response(html, content_type="text/html; charset=utf-8")


@app.get("/historique")
def historique():
    html = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Historique</title><style>
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#f4f5f7;color:#17191c}.top{min-height:64px;background:#111827;color:#fff;display:flex;align-items:center;gap:10px;padding:10px 20px;flex-wrap:wrap}.top b{font-size:22px}.navlink{color:#fff;text-decoration:none;background:#263244;padding:9px 12px;border-radius:8px;font-weight:700;font-size:13px}.navlink.active{background:#2563eb}.spacer{flex:1}.wrap{padding:20px;max-width:1200px;margin:auto}.filters{display:flex;gap:8px;margin:0 0 14px;flex-wrap:wrap}.filter{border:1px solid #ccd1d8;background:#fff;border-radius:8px;padding:9px 12px;font-weight:700;cursor:pointer}.filter.active{background:#111827;color:#fff}.table{background:#fff;border-radius:12px;overflow:hidden;border:1px solid #ddd}.row{display:grid;grid-template-columns:80px 150px 110px 1fr 130px 110px;gap:10px;align-items:center;padding:12px 14px;border-bottom:1px solid #eee}.row.head{background:#eef0f3;font-size:12px;font-weight:800}.row:last-child{border-bottom:0}.num{font-weight:900}.kind{font-size:12px;font-weight:800}.status{font-size:12px}.total{text-align:right;font-weight:800}.items{font-size:12px;color:#666;margin-top:3px}.empty{padding:40px;text-align:center;color:#777}.error{background:#fff0ee;border:1px solid #f3c0ba;color:#9d261d;padding:12px;border-radius:9px}@media(max-width:800px){.row{grid-template-columns:70px 1fr 100px}.hide-sm{display:none}}
</style></head><body><div class="top"><b>BÉCHÉFAA • HISTORIQUE</b><a class="navlink" href="/pos">Caisse</a><a class="navlink" href="/cuisine">Cuisine</a><a class="navlink active" href="/historique">Historique</a><span class="spacer"></span><span id="count">Chargement…</span></div><div class="wrap"><div class="filters"><button class="filter active" data-filter="Tous">Tous</button><button class="filter" data-filter="Comptoir">Comptoir</button><button class="filter" data-filter="Livraison">Livraison</button></div><div id="error"></div><div class="table"><div class="row head"><span>N°</span><span>Date / heure</span><span>Type</span><span class="hide-sm">Ticket</span><span>Statut</span><span>Total</span></div><div id="rows"></div></div></div><script>
let ORDERS=[],FILTER='Tous';const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function dt(ms){if(!ms)return '';return new Date(Number(ms)).toLocaleString('fr-FR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}
function render(){let data=ORDERS.filter(o=>FILTER==='Tous'||o.ticket_type===FILTER);document.getElementById('count').textContent=data.length+' ticket(s)';document.getElementById('rows').innerHTML=data.length?data.map(o=>`<div class="row"><span class="num">#${esc(o.num)}</span><span>${esc(dt(o.created_at))}</span><span class="kind">${esc(o.ticket_type)}</span><span class="hide-sm"><b>${esc(o.customer_name)}</b><div class="items">${esc(o.items.map(i=>i.qty+'× '+i.name).join(' • '))}</div></span><span class="status">${esc(o.status)}</span><span class="total">${Number(o.total||0).toFixed(2).replace('.',',')} €</span></div>`).join(''):'<div class="empty">Aucun ticket dans cette catégorie.</div>'}
document.querySelector('.filters').onclick=e=>{let b=e.target.closest('[data-filter]');if(!b)return;FILTER=b.dataset.filter;document.querySelectorAll('.filter').forEach(x=>x.classList.toggle('active',x===b));render()};
fetch('/api/orders/history',{cache:'no-store'}).then(async r=>{let d=await r.json();if(!r.ok||!d.ok)throw new Error(d.detail||d.error||'Erreur');ORDERS=d.orders;document.getElementById('error').innerHTML='';render()}).catch(e=>{document.getElementById('error').innerHTML=`<div class="error">Historique indisponible : ${esc(e.message)}</div>`});
</script></body></html>'''
    return Response(html, content_type="text/html; charset=utf-8")


@app.get("/")
def root():
    return "BÉCHÉFAA-Caisse clean backend", 200, {"Content-Type": "text/plain; charset=utf-8"}
