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
        photo = p.get("photo") or ""
        items.append({"id": p.get("id"), "name": name, "category": p.get("category") or p.get("cat") or "",
                      "price": p.get("price",0), "optionGroups": len(direct_options) if direct_options else len(active_selection_groups),
                      "hasDirectOptions": bool(direct_options), "photo": photo})
    return jsonify({"ok": True, "source": "catalog_admin_v2", "categories": len(categories), "categoryNames": categories,
                    "products": len(items), "items": items, "updatedAt": updated_at})


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
        groups = []
        if direct_options:
            groups = direct_options
        else:
            for group_name, values in selections.items():
                if isinstance(values, list) and values:
                    groups.append({"name": group_name, "options": values})
        return jsonify({"ok": True, "readOnly": True, "source": "catalog_admin_v2", "product": {"id": p.get("id"), "name": p.get("name"), "price": p.get("price", 0)}, "groups": groups, "updatedAt": updated_at})
    return jsonify({"ok": False, "error": "Produit introuvable", "updatedAt": updated_at}), 404


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
            return jsonify({"ok": True, "source": "catalog_admin_v2", "name": p.get("name"), "id": p.get("id"), "category": p.get("category") or p.get("cat"), "price": p.get("price"), "imageFields": interesting, "allKeys": sorted([str(k) for k in p.keys()]), "updatedAt": updated_at, "readOnly": True})
    return jsonify({"ok": False, "error": "Classic Burger introuvable", "updatedAt": updated_at}), 404


