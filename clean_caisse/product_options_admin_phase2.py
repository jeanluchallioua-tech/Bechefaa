"""Phase 2.3 — administration propre des options produits.

Lit les options déjà présentes dans catalog_admin_v2 sans les recréer.
- Format canonique : products[].options
- Compatibilité lecture : products[].optionSelections
- L'enregistrement écrit uniquement products[].options et conserve les données historiques.
Aucun Wix / V1 / localStorage.
"""
import json
import time
from decimal import Decimal, InvalidOperation

from flask import Response, jsonify, request


def register_product_options_admin_phase2(app, db):
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
            (
                p
                for p in data.get("products") or []
                if isinstance(p, dict) and str(p.get("id") or "") == str(product_id)
            ),
            None,
        )

    def legacy_option_item(value):
        """Normalise une option historique pour affichage sans modifier la base."""
        if isinstance(value, dict):
            name = str(
                value.get("name")
                or value.get("label")
                or value.get("title")
                or value.get("value")
                or value.get("id")
                or ""
            ).strip()
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

    def groups_for_admin(product):
        """Retourne d'abord le format moderne, sinon les groupes historiques existants."""
        direct = product.get("options")
        if isinstance(direct, list) and direct:
            return direct, "options"

        selections = product.get("optionSelections")
        if not isinstance(selections, dict):
            return [], "none"

        rules = product.get("optionRules") if isinstance(product.get("optionRules"), dict) else {}
        groups = []
        for group_name, values in selections.items():
            if not isinstance(values, list) or not values:
                continue
            rule = rules.get(group_name) if isinstance(rules.get(group_name), dict) else {}
            required = bool(rule.get("required", False))
            raw_max = rule.get("max", rule.get("maxChoices", rule.get("maximum", 0)))
            try:
                max_choices = max(0, int(raw_max or 0))
            except (ValueError, TypeError):
                max_choices = 0
            items = [legacy_option_item(v) for v in values]
            items = [v for v in items if v["name"]]
            if items:
                if max_choices > len(items):
                    max_choices = len(items)
                groups.append(
                    {
                        "name": str(group_name).strip(),
                        "required": required,
                        "max": max_choices,
                        "options": items,
                    }
                )
        return groups, "optionSelections"

    def clean_options(payload):
        raw_groups = payload.get("groups")
        if not isinstance(raw_groups, list):
            return None, "Liste des groupes invalide"
        groups = []
        for raw_group in raw_groups:
            if not isinstance(raw_group, dict):
                return None, "Groupe d’options invalide"
            name = str(raw_group.get("name") or "").strip()
            if not name:
                return None, "Nom du groupe obligatoire"
            required = bool(raw_group.get("required", False))
            try:
                max_choices = int(raw_group.get("max", 0) or 0)
            except (ValueError, TypeError):
                return None, "Nombre maximum de choix invalide"
            if max_choices < 0:
                return None, "Nombre maximum de choix invalide"
            raw_items = raw_group.get("options")
            if not isinstance(raw_items, list) or not raw_items:
                return None, f"Ajoutez au moins une option dans « {name} »"
            items = []
            seen = set()
            for raw_item in raw_items:
                if not isinstance(raw_item, dict):
                    return None, f"Option invalide dans « {name} »"
                item_name = str(raw_item.get("name") or "").strip()
                if not item_name:
                    return None, f"Nom d’option obligatoire dans « {name} »"
                key = item_name.casefold()
                if key in seen:
                    return None, f"Option en double dans « {name} »"
                seen.add(key)
                try:
                    price = Decimal(str(raw_item.get("price", 0) or 0)).quantize(Decimal("0.01"))
                except (InvalidOperation, ValueError, TypeError):
                    return None, f"Prix invalide pour « {item_name} »"
                if price < 0:
                    return None, f"Prix invalide pour « {item_name} »"
                items.append({"name": item_name, "price": float(price)})
            if max_choices > len(items):
                max_choices = len(items)
            groups.append(
                {
                    "name": name,
                    "required": required,
                    "max": max_choices,
                    "options": items,
                }
            )
        return groups, None

    @app.get("/api/admin/products/<product_id>/options")
    def admin_get_product_options(product_id):
        try:
            with db() as conn:
                data = load(conn)
            product = find_product(data, product_id)
            if not product:
                return jsonify({"ok": False, "error": "Produit introuvable"}), 404
            groups, source_format = groups_for_admin(product)
            return jsonify(
                {
                    "ok": True,
                    "product": {
                        "id": product.get("id"),
                        "name": product.get("name"),
                        "price": product.get("price", 0),
                    },
                    "groups": groups,
                    "sourceFormat": source_format,
                }
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": "Options indisponibles", "detail": str(exc)}), 500

    @app.put("/api/admin/products/<product_id>/options")
    def admin_update_product_options(product_id):
        groups, error = clean_options(request.get_json(silent=True) or {})
        if error:
            return jsonify({"ok": False, "error": error}), 400
        try:
            with db() as conn:
                data = load(conn)
                product = find_product(data, product_id)
                if not product:
                    return jsonify({"ok": False, "error": "Produit introuvable"}), 404
                # Écrit le format propre utilisé par la nouvelle caisse.
                # Ne supprime PAS optionSelections : aucune donnée historique n'est détruite.
                product["options"] = groups
                save(conn, data)
            return jsonify({"ok": True, "product_id": product_id, "groups": groups})
        except Exception as exc:
            return jsonify({"ok": False, "error": "Enregistrement des options impossible", "detail": str(exc)}), 500

    @app.get("/administration/options-produits")
    def page_product_options():
        return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Options produits</title><style>*{box-sizing:border-box}body{margin:0;font-family:Arial;background:#f4f5f7;color:#17191c}.top{background:#111827;color:#fff;padding:14px 22px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}.top a{color:#fff;text-decoration:none;background:#263244;padding:9px 12px;border-radius:8px;font-weight:700}.wrap{max-width:1000px;margin:auto;padding:24px}.card{background:#fff;border-radius:14px;padding:20px;margin-bottom:18px}select,input{padding:11px;border:1px solid #ccd1d8;border-radius:9px;font-size:15px}.wide{width:100%}button{border:0;border-radius:9px;padding:10px 13px;background:#14804a;color:#fff;font-weight:800;cursor:pointer}.secondary{background:#344054}.danger{background:#9d261d}.group{border:1px solid #d9dde3;border-radius:12px;padding:14px;margin:12px 0}.ghead{display:grid;grid-template-columns:1fr 120px 130px auto;gap:8px;align-items:center}.opt{display:grid;grid-template-columns:1fr 140px auto;gap:8px;align-items:center;margin-top:8px}.check{display:flex;gap:6px;align-items:center;font-size:13px;font-weight:700}.check input{width:auto}.msg{margin:12px 0;padding:11px;border-radius:8px}.ok{background:#e8f7ee}.err{background:#fff0ee;color:#9d261d}.hint{color:#667085;font-size:13px}@media(max-width:700px){.ghead,.opt{grid-template-columns:1fr}.ghead button,.opt button{width:100%}}</style></head><body><div class="top"><b>BÉCHÉFAA • Administration</b><a href="/administration/produits">Produits</a><a href="/pos">Caisse</a></div><div class="wrap"><h1>Options et suppléments</h1><p class="hint">Les groupes et options déjà présents dans catalog_admin_v2 sont chargés automatiquement.</p><div id="msg"></div><div class="card"><label><b>Produit</b></label><select id="product" class="wide"></select></div><div class="card"><div id="groups"></div><button id="add-group" type="button">+ Ajouter un groupe</button></div><div class="card"><button id="save" type="button">Enregistrer les options</button></div></div><script>const $=i=>document.getElementById(i);let groups=[];function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function message(t,ok){$('msg').innerHTML='<div class="msg '+(ok?'ok':'err')+'">'+esc(t)+'</div>'}function readForm(){let out=[];document.querySelectorAll('.group').forEach(g=>{let opts=[];g.querySelectorAll('.opt').forEach(o=>opts.push({name:o.querySelector('.oname').value,price:o.querySelector('.oprice').value}));out.push({name:g.querySelector('.gname').value,required:g.querySelector('.grequired').checked,max:g.querySelector('.gmax').value,options:opts})});return out}function render(){let root=$('groups');root.innerHTML=groups.map((g,gi)=>'<div class="group" data-gi="'+gi+'"><div class="ghead"><input class="gname" placeholder="Nom du groupe" value="'+esc(g.name||'')+'"><input class="gmax" type="number" min="0" value="'+Number(g.max||0)+'" title="0 = sans limite"><label class="check"><input class="grequired" type="checkbox" '+(g.required?'checked':'')+'> Obligatoire</label><button type="button" class="danger del-group">Supprimer groupe</button></div><div class="opts">'+(g.options||[]).map((o,oi)=>'<div class="opt" data-oi="'+oi+'"><input class="oname" placeholder="Nom de l’option" value="'+esc(o.name||'')+'"><input class="oprice" type="number" min="0" step="0.01" value="'+Number(o.price||0).toFixed(2)+'"><button type="button" class="danger del-opt">Supprimer</button></div>').join('')+'</div><button type="button" class="secondary add-opt" style="margin-top:10px">+ Ajouter une option</button></div>').join('');root.querySelectorAll('.group').forEach(el=>{let gi=Number(el.dataset.gi);el.querySelector('.del-group').onclick=()=>{groups=readForm();groups.splice(gi,1);render()};el.querySelector('.add-opt').onclick=()=>{groups=readForm();groups[gi].options.push({name:'',price:0});render()};el.querySelectorAll('.opt').forEach(opt=>{let oi=Number(opt.dataset.oi);opt.querySelector('.del-opt').onclick=()=>{groups=readForm();groups[gi].options.splice(oi,1);render()}})})}async function loadProducts(){let r=await fetch('/api/admin/products',{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Produits indisponibles');$('product').innerHTML=(d.products||[]).map(p=>'<option value="'+esc(String(p.id||''))+'">'+esc(p.name||'')+'</option>').join('');if($('product').value)await loadOptions()}async function loadOptions(){let id=$('product').value;if(!id)return;let r=await fetch('/api/admin/products/'+encodeURIComponent(id)+'/options',{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Options indisponibles');groups=Array.isArray(d.groups)?d.groups:[];render();let suffix=d.sourceFormat==='optionSelections'?' • options existantes récupérées du catalogue':'';message('Options de « '+(d.product?.name||'produit')+' » chargées'+suffix+'.',true)}$('product').onchange=()=>loadOptions().catch(e=>message(e.message,false));$('add-group').onclick=()=>{groups=readForm();groups.push({name:'',required:false,max:1,options:[{name:'',price:0}]});render()};$('save').onclick=async()=>{let id=$('product').value;if(!id)return;let payload={groups:readForm()};try{let r=await fetch('/api/admin/products/'+encodeURIComponent(id)+'/options',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Erreur');groups=d.groups||[];render();message('Options enregistrées.',true)}catch(e){message(e.message,false)}};loadProducts().catch(e=>message(e.message,false));</script></body></html>''', content_type="text/html; charset=utf-8")
