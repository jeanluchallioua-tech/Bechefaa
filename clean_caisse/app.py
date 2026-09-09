import json
import os
import time
import uuid
from decimal import Decimal, InvalidOperation

from flask import Flask, jsonify, Response, request
import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("POSTGRESQL_ADDON_URI") or os.getenv("DATABASE_URL")

app = Flask(__name__)


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
        notes TEXT NOT NULL DEFAULT '',
        created_at BIGINT NOT NULL,
        updated_at BIGINT NOT NULL
    )""")
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
                row = conn.execute("SELECT COALESCE(MAX(num), 0) + 1 AS next_num FROM caisse_orders").fetchone()
                order_num = int(row["next_num"])
                conn.execute(
                    """INSERT INTO caisse_orders
                       (id, num, customer_name, source, payment, status, total, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (order_id, order_num, customer_name, source, "À ENCAISSER", "Enregistrée", total, now, now),
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
                   WHERE (to_timestamp(created_at / 1000.0) AT TIME ZONE 'Europe/Paris')::date
                         = (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Paris')::date
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
                "product": {"id": p.get("id"), "name": p.get("name")},
                "imageFields": interesting,
                "updatedAt": updated_at,
            })
    return jsonify({"ok": False, "error": "Classic Burger introuvable", "updatedAt": updated_at}), 404


@app.get("/api/debug/routes")
def debug_routes():
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({"rule": str(rule), "methods": sorted(m for m in rule.methods if m not in {"HEAD", "OPTIONS"})})
    return jsonify({"ok": True, "routes": routes})


@app.get("/api/debug/orders")
def debug_orders():
    try:
        with db() as conn:
            ensure_order_schema(conn)
            conn.commit()
            rows = conn.execute(
                """SELECT id, num, customer_name, source, payment, status, total, created_at, updated_at
                   FROM caisse_orders
                   ORDER BY created_at DESC
                   LIMIT 20"""
            ).fetchall()
        return jsonify({"ok": True, "count": len(rows), "orders": rows})
    except Exception as exc:
        return jsonify({"ok": False, "error": "Debug commandes indisponible", "detail": str(exc)}), 500


@app.get("/api/debug/schema")
def debug_schema():
    try:
        with db() as conn:
            rows = conn.execute(
                """SELECT column_name, data_type, is_nullable, column_default
                   FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='caisse_orders'
                   ORDER BY ordinal_position"""
            ).fetchall()
        return jsonify({"ok": True, "table": "caisse_orders", "columns": rows})
    except Exception as exc:
        return jsonify({"ok": False, "error": "Debug schéma indisponible", "detail": str(exc)}), 500


@app.get("/api/debug/order/<order_id>")
def debug_order(order_id):
    try:
        with db() as conn:
            ensure_order_schema(conn)
            conn.commit()
            row = conn.execute(
                """SELECT id, num, customer_name, source, payment, status, total, created_at, updated_at,
                          modification_flag, change_summary::text AS change_summary, modified_at
                   FROM caisse_orders
                   WHERE id=%s""",
                (order_id,),
            ).fetchone()
            if not row:
                return jsonify({"ok": False, "error": "Commande introuvable"}), 404
            items = conn.execute(
                """SELECT id, line_id, product_id, name, qty, unit_price,
                          options_json::text AS options_json, options_text, prepared, position
                   FROM caisse_order_items
                   WHERE order_id=%s
                   ORDER BY position, id""",
                (order_id,),
            ).fetchall()
        return jsonify({"ok": True, "order": row, "items": items})
    except Exception as exc:
        return jsonify({"ok": False, "error": "Debug commande indisponible", "detail": str(exc)}), 500