@app.get("/pos")
def pos():
    html = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BÉCHÉFAA-Caisse</title><style>
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#f4f5f7;color:#17191c}.top{height:64px;background:#111827;color:white;display:flex;align-items:center;padding:0 22px;gap:20px}.top b{font-size:22px}.status{margin-left:auto;font-size:13px}.layout{display:grid;grid-template-columns:190px 1fr 310px;height:calc(100vh - 64px)}.cats{background:#fff;border-right:1px solid #ddd;padding:12px;overflow:auto}.cat{width:100%;padding:13px 10px;margin:4px 0;border:0;border-radius:8px;background:#f0f1f3;text-align:left;font-weight:700;cursor:pointer}.cat.active{background:#111827;color:#fff}.main{padding:18px;overflow:auto}.title{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px}.product{background:#fff;border:1px solid #ddd;border-radius:12px;padding:14px;min-height:118px;cursor:pointer;display:flex;flex-direction:column}.product:hover{box-shadow:0 2px 10px #0002}.product-photo{width:100%;height:120px;object-fit:cover;border-radius:8px;margin-bottom:10px}.name{font-weight:800;font-size:16px}.meta{font-size:12px;color:#666;margin-top:7px}.price{font-size:20px;font-weight:800;margin-top:auto;padding-top:10px}.cart{background:#fff;border-left:1px solid #ddd;padding:18px;overflow:auto}.cart h2{margin-top:0}.empty{color:#777;padding:30px 0;text-align:center}.badge{font-size:11px;background:#e8eefc;border-radius:20px;padding:4px 8px;margin-top:8px;display:inline-block;width:max-content}.note{font-size:12px;color:#666;margin-top:20px;border-top:1px solid #eee;padding-top:12px}.opt-group{border-top:1px solid #eee;padding-top:10px;margin-top:10px}.opt-group b{display:block;margin-bottom:6px}.opt-value{font-size:13px;background:#f4f5f7;border-radius:7px;padding:7px;margin:4px 0;word-break:break-word}@media(max-width:900px){.layout{grid-template-columns:150px 1fr}.cart{display:none}}
</style></head><body><div class="top"><b>BÉCHÉFAA-Caisse</b><span>Nouvelle caisse PostgreSQL</span><span class="status" id="status">Chargement…</span></div><div class="layout"><aside class="cats" id="cats"></aside><main class="main"><div class="title"><h2 id="title">Catalogue</h2><span id="count"></span></div><div class="grid" id="grid"></div></main><aside class="cart"><h2 id="side-title">Options produit</h2><div id="options"><div class="empty">Cliquez sur un produit pour lire ses options.<br>Aucun ajout au panier.</div></div><div class="note">Lecture seule depuis catalog_admin_v2 / PostgreSQL.<br>Aucune commande n’est créée.</div></aside></div>
<script>
let DATA=null,current=null;const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function optionText(v){if(v===null||v===undefined)return'';if(Array.isArray(v)){let n=v[0]??'';let price=Number(v[1]||0);return esc(n)+(price?' (+'+price.toFixed(2).replace('.',',')+' €)':'')}if(typeof v==='string'||typeof v==='number')return esc(v);if(typeof v==='object'){let n=v.name||v.label||v.title||v.value||v.id||'';let price=Number(v.price||v.extraPrice||v.supplement||0);return esc(n)+(price?' (+'+price.toFixed(2).replace('.',',')+' €)':'')}return esc(String(v))}
function showOptions(id,name){document.getElementById('side-title').textContent='Options • '+name;document.getElementById('options').innerHTML='<div class="empty">Chargement…</div>';fetch('/api/catalog/product/'+encodeURIComponent(id)+'/options').then(r=>r.json()).then(d=>{if(!d.ok||!d.groups.length){document.getElementById('options').innerHTML='<div class="empty">Aucune option enregistrée pour ce produit.</div>';return}document.getElementById('options').innerHTML=d.groups.map((g,i)=>{let gn=(g&&typeof g==='object'?(g.name||g.label||g.title):'')||('Groupe '+(i+1));let vals=(g&&typeof g==='object'?(g.options||g.values||g.items||g.choices):null);if(!Array.isArray(vals))vals=Array.isArray(g)?g:[];return `<div class="opt-group"><b>${esc(gn)}</b>${vals.map(v=>`<div class="opt-value">${optionText(v)}</div>`).join('')||'<div class="opt-value">Données présentes — structure à valider</div>'}</div>`}).join('')}).catch(()=>{document.getElementById('options').innerHTML='<div class="empty">Impossible de lire les options.</div>'})}
function render(){let items=DATA.items.filter(p=>!current||p.category===current);document.getElementById('title').textContent=current||'Tous les produits';document.getElementById('count').textContent=items.length+' produit(s)';document.getElementById('grid').innerHTML=items.map(p=>`<div class="product" data-id="${esc(p.id)}" data-name="${esc(p.name)}">${p.photo?`<img class="product-photo" src="${esc(p.photo)}" alt="${esc(p.name)}">`:''}<div class="name">${esc(p.name)}</div><div class="meta">${esc(p.category)}</div>${p.optionGroups?`<span class="badge">${p.optionGroups} groupe(s) d’options</span>`:''}<div class="price">${Number(p.price||0).toFixed(2).replace('.',',')} €</div></div>`).join('');document.querySelectorAll('.cat').forEach(b=>b.classList.toggle('active',b.dataset.cat===(current||'')))}
fetch('/api/catalog/summary').then(r=>r.json()).then(d=>{DATA=d;document.getElementById('status').textContent=d.products+' produits • PostgreSQL';let cats=['',...d.categoryNames];document.getElementById('cats').innerHTML=cats.map(c=>`<button class="cat" data-cat="${esc(c)}">${esc(c||'Tous les produits')}</button>`).join('');document.getElementById('cats').onclick=e=>{let b=e.target.closest('.cat');if(!b)return;current=b.dataset.cat||null;render()};document.getElementById('grid').onclick=e=>{let p=e.target.closest('.product');if(!p)return;showOptions(p.dataset.id,p.dataset.name)};render()}).catch(()=>{document.getElementById('status').textContent='Erreur catalogue';document.getElementById('grid').innerHTML='<p>Impossible de charger le catalogue.</p>'});
</script></body></html>'''
    return Response(html, content_type="text/html; charset=utf-8")


@app.get("/")
def root():
    return "BÉCHÉFAA-Caisse clean backend", 200, {"Content-Type": "text/plain; charset=utf-8"}
