import json
import os

from flask import Flask, jsonify, Response
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
    return jsonify({"ok": database == "postgresql", "service": "BECHEFAA-Caisse", "database": database,
                    "catalogue": "catalog_admin_v2", "orders": "caisse_orders", "clients": "caisse_clients"}), (200 if database == "postgresql" else 503)


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
        if isinstance(c, str): name, active = c.strip(), True
        elif isinstance(c, dict): name, active = str(c.get("name") or c.get("label") or "").strip(), c.get("active", True) is not False
        else: continue
        if name and active: categories.append(name)
    items = []
    for p in raw_products:
        if not isinstance(p, dict) or p.get("active", True) is False: continue
        name = str(p.get("name") or "").strip()
        if not name: continue
        direct_options = p.get("options") if isinstance(p.get("options"), list) else []
        selection_groups = p.get("optionSelections") if isinstance(p.get("optionSelections"), dict) else {}
        active_selection_groups = [k for k,v in selection_groups.items() if isinstance(v,list) and v]
        photo = p.get("photo") if name.lower() == "classic burger" else ""
        items.append({"id": p.get("id"), "name": name, "category": p.get("category") or p.get("cat") or "",
                      "price": p.get("price",0), "optionGroups": len(direct_options) if direct_options else len(active_selection_groups),
                      "hasDirectOptions": bool(direct_options), "photo": photo})
    return jsonify({"ok": True, "source": "catalog_admin_v2", "categories": len(categories), "categoryNames": categories,
                    "products": len(items), "items": items, "updatedAt": updated_at})


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
                "readOnly": True
            })
    return jsonify({"ok": False, "error": "Classic Burger introuvable", "updatedAt": updated_at}), 404


@app.get("/pos")
def pos():
    html = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BÉCHÉFAA-Caisse</title><style>
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#f4f5f7;color:#17191c}.top{height:64px;background:#111827;color:white;display:flex;align-items:center;padding:0 22px;gap:20px}.top b{font-size:22px}.status{margin-left:auto;font-size:13px}.layout{display:grid;grid-template-columns:190px 1fr 310px;height:calc(100vh - 64px)}.cats{background:#fff;border-right:1px solid #ddd;padding:12px;overflow:auto}.cat{width:100%;padding:13px 10px;margin:4px 0;border:0;border-radius:8px;background:#f0f1f3;text-align:left;font-weight:700;cursor:pointer}.cat.active{background:#111827;color:#fff}.main{padding:18px;overflow:auto}.title{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px}.product{background:#fff;border:1px solid #ddd;border-radius:12px;padding:14px;min-height:118px;cursor:pointer;display:flex;flex-direction:column}.product:hover{box-shadow:0 2px 10px #0002}.product-photo{width:100%;height:120px;object-fit:cover;border-radius:8px;margin-bottom:10px}.name{font-weight:800;font-size:16px}.meta{font-size:12px;color:#666;margin-top:7px}.price{font-size:20px;font-weight:800;margin-top:auto;padding-top:10px}.cart{background:#fff;border-left:1px solid #ddd;padding:18px}.cart h2{margin-top:0}.empty{color:#777;padding:30px 0;text-align:center}.badge{font-size:11px;background:#e8eefc;border-radius:20px;padding:4px 8px;margin-top:8px;display:inline-block;width:max-content}.note{font-size:12px;color:#666;margin-top:20px;border-top:1px solid #eee;padding-top:12px}@media(max-width:900px){.layout{grid-template-columns:150px 1fr}.cart{display:none}}
</style></head><body><div class="top"><b>BÉCHÉFAA-Caisse</b><span>Nouvelle caisse PostgreSQL</span><span class="status" id="status">Chargement…</span></div><div class="layout"><aside class="cats" id="cats"></aside><main class="main"><div class="title"><h2 id="title">Catalogue</h2><span id="count"></span></div><div class="grid" id="grid"></div></main><aside class="cart"><h2>Commande</h2><div class="empty">Panier volontairement désactivé<br>pendant la validation du catalogue.</div><div class="note">Source unique : catalog_admin_v2 / PostgreSQL.<br>Aucune donnée Wix/V1 embarquée.</div></aside></div>
<script>
let DATA=null, current=null; const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function render(){let items=DATA.items.filter(p=>!current||p.category===current);document.getElementById('title').textContent=current||'Tous les produits';document.getElementById('count').textContent=items.length+' produit(s)';document.getElementById('grid').innerHTML=items.map(p=>`<div class="product">${p.photo?`<img class="product-photo" src="${esc(p.photo)}" alt="${esc(p.name)}">`:''}<div class="name">${esc(p.name)}</div><div class="meta">${esc(p.category)}</div>${p.optionGroups?`<span class="badge">${p.optionGroups} groupe(s) d’options</span>`:''}<div class="price">${Number(p.price||0).toFixed(2).replace('.',',')} €</div></div>`).join('');document.querySelectorAll('.cat').forEach(b=>b.classList.toggle('active',b.dataset.cat===(current||'')))}
fetch('/api/catalog/summary').then(r=>r.json()).then(d=>{DATA=d;document.getElementById('status').textContent=d.products+' produits • PostgreSQL';let cats=['',...d.categoryNames];document.getElementById('cats').innerHTML=cats.map(c=>`<button class="cat" data-cat="${esc(c)}">${esc(c||'Tous les produits')}</button>`).join('');document.getElementById('cats').onclick=e=>{let b=e.target.closest('.cat');if(!b)return;current=b.dataset.cat||null;render()};render()}).catch(e=>{document.getElementById('status').textContent='Erreur catalogue';document.getElementById('grid').innerHTML='<p>Impossible de charger le catalogue.</p>'});
</script></body></html>'''
    return Response(html, content_type="text/html; charset=utf-8")


@app.get("/")
def root():
    return "BÉCHÉFAA-Caisse clean backend", 200, {"Content-Type": "text/plain; charset=utf-8"}
