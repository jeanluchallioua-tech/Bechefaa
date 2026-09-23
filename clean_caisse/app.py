import json
import os
import base64
import time
import uuid
from decimal import Decimal, InvalidOperation

from flask import Flask, jsonify, Response, request
import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("POSTGRESQL_ADDON_URI") or os.getenv("DATABASE_URL")

app = Flask(__name__)

CAISSE_ICON_B64 = """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[...truncated...]"""

@app.get("/caisse-icon.png")
def caisse_icon_png():
    response = Response(base64.b64decode(CAISSE_ICON_B64), mimetype="image/png")
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response

@app.get("/caisse-icon-512.svg")
def caisse_icon_512_svg():
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
<rect width="512" height="512" rx="86" fill="#ffffff"/>
<image href="data:image/png;base64,{CAISSE_ICON_B64}" x="0" y="0" width="512" height="512" preserveAspectRatio="xMidYMid meet"/>
</svg>'''
    response = Response(svg, mimetype="image/svg+xml")
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response

@app.get("/caisse-manifest.webmanifest")
def caisse_manifest():
    manifest = {
        "id": "/pos",
        "name": "BÉCHÉFAA Caisse",
        "short_name": "Caisse",
        "description": "Accès direct à la caisse BÉCHÉFAA",
        "start_url": "/pos",
        "scope": "/",
        "display": "standalone",
        "orientation": "landscape",
        "background_color": "#0b0b0b",
        "theme_color": "#0b0b0b",
        "icons": [
            {"src": "/caisse-icon.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "/caisse-icon-512.svg", "sizes": "512x512", "type": "image/svg+xml", "purpose": "any"}
        ]
    }
    response = Response(json.dumps(manifest, ensure_ascii=False), content_type="application/manifest+json; charset=utf-8")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response

@app.get("/caisse-sw.js")
def caisse_service_worker():
    js = r'''const CACHE="bechefaa-caisse-pwa-v2";
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
<title>BÉCHÉFAA Caisse</title><meta name="theme-color" content="#0b0b0b"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><meta name="apple-mobile-web-app-title" content="BÉCHÉFAA Caisse"><link rel="manifest" href="/caisse-manifest.webmanifest"><link rel="icon" type="image/png" href="/caisse-icon.png"><link rel="apple-touch-icon" href="/caisse-icon.png"><style>
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
