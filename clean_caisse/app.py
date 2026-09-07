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
                    (order_id, order_num, "Client comptoir", "CAISSE", "À ENCAISSER", "Enregistrée", total, now, now),
                )
                for line in normalized:
                    conn.execute(
                        """INSERT INTO caisse_order_items
                           (order_id, line_id, product_id, name, qty, unit_price, options_json, options_text, prepared, position)
                           VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, FALSE, %s)""",
                        (order_id, line["line_id"], line["product_id"], line["name"], line["qty"], line["unit_price"],
                         json.dumps(line["options"], ensure_ascii=False), line["options_text"], line["position"]),
                    )
    except Exception as exc:
        return jsonify({"ok": False, "error": "Enregistrement PostgreSQL impossible", "detail": str(exc)}), 500

    return jsonify({"ok": True, "id": order_id, "num": order_num, "total": float(total), "status": "Enregistrée"}), 201


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
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#f4f5f7;color:#17191c}.top{height:64px;background:#111827;color:white;display:flex;align-items:center;padding:0 22px;gap:20px}.top b{font-size:22px}.status{margin-left:auto;font-size:13px}.layout{display:grid;grid-template-columns:190px 1fr 370px;height:calc(100vh - 64px)}.cats{background:#fff;border-right:1px solid #ddd;padding:12px;overflow:auto}.cat{width:100%;padding:13px 10px;margin:4px 0;border:0;border-radius:8px;background:#f0f1f3;text-align:left;font-weight:700;cursor:pointer}.cat.active{background:#111827;color:#fff}.main{padding:18px;overflow:auto}.title{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px}.product{background:#fff;border:1px solid #ddd;border-radius:12px;padding:14px;min-height:118px;cursor:pointer;display:flex;flex-direction:column}.product:hover{box-shadow:0 2px 10px #0002}.product-photo{width:100%;height:120px;object-fit:cover;border-radius:8px;margin-bottom:10px}.name{font-weight:800;font-size:16px}.meta{font-size:12px;color:#666;margin-top:7px}.price{font-size:20px;font-weight:800;margin-top:auto;padding-top:10px}.cart{background:#fff;border-left:1px solid #ddd;padding:18px;overflow:auto}.cart h2{margin:0 0 10px}.empty{color:#777;padding:24px 0;text-align:center}.badge{font-size:11px;background:#e8eefc;border-radius:20px;padding:4px 8px;margin-top:8px;display:inline-block;width:max-content}.note{font-size:12px;color:#666;margin-top:20px;border-top:1px solid #eee;padding-top:12px}.opt-group{border-top:1px solid #eee;padding-top:12px;margin-top:12px}.opt-head{display:flex;justify-content:space-between;gap:8px;align-items:center;margin-bottom:7px}.opt-head b{display:block}.rule{font-size:11px;color:#777}.opt-value{width:100%;font-size:13px;background:#f4f5f7;border:1px solid #e3e5e8;border-radius:8px;padding:9px;margin:5px 0;cursor:pointer;text-align:left;display:flex;justify-content:space-between;gap:8px}.opt-value:hover{background:#eceff3}.opt-value.selected{background:#111827;color:#fff;border-color:#111827}.selection-summary{background:#f7f8fa;border:1px solid #e5e7eb;border-radius:10px;padding:10px;margin-bottom:10px;font-size:13px}.selection-summary b{display:block;margin-bottom:5px}.selection-price{font-size:18px;font-weight:800;margin-top:8px}.action{width:100%;border:0;border-radius:9px;padding:12px 10px;font-weight:800;cursor:pointer}.add{background:#111827;color:white;margin-top:12px}.save{background:#14804a;color:white;margin-top:12px}.order-box{border-top:2px solid #111827;margin-top:18px;padding-top:16px}.order-line{border-bottom:1px solid #eee;padding:9px 0}.order-line-head{display:flex;justify-content:space-between;gap:8px;font-weight:700}.order-opts{font-size:11px;color:#666;margin-top:4px}.remove{border:0;background:transparent;color:#b42318;cursor:pointer;padding:3px 0;font-size:12px}.order-total{display:flex;justify-content:space-between;font-size:20px;font-weight:800;margin-top:12px}.success{background:#e8f7ee;border:1px solid #b9e2c8;border-radius:9px;padding:10px;margin:10px 0;font-size:13px}.error{background:#fff0ee;border:1px solid #f3c0ba;border-radius:9px;padding:10px;margin:10px 0;font-size:13px;color:#9d261d}@media(max-width:900px){.layout{grid-template-columns:150px 1fr}.cart{display:none}}
</style></head><body><div class="top"><b>BÉCHÉFAA-Caisse</b><span>Nouvelle caisse PostgreSQL</span><span class="status" id="status">Chargement…</span></div><div class="layout"><aside class="cats" id="cats"></aside><main class="main"><div class="title"><h2 id="title">Catalogue</h2><span id="count"></span></div><div class="grid" id="grid"></div></main><aside class="cart"><h2 id="side-title">Options produit</h2><div id="options"><div class="empty">Cliquez sur un produit pour sélectionner ses options.</div></div><div class="order-box"><h2>Commande</h2><div id="order-message"></div><div id="order"><div class="empty">Commande vide</div></div></div><div class="note">Étape 2 : l'enregistrement écrit uniquement dans <b>caisse_orders</b> et <b>caisse_order_items</b> PostgreSQL.</div></aside></div>
<script>
let DATA=null,current=null,currentProduct=null,currentGroups=[],selections={},ORDER=[];const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
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
function renderOrder(){let el=document.getElementById('order');if(!ORDER.length){el.innerHTML='<div class="empty">Commande vide</div>';return}let total=ORDER.reduce((s,l)=>s+Number(l.unit_price||0)*Number(l.qty||1),0);el.innerHTML=ORDER.map((l,i)=>`<div class="order-line"><div class="order-line-head"><span>${esc(l.name)}</span><span>${Number(l.unit_price).toFixed(2).replace('.',',')} €</span></div>${l.options.length?`<div class="order-opts">${esc(l.options.map(o=>o.name).join(' • '))}</div>`:''}<button class="remove" data-action="remove-line" data-index="${i}">Retirer</button></div>`).join('')+`<div class="order-total"><span>Total</span><span>${total.toFixed(2).replace('.',',')} €</span></div><button class="action save" data-action="save-order">Enregistrer la commande</button>`}
function saveOrder(){if(!ORDER.length)return;let btn=document.querySelector('[data-action="save-order"]');if(btn){btn.disabled=true;btn.textContent='Enregistrement…'}document.getElementById('order-message').innerHTML='';fetch('/api/orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items:ORDER})}).then(async r=>{let d=await r.json();if(!r.ok||!d.ok)throw new Error(d.detail||d.error||'Erreur');ORDER=[];renderOrder();document.getElementById('order-message').innerHTML=`<div class="success"><b>Commande #${esc(d.num)} enregistrée</b><br>Total ${Number(d.total||0).toFixed(2).replace('.',',')} € • ${esc(d.status)}</div>`}).catch(err=>{document.getElementById('order-message').innerHTML=`<div class="error"><b>Commande non enregistrée.</b><br>${esc(err.message)}</div>`;renderOrder()})}
function render(){let items=DATA.items.filter(p=>!current||p.category===current);document.getElementById('title').textContent=current||'Tous les produits';document.getElementById('count').textContent=items.length+' produit(s)';document.getElementById('grid').innerHTML=items.map(p=>`<div class="product" data-id="${esc(p.id)}" data-name="${esc(p.name)}">${p.photo?`<img class="product-photo" src="${esc(p.photo)}" alt="${esc(p.name)}">`:''}<div class="name">${esc(p.name)}</div><div class="meta">${esc(p.category)}</div>${p.optionGroups?`<span class="badge">${p.optionGroups} groupe(s) d’options</span>`:''}<div class="price">${Number(p.price||0).toFixed(2).replace('.',',')} €</div></div>`).join('');document.querySelectorAll('.cat').forEach(b=>b.classList.toggle('active',b.dataset.cat===(current||'')))}
fetch('/api/catalog/summary').then(r=>r.json()).then(d=>{DATA=d;document.getElementById('status').textContent=d.products+' produits • PostgreSQL';let cats=['',...d.categoryNames];document.getElementById('cats').innerHTML=cats.map(c=>`<button class="cat" data-cat="${esc(c)}">${esc(c||'Tous les produits')}</button>`).join('');document.getElementById('cats').onclick=e=>{let b=e.target.closest('.cat');if(!b)return;current=b.dataset.cat||null;render()};document.getElementById('grid').onclick=e=>{let p=e.target.closest('.product');if(!p)return;showOptions(p.dataset.id,p.dataset.name)};document.querySelector('.cart').onclick=e=>{let b=e.target.closest('[data-action]');if(!b)return;let action=b.dataset.action;if(action==='add-current')addCurrent();else if(action==='remove-line'){ORDER.splice(Number(b.dataset.index),1);renderOrder()}else if(action==='save-order')saveOrder();else if(b.classList.contains('opt-value')){};let opt=e.target.closest('.opt-value');if(opt)toggleOption(Number(opt.dataset.gi),Number(opt.dataset.vi))};document.getElementById('options').onclick=e=>{let b=e.target.closest('.opt-value');if(!b)return;toggleOption(Number(b.dataset.gi),Number(b.dataset.vi))};render();renderOrder()}).catch(()=>{document.getElementById('status').textContent='Erreur catalogue';document.getElementById('grid').innerHTML='<p>Impossible de charger le catalogue.</p>'});
</script></body></html>'''
    return Response(html, content_type="text/html; charset=utf-8")


@app.get("/")
def root():
    return "BÉCHÉFAA-Caisse clean backend", 200, {"Content-Type": "text/plain; charset=utf-8"}
