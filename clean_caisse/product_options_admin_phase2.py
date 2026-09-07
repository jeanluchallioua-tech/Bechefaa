"""Phase 2.3 — administration des options produits depuis catalog_admin_v2.

Lecture fidèle de la structure existante :
- optionLists : définitions centrales des groupes/options
- optionListDefs : métadonnées des groupes custom
- optionListOrders / optionListOrderModes : ordre existant
- products[].optionSelections : sélections par produit
- products[].options : groupes matérialisés sur certains produits

Cette étape affiche les groupes/options existants sans les recréer.
Aucun Wix / V1 / localStorage.
"""
import json
import time
from decimal import Decimal, InvalidOperation

from flask import Response, jsonify, request


def register_product_options_admin_phase2(app, db):
    LABELS = {
        "pain": "Pain",
        "poulet": "Poulet",
        "sauces": "Sauces",
        "tender": "Type de tender",
        "cuisson": "Cuisson",
        "viandes": "Viandes",
        "boissons": "Boissons",
        "garnitures": "Garnitures",
        "saucesSupp": "Sauces supplémentaires",
        "supplements": "Suppléments",
        "accompagnements": "Accompagnements",
    }

    def load(conn):
        row = conn.execute(
            "SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1"
        ).fetchone()
        if not row:
            raise RuntimeError("Catalogue catalog_admin_v2 introuvable")
        data = json.loads(row["data_json"] or "{}")
        data.setdefault("products", [])
        return data

    def save(conn, data):
        conn.execute(
            "UPDATE catalog_admin_v2 SET data_json=%s::jsonb, updated_at=%s WHERE id=1",
            (json.dumps(data, ensure_ascii=False), int(time.time() * 1000)),
        )
        conn.commit()

    def find_product(data, product_id):
        return next(
            (p for p in data.get("products") or []
             if isinstance(p, dict) and str(p.get("id") or "") == str(product_id)),
            None,
        )

    def normal_item(value):
        if isinstance(value, dict):
            name = str(value.get("name") or value.get("label") or value.get("title") or value.get("value") or "").strip()
            price = value.get("price", value.get("extraPrice", value.get("supplement", 0)))
        elif isinstance(value, (list, tuple)):
            name = str(value[0] if value else "").strip()
            price = value[1] if len(value) > 1 else 0
        else:
            name = str(value if value is not None else "").strip()
            price = 0
        try:
            price = float(Decimal(str(price or 0)).quantize(Decimal("0.01")))
        except (InvalidOperation, ValueError, TypeError):
            price = 0.0
        return {"name": name, "price": price}

    def ordered_values(values, order):
        if not isinstance(values, list):
            return []
        if not isinstance(order, list) or not order:
            return values
        out, used = [], set()
        for raw in order:
            try:
                idx = int(raw)
            except (ValueError, TypeError):
                continue
            if 0 <= idx < len(values) and idx not in used:
                out.append(values[idx]); used.add(idx)
        out.extend(v for i, v in enumerate(values) if i not in used)
        return out

    def central_groups(data):
        lists = data.get("optionLists") if isinstance(data.get("optionLists"), dict) else {}
        defs = data.get("optionListDefs") if isinstance(data.get("optionListDefs"), dict) else {}
        orders = data.get("optionListOrders") if isinstance(data.get("optionListOrders"), dict) else {}
        modes = data.get("optionListOrderModes") if isinstance(data.get("optionListOrderModes"), dict) else {}
        groups = []
        for key, raw_values in lists.items():
            if not isinstance(raw_values, list):
                continue
            meta = defs.get(key) if isinstance(defs.get(key), dict) else {}
            label = str(meta.get("title") or meta.get("label") or LABELS.get(key) or key).strip()
            display_values = ordered_values(raw_values, orders.get(key))
            groups.append({
                "key": key,
                "name": label,
                "required": bool(meta.get("required", False)),
                "max": int(meta.get("max", 0) or 0) if str(meta.get("max", 0) or 0).lstrip("-").isdigit() else 0,
                "priceMode": str(meta.get("priceMode") or "extra"),
                "orderMode": str(modes.get(key) or "source"),
                "options": [normal_item(v) for v in display_values if normal_item(v)["name"]],
            })
        return groups

    @app.get("/api/admin/option-lists")
    def admin_option_lists():
        try:
            with db() as conn:
                data = load(conn)
            groups = central_groups(data)
            return jsonify({
                "ok": True,
                "source": "catalog_admin_v2.optionLists",
                "count": len(groups),
                "groups": groups,
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": "Groupes d’options indisponibles", "detail": str(exc)}), 500

    @app.get("/api/admin/products/<product_id>/options")
    def admin_get_product_options(product_id):
        try:
            with db() as conn:
                data = load(conn)
            product = find_product(data, product_id)
            if not product:
                return jsonify({"ok": False, "error": "Produit introuvable"}), 404
            selections = product.get("optionSelections") if isinstance(product.get("optionSelections"), dict) else {}
            direct = product.get("options") if isinstance(product.get("options"), list) else []
            return jsonify({
                "ok": True,
                "product": {"id": product.get("id"), "name": product.get("name"), "price": product.get("price", 0)},
                "optionSelections": selections,
                "directOptions": direct,
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": "Options indisponibles", "detail": str(exc)}), 500

    @app.get("/administration/options-produits")
    def page_product_options():
        return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Options produits</title><style>*{box-sizing:border-box}body{margin:0;font-family:Arial;background:#f4f5f7;color:#17191c}.top{background:#111827;color:#fff;padding:14px 22px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}.top a{color:#fff;text-decoration:none;background:#263244;padding:9px 12px;border-radius:8px;font-weight:700}.wrap{max-width:1050px;margin:auto;padding:24px}.card{background:#fff;border-radius:14px;padding:20px;margin-bottom:18px}.hint{color:#667085;font-size:13px}.group{border:1px solid #d9dde3;border-radius:12px;padding:14px;margin:12px 0}.ghead{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap}.gkey{font-size:12px;color:#667085}.opts{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;margin-top:12px}.opt{border:1px solid #e4e7ec;border-radius:9px;padding:10px;background:#fafafa;display:flex;justify-content:space-between;gap:10px}.price{font-weight:800}.msg{margin:12px 0;padding:11px;border-radius:8px}.ok{background:#e8f7ee}.err{background:#fff0ee;color:#9d261d}select{width:100%;padding:11px;border:1px solid #ccd1d8;border-radius:9px;font-size:15px}.badge{background:#eef2f6;padding:5px 8px;border-radius:999px;font-size:12px;font-weight:700}.selection{margin-top:10px;font-size:13px;color:#344054}</style></head><body><div class="top"><b>BÉCHÉFAA • Administration</b><a href="/administration/produits">Produits</a><a href="/pos">Caisse</a></div><div class="wrap"><h1>Options et suppléments</h1><p class="hint">Affichage direct des groupes déjà enregistrés dans catalog_admin_v2. Aucune ressaisie.</p><div id="msg"></div><div class="card"><h2>Groupes existants</h2><div id="central">Chargement…</div></div><div class="card"><h2>Affectation par produit</h2><select id="product"></select><div id="assignment" class="selection"></div></div></div><script>const $=i=>document.getElementById(i);const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));function money(v){return Number(v||0).toFixed(2).replace('.',',')+' €'}function msg(t,ok){$('msg').innerHTML='<div class="msg '+(ok?'ok':'err')+'">'+esc(t)+'</div>'}async function loadGroups(){let r=await fetch('/api/admin/option-lists',{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Groupes indisponibles');$('central').innerHTML=(d.groups||[]).map(g=>'<div class="group"><div class="ghead"><div><b>'+esc(g.name)+'</b><div class="gkey">'+esc(g.key)+'</div></div><div><span class="badge">'+(g.options||[]).length+' options</span></div></div><div class="opts">'+(g.options||[]).map(o=>'<div class="opt"><span>'+esc(o.name)+'</span><span class="price">'+(Number(o.price||0)?('+'+money(o.price)):'0,00 €')+'</span></div>').join('')+'</div></div>').join('');msg(d.count+' groupes existants chargés depuis le catalogue.',true)}async function loadProducts(){let r=await fetch('/api/admin/products',{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Produits indisponibles');$('product').innerHTML=(d.products||[]).map(p=>'<option value="'+esc(String(p.id||''))+'">'+esc(p.name||'')+'</option>').join('');if($('product').value)await loadAssignment()}async function loadAssignment(){let id=$('product').value;if(!id)return;let r=await fetch('/api/admin/products/'+encodeURIComponent(id)+'/options',{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Options produit indisponibles');let s=d.optionSelections||{},keys=Object.keys(s),active=keys.filter(k=>Array.isArray(s[k])&&s[k].length);$('assignment').innerHTML='<b>'+esc(d.product?.name||'Produit')+'</b><br>Groupes référencés : '+(keys.length?keys.map(esc).join(', '):'aucun')+'<br>Groupes avec choix enregistrés : '+(active.length?active.map(k=>esc(k)+' ('+s[k].length+')').join(', '):'aucun')+'<br>Groupes directs matérialisés : '+(Array.isArray(d.directOptions)?d.directOptions.length:0)}$('product').onchange=()=>loadAssignment().catch(e=>msg(e.message,false));Promise.all([loadGroups(),loadProducts()]).catch(e=>msg(e.message,false));</script></body></html>''', content_type="text/html; charset=utf-8")