@app.get("/pos")
def pos():
    return Response("""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BÉCHÉFAA — Caisse</title>
<style>
:root{--bg:#0b0b0c;--panel:#141416;--line:#2a2a2d;--txt:#fff;--muted:#aaa;--accent:#e21f2f;--ok:#18a957}
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:var(--bg);color:var(--txt)}
header{height:64px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 18px;background:#101012;position:sticky;top:0;z-index:5}
.brand{font-weight:900;letter-spacing:.4px}.brand b{color:var(--accent)}.pill{border:1px solid var(--line);border-radius:999px;padding:7px 10px;color:var(--muted);font-size:12px}
main{max-width:1280px;margin:0 auto;padding:18px}.grid{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:16px}.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px}.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.toolbar input,.toolbar select{background:#0e0e10;color:#fff;border:1px solid var(--line);border-radius:10px;padding:10px 12px}.toolbar input{min-width:240px;flex:1}.cats{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.cat{border:1px solid var(--line);background:#0e0e10;color:#ddd;border-radius:999px;padding:8px 12px;cursor:pointer}.cat.active{background:#fff;color:#111}.products{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:12px}.product{border:1px solid var(--line);background:#0e0e10;border-radius:12px;padding:12px;cursor:pointer;min-height:94px;display:flex;flex-direction:column;justify-content:space-between}.product:hover{border-color:#555}.product .name{font-weight:800}.product .meta{color:var(--muted);font-size:12px}.product .price{font-weight:900;margin-top:8px}.cart{position:sticky;top:82px}.cart h2{margin:0 0 10px}.cart-list{display:flex;flex-direction:column;gap:8px;max-height:48vh;overflow:auto}.cart-line{border:1px solid var(--line);border-radius:10px;padding:10px;background:#0e0e10}.cart-line .top{display:flex;justify-content:space-between;gap:8px}.cart-line .opts{font-size:12px;color:#bbb;margin-top:5px}.cart-line button{background:transparent;color:#ff6b78;border:0;cursor:pointer}.total{display:flex;justify-content:space-between;font-size:20px;font-weight:900;border-top:1px solid var(--line);padding-top:12px;margin-top:12px}.actions{display:grid;gap:8px;margin-top:12px}.btn{border:0;border-radius:10px;padding:12px 14px;font-weight:900;cursor:pointer}.btn.primary{background:var(--accent);color:#fff}.btn.secondary{background:#252529;color:#fff}.btn:disabled{opacity:.45;cursor:not-allowed}.status{font-size:13px;color:var(--muted);min-height:18px;margin-top:8px}.history{margin-top:16px}.history-list{display:grid;gap:10px}.order{border:1px solid var(--line);border-radius:12px;padding:12px;background:#0e0e10}.order-head{display:flex;justify-content:space-between;gap:12px;align-items:center}.order-title{font-weight:900}.order-meta{color:var(--muted);font-size:12px;margin-top:3px}.order-items{font-size:13px;color:#ddd;margin-top:8px}.badge{display:inline-block;border:1px solid #444;border-radius:999px;padding:4px 8px;font-size:11px}.empty{color:var(--muted);padding:20px;text-align:center;border:1px dashed var(--line);border-radius:12px}
@media(max-width:900px){.grid{grid-template-columns:1fr}.cart{position:static}.products{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:560px){.products{grid-template-columns:1fr}.toolbar input{min-width:0}}
</style>
</head>
<body>
<header><div class="brand">BÉCHÉFAA <b>CAISSE</b></div><div class="pill" id="dbState">PostgreSQL</div></header>
<main>
<div class="grid">
<section class="card">
<div class="toolbar"><input id="search" placeholder="Rechercher un produit"><select id="ticketType"><option>Comptoir</option><option>Livraison</option></select></div>
<div class="cats" id="cats"></div><div class="products" id="products"></div>
</section>
<aside class="card cart"><h2>Commande</h2><div id="cartList" class="cart-list"></div><div class="total"><span>Total</span><span id="cartTotal">0,00 €</span></div><div class="actions"><button class="btn primary" id="saveBtn" disabled>Enregistrer la commande</button><button class="btn secondary" id="kitchenBtn" disabled>Envoyer à la cuisine</button><button class="btn secondary" id="clearBtn">Vider</button></div><div class="status" id="status"></div></aside>
</div>
<section class="card history"><div class="toolbar" style="justify-content:space-between"><h2 style="margin:0">Historique PostgreSQL</h2><button class="btn secondary" id="refreshHistory">Actualiser</button></div><div id="history" class="history-list" style="margin-top:12px"></div></section>
</main>
<script>
let catalog={categories:[],products:[]}, cart=[], selectedCategory='Toutes', currentOrderId=null;
const euro=n=>Number(n||0).toLocaleString('fr-FR',{minimumFractionDigits:2,maximumFractionDigits:2})+' €';
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
function normalizeCatalog(data){
 const cats=[];(data?.categories||[]).forEach(c=>{if(typeof c==='string'){if(c.trim())cats.push(c.trim())}else if(c&&c.active!==false){const n=String(c.name||c.label||'').trim();if(n)cats.push(n)}});
 const products=(data?.products||[]).filter(p=>p&&p.active!==false&&p.name).map(p=>({id:String(p.id||''),name:String(p.name),category:String(p.category||p.cat||''),price:Number(p.price||0),raw:p}));
 return {categories:cats,products};
}
async function loadCatalog(){const r=await fetch('/api/catalog');const j=await r.json();catalog=normalizeCatalog(j.data||{});renderCats();renderProducts()}
function renderCats(){const el=document.getElementById('cats');const cats=['Toutes',...catalog.categories];el.innerHTML=cats.map(c=>`<button class="cat ${c===selectedCategory?'active':''}" data-cat="${esc(c)}">${esc(c)}</button>`).join('');el.querySelectorAll('.cat').forEach(b=>b.onclick=()=>{selectedCategory=b.dataset.cat;renderCats();renderProducts()})}
function renderProducts(){const q=document.getElementById('search').value.trim().toLowerCase();const list=catalog.products.filter(p=>(selectedCategory==='Toutes'||p.category===selectedCategory)&&(!q||p.name.toLowerCase().includes(q)));document.getElementById('products').innerHTML=list.length?list.map(p=>`<button class="product" data-id="${esc(p.id)}"><span class="name">${esc(p.name)}</span><span class="meta">${esc(p.category)}</span><span class="price">${euro(p.price)}</span></button>`).join(''):'<div class="empty">Aucun produit</div>';document.querySelectorAll('.product').forEach(b=>b.onclick=()=>addProduct(b.dataset.id))}
async function addProduct(id){const p=catalog.products.find(x=>x.id===id);if(!p)return;let options=[];try{const r=await fetch('/api/catalog/product/'+encodeURIComponent(id)+'/options');const j=await r.json();if(j.ok&&Array.isArray(j.groups)){for(const g of j.groups){const values=Array.isArray(g.options)?g.options:[];if(!values.length)continue;const labels=values.map(v=>typeof v==='string'?v:String(v.name||v.label||'')).filter(Boolean);if(!labels.length)continue;const answer=prompt((g.name||'Option')+'\n'+labels.map((x,i)=>(i+1)+'. '+x).join('\n')+'\nNuméro (vide = aucune)');const idx=Number(answer)-1;if(answer&&labels[idx])options.push({group:g.name||'',name:labels[idx]})}}}catch(e){}cart.push({line_id:crypto.randomUUID?crypto.randomUUID():String(Date.now()+Math.random()),product_id:p.id,name:p.name,qty:1,unit_price:p.price,options});renderCart()}
function renderCart(){const el=document.getElementById('cartList');el.innerHTML=cart.length?cart.map((x,i)=>`<div class="cart-line"><div class="top"><b>${esc(x.name)}</b><button data-i="${i}">✕</button></div><div class="opts">${x.options.map(o=>esc((o.group?o.group+': ':'')+o.name)).join(' • ')}</div><div>${x.qty} × ${euro(x.unit_price)}</div></div>`).join(''):'<div class="empty">Panier vide</div>';el.querySelectorAll('button[data-i]').forEach(b=>b.onclick=()=>{cart.splice(Number(b.dataset.i),1);renderCart()});document.getElementById('cartTotal').textContent=euro(cart.reduce((s,x)=>s+x.qty*x.unit_price,0));document.getElementById('saveBtn').disabled=!cart.length;document.getElementById('kitchenBtn').disabled=!currentOrderId}
async function saveOrder(){const btn=document.getElementById('saveBtn'),st=document.getElementById('status');btn.disabled=true;st.textContent='Enregistrement…';try{const r=await fetch('/api/orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ticket_type:document.getElementById('ticketType').value,items:cart})});const j=await r.json();if(!r.ok)throw new Error(j.error+(j.detail?' — '+j.detail:''));currentOrderId=j.id;st.textContent=`Commande #${j.num} enregistrée — ${euro(j.total)}`;document.getElementById('kitchenBtn').disabled=false;await loadHistory()}catch(e){st.textContent=e.message}finally{btn.disabled=!cart.length}}
async function sendKitchen(){if(!currentOrderId)return;const st=document.getElementById('status');st.textContent='Envoi cuisine…';try{const r=await fetch('/api/orders/'+encodeURIComponent(currentOrderId)+'/send-kitchen',{method:'POST'});const j=await r.json();if(!r.ok)throw new Error(j.error+(j.detail?' — '+j.detail:''));st.textContent=`Commande #${j.num} envoyée en cuisine`;cart=[];currentOrderId=null;renderCart();await loadHistory()}catch(e){st.textContent=e.message}}
async function loadHistory(){const r=await fetch('/api/orders/history');const j=await r.json();const el=document.getElementById('history');if(!j.ok){el.innerHTML='<div class="empty">'+esc(j.error)+'</div>';return}el.innerHTML=j.orders.length?j.orders.map(o=>`<div class="order"><div class="order-head"><div><div class="order-title">#${o.num} · ${esc(o.ticket_type)} · ${euro(o.total)}</div><div class="order-meta">${new Date(o.created_at).toLocaleString('fr-FR')} · ${esc(o.status)}</div></div><span class="badge">${esc(o.payment)}</span></div><div class="order-items">${o.items.map(i=>esc(i.qty+'× '+i.name+(i.options_text?' — '+i.options_text:''))).join('<br>')}</div></div>`).join(''):'<div class="empty">Aucune commande</div>'}
document.getElementById('search').addEventListener('input',renderProducts);document.getElementById('saveBtn').onclick=saveOrder;document.getElementById('kitchenBtn').onclick=sendKitchen;document.getElementById('clearBtn').onclick=()=>{cart=[];currentOrderId=null;renderCart();document.getElementById('status').textContent=''};document.getElementById('refreshHistory').onclick=loadHistory;
renderCart();loadCatalog();loadHistory();
</script>
</body></html>""", content_type="text/html; charset=utf-8")
