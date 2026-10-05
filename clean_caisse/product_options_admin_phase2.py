"""Phase 2.3 — administration des options existantes de catalog_admin_v2.
Les écritures nom/prix sont isolées dans option_price_admin_phase23.py.
"""
import json
import time
from decimal import Decimal, InvalidOperation
from flask import Response, jsonify, request


def register_product_options_admin_phase2(app, db):
    LABELS = {'pain':'Pain','poulet':'Poulet','sauces':'Sauces','tender':'Type de tender','cuisson':'Cuisson','viandes':'Viandes','boissons':'Boissons','garnitures':'Garnitures','saucesSupp':'Sauces supplémentaires','supplements':'Suppléments','accompagnements':'Accompagnements'}
    def load_catalog():
        with db() as conn: row=conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1").fetchone()
        if not row: raise RuntimeError('Catalogue catalog_admin_v2 introuvable')
        data=json.loads(row['data_json'] or '{}'); return data if isinstance(data,dict) else {}
    def item(v,source_index):
        if isinstance(v,(list,tuple)): name=str(v[0] if v else '').strip(); price=v[1] if len(v)>1 else 0
        elif isinstance(v,dict): name=str(v.get('name') or v.get('label') or v.get('title') or '').strip(); price=v.get('price',0)
        else: name=str(v or '').strip(); price=0
        try: price=float(Decimal(str(price or 0)).quantize(Decimal('0.01')))
        except (InvalidOperation,ValueError,TypeError): price=0.0
        return {'name':name,'price':price,'index':source_index}
    @app.get('/api/admin/option-lists')
    def option_lists():
        try:
            data=load_catalog(); lists=data.get('optionLists') or {}; defs=data.get('optionListDefs') or {}; orders=data.get('optionListOrders') or {}; modes=data.get('optionListOrderModes') or {}; groups=[]
            for key,vals in lists.items():
                if not isinstance(vals,list): continue
                meta=defs.get(key) if isinstance(defs.get(key),dict) else {}; order=orders.get(key); ordered=[]; used=set()
                if isinstance(order,list):
                    for x in order:
                        try:i=int(x)
                        except (TypeError,ValueError):continue
                        if 0<=i<len(vals) and i not in used:ordered.append((i,vals[i]));used.add(i)
                ordered.extend((i,v) for i,v in enumerate(vals) if i not in used); options=[item(v,i) for i,v in ordered]; options=[o for o in options if o['name']]
                groups.append({'key':key,'name':str(meta.get('title') or meta.get('label') or LABELS.get(key) or key),'required':bool(meta.get('required',False)),'max':meta.get('max',0) or 0,'priceMode':meta.get('priceMode','extra'),'orderMode':modes.get(key,'source'),'options':options})
            return jsonify({'ok':True,'count':len(groups),'groups':groups,'source':'catalog_admin_v2.optionLists'})
        except Exception as exc:return jsonify({'ok':False,'error':'Groupes indisponibles','detail':str(exc)}),500
    @app.get('/api/admin/options-products-list')
    def options_products_list():
        try:
            data=load_catalog(); products=[{'id':p.get('id'),'name':p.get('name') or 'Sans nom','category':p.get('category') or p.get('cat') or ''} for p in data.get('products') or [] if isinstance(p,dict)]; return jsonify({'ok':True,'products':products})
        except Exception as exc:return jsonify({'ok':False,'error':'Produits indisponibles','detail':str(exc)}),500
    @app.get('/api/admin/options-product/<product_id>')
    def options_product(product_id):
        try:
            data=load_catalog(); p=next((x for x in data.get('products') or [] if isinstance(x,dict) and str(x.get('id'))==str(product_id)),None)
            if not p:return jsonify({'ok':False,'error':'Produit introuvable'}),404
            return jsonify({'ok':True,'product':{'id':p.get('id'),'name':p.get('name')},'optionSelections':p.get('optionSelections') if isinstance(p.get('optionSelections'),dict) else {},'directOptions':p.get('options') if isinstance(p.get('options'),list) else []})
        except Exception as exc:return jsonify({'ok':False,'error':'Options produit indisponibles','detail':str(exc)}),500
    def _choice_pair(v):
        if isinstance(v,(list,tuple)):
            return str(v[0] if v else '').strip(), float(v[1] if len(v)>1 else 0)
        if isinstance(v,dict):
            return str(v.get('name') or v.get('label') or v.get('title') or '').strip(), float(v.get('price',0) or 0)
        return str(v or '').strip(), 0.0

    def _group_meta(data, product, key):
        central='central_'+key
        for g in product.get('options') or []:
            if isinstance(g,dict) and str(g.get('key') or '')==central:
                return {
                    'key':central,
                    'title':str(g.get('title') or g.get('name') or LABELS.get(key) or key),
                    'required':bool(g.get('required',False)),
                    'max':g.get('max',0) or 0,
                    'priceMode':g.get('priceMode','extra'),
                }
        defs=data.get('optionListDefs') or {}
        d=defs.get(key) if isinstance(defs,dict) and isinstance(defs.get(key),dict) else {}
        return {
            'key':central,
            'title':str(d.get('title') or d.get('label') or LABELS.get(key) or key),
            'required':bool(d.get('required',False)),
            'max':d.get('max',0) or 0,
            'priceMode':d.get('priceMode','extra'),
        }

    @app.get('/api/admin/simple-product-options/<product_id>')
    def simple_product_options_get(product_id):
        try:
            data=load_catalog()
            product=next((p for p in data.get('products') or [] if isinstance(p,dict) and str(p.get('id'))==str(product_id)),None)
            if not product:return jsonify({'ok':False,'error':'Produit introuvable'}),404
            lists=data.get('optionLists') or {}
            selections=product.get('optionSelections') if isinstance(product.get('optionSelections'),dict) else {}
            direct=product.get('options') if isinstance(product.get('options'),list) else []
            current_order=[]
            for g in direct:
                if isinstance(g,dict):
                    k=str(g.get('key') or '')
                    if k.startswith('central_'): current_order.append(k[8:])
            groups=[]
            known=set()
            for key,vals in lists.items():
                if not isinstance(vals,list):continue
                meta=_group_meta(data,product,key)
                selected=[]
                for x in selections.get(key) or []:
                    try:selected.append(int(x))
                    except (TypeError,ValueError):pass
                # Si une ancienne fiche n'a pas optionSelections mais possède déjà
                # un groupe matérialisé, on retrouve les choix par leur nom.
                if not selected:
                    dg=next((g for g in direct if isinstance(g,dict) and str(g.get('key') or '')=='central_'+key),None)
                    if isinstance(dg,dict) and isinstance(dg.get('choices'),list):
                        direct_names={_choice_pair(v)[0].casefold() for v in dg.get('choices') or [] if _choice_pair(v)[0]}
                        for i,v in enumerate(vals):
                            n,_=_choice_pair(v)
                            if n and n.casefold() in direct_names:selected.append(i)
                raw_options=[{'index':i,'name':_choice_pair(v)[0],'price':_choice_pair(v)[1]} for i,v in enumerate(vals) if _choice_pair(v)[0]]
                dg=next((g for g in direct if isinstance(g,dict) and str(g.get('key') or '')=='central_'+key),None)
                direct_order=[]
                if isinstance(dg,dict) and isinstance(dg.get('choices'),list):
                    name_to_index={str(_choice_pair(v)[0]).casefold():i for i,v in enumerate(vals) if _choice_pair(v)[0]}
                    for choice in dg.get('choices') or []:
                        n,_=_choice_pair(choice)
                        idx=name_to_index.get(str(n).casefold())
                        if idx is not None and idx not in direct_order:direct_order.append(idx)
                by_index={int(o['index']):o for o in raw_options}
                ordered_options=[by_index[i] for i in direct_order if i in by_index]
                used=set(direct_order)
                ordered_options.extend(o for o in raw_options if int(o['index']) not in used)
                groups.append({
                    'key':key,
                    'name':meta['title'],
                    'required':meta['required'],
                    'max':meta['max'],
                    'selected':selected,
                    'options':ordered_options,
                    'source':'central',
                })
                known.add(key)
            # Récupère aussi les groupes présents uniquement sur le produit
            # (ex. Cuisson sur certaines anciennes fiches).
            for dg in direct:
                if not isinstance(dg,dict):continue
                raw_key=str(dg.get('key') or '')
                if not raw_key.startswith('central_'):continue
                key=raw_key[8:]
                if not key or key in known:continue
                choices=dg.get('choices') if isinstance(dg.get('choices'),list) else []
                opts=[]
                for i,v in enumerate(choices):
                    n,p=_choice_pair(v)
                    if n:opts.append({'index':i,'name':n,'price':p})
                groups.append({
                    'key':key,
                    'name':str(dg.get('title') or dg.get('name') or LABELS.get(key) or key),
                    'required':bool(dg.get('required',False)),
                    'max':dg.get('max',0) or 0,
                    'selected':[o['index'] for o in opts],
                    'options':opts,
                    'source':'direct',
                })
                known.add(key)
            order=current_order+[g['key'] for g in groups if g['key'] not in current_order]
            groups.sort(key=lambda g: order.index(g['key']) if g['key'] in order else 9999)
            return jsonify({'ok':True,'product':{'id':product.get('id'),'name':product.get('name'),'category':product.get('category') or product.get('cat') or ''},'groups':groups,'order':order})
        except Exception as exc:return jsonify({'ok':False,'error':'Configuration options indisponible','detail':str(exc)}),500

    @app.post('/api/admin/simple-product-options/<product_id>')
    def simple_product_options_save(product_id):
        payload=request.get_json(silent=True) or {}
        groups_payload=payload.get('groups')
        if not isinstance(groups_payload,list):return jsonify({'ok':False,'error':'Configuration invalide'}),400
        try:
            with db() as conn:
                with conn.transaction():
                    row=conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1 FOR UPDATE").fetchone()
                    if not row:return jsonify({'ok':False,'error':'Catalogue introuvable'}),404
                    data=json.loads(row['data_json'] or '{}')
                    product=next((p for p in data.get('products') or [] if isinstance(p,dict) and str(p.get('id'))==str(product_id)),None)
                    if not product:return jsonify({'ok':False,'error':'Produit introuvable'}),404
                    lists=data.get('optionLists') or {}
                    old_direct=product.get('options') if isinstance(product.get('options'),list) else []
                    old_by_key={str(g.get('key') or '')[8:]:g for g in old_direct if isinstance(g,dict) and str(g.get('key') or '').startswith('central_')}
                    selections=product.get('optionSelections') if isinstance(product.get('optionSelections'),dict) else {}
                    new_direct=[]
                    seen=set()
                    for cfg in groups_payload:
                        if not isinstance(cfg,dict):continue
                        key=str(cfg.get('key') or '').strip()
                        if not key or key in seen:continue
                        previous=old_by_key.get(key)
                        central_vals=lists.get(key) if isinstance(lists.get(key),list) else None
                        direct_vals=previous.get('choices') if isinstance(previous,dict) and isinstance(previous.get('choices'),list) else None
                        vals=central_vals if central_vals is not None else direct_vals
                        if not isinstance(vals,list):continue
                        seen.add(key)
                        selected=[]
                        for raw in cfg.get('selected') or []:
                            try:i=int(raw)
                            except (TypeError,ValueError):continue
                            if 0<=i<len(vals) and i not in selected:selected.append(i)
                        selections[key]=selected
                        if central_vals is not None and isinstance(cfg.get('optionOrder'),list):
                            wanted=[]
                            for raw in cfg.get('optionOrder') or []:
                                try:i=int(raw)
                                except (TypeError,ValueError):continue
                                if i in selected and 0<=i<len(central_vals) and i not in wanted:wanted.append(i)
                            wanted.extend(i for i in selected if i not in wanted)
                            selected=wanted
                            selections[key]=selected
                        if not selected:continue
                        meta=_group_meta(data,product,key)
                        if isinstance(previous,dict):
                            meta['required']=bool(previous.get('required',meta['required']))
                            meta['max']=previous.get('max',meta['max']) or 0
                            meta['priceMode']=previous.get('priceMode',meta['priceMode'])
                            meta['title']=str(previous.get('title') or previous.get('name') or meta['title'])
                        if cfg.get('max') is not None:
                            try:
                                max_choices=int(cfg.get('max'))
                            except (TypeError,ValueError):
                                max_choices=meta.get('max',0) or 0
                            if max_choices<0:max_choices=0
                            if max_choices>len(selected):max_choices=len(selected)
                            meta['max']=max_choices
                        materialized=[]
                        for i in selected:
                            name,price=_choice_pair(vals[i])
                            if name:materialized.append([name,price])
                        meta['choices']=materialized
                        new_direct.append(meta)
                    # Un groupe connu mais non renvoyé par l'interface est désactivé.
                    known_product_keys=set(lists.keys()) | set(old_by_key.keys())
                    for key in list(selections.keys()):
                        if key in known_product_keys and key not in seen: selections[key]=[]
                    product['optionSelections']=selections
                    # Preserve any non-central direct groups, then use the user-defined central order.
                    noncentral=[g for g in old_direct if not (isinstance(g,dict) and str(g.get('key') or '').startswith('central_'))]
                    product['options']=new_direct+noncentral
                    conn.execute("UPDATE catalog_admin_v2 SET data_json=%s::jsonb, updated_at=%s WHERE id=1",(json.dumps(data,ensure_ascii=False),int(time.time()*1000)))
            return jsonify({'ok':True,'product_id':product_id,'groups':len(new_direct)})
        except Exception as exc:return jsonify({'ok':False,'error':'Enregistrement impossible','detail':str(exc)}),500

    @app.post('/api/admin/simple-option-add')
    def simple_option_add():
        payload=request.get_json(silent=True) or {}
        key=str(payload.get('group') or '').strip()
        name=str(payload.get('name') or '').strip()
        try: price=float(Decimal(str(payload.get('price',0) or 0)).quantize(Decimal('0.01')))
        except (InvalidOperation,ValueError,TypeError):return jsonify({'ok':False,'error':'Prix invalide'}),400
        if not key or not name:return jsonify({'ok':False,'error':'Groupe et nom obligatoires'}),400
        if price<0:return jsonify({'ok':False,'error':'Prix invalide'}),400
        try:
            with db() as conn:
                with conn.transaction():
                    row=conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1 FOR UPDATE").fetchone()
                    if not row:return jsonify({'ok':False,'error':'Catalogue introuvable'}),404
                    data=json.loads(row['data_json'] or '{}');lists=data.get('optionLists') or {}
                    vals=lists.get(key)
                    if not isinstance(vals,list):return jsonify({'ok':False,'error':'Groupe introuvable'}),404
                    for v in vals:
                        existing,_=_choice_pair(v)
                        if existing.casefold()==name.casefold():return jsonify({'ok':False,'error':'Cette option existe déjà'}),409
                    vals.append([name,price])
                    idx=len(vals)-1
                    orders=data.get('optionListOrders')
                    if isinstance(orders,dict) and isinstance(orders.get(key),list):orders[key].append(idx)
                    conn.execute("UPDATE catalog_admin_v2 SET data_json=%s::jsonb, updated_at=%s WHERE id=1",(json.dumps(data,ensure_ascii=False),int(time.time()*1000)))
            return jsonify({'ok':True,'group':key,'index':idx,'name':name,'price':price})
        except Exception as exc:return jsonify({'ok':False,'error':'Ajout impossible','detail':str(exc)}),500

    @app.get('/administration/options-produits')
    def options_admin_page():
        return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Options par produit</title><style>
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#f4f5f7;color:#17191c}.top{background:#111;color:#fff;padding:15px 22px}.wrap{max-width:1180px;margin:auto;padding:24px 18px 42px}h1{margin:0 0 6px;font-size:30px}.intro{margin:0 0 18px;color:#667085}.card{background:#fff;border:1px solid #e1e4e8;border-radius:14px;padding:18px;margin:12px 0;box-shadow:0 2px 8px #00000008}.row{display:flex;gap:10px;align-items:end;flex-wrap:wrap}.field{flex:1;min-width:220px}.category-buttons{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}.catbtn{border:1px solid #cfd4dc;background:#fff;color:#20242a;border-radius:10px;padding:10px 14px;font-weight:900;cursor:pointer}.catbtn:hover{border-color:#d6a62d;background:#fffaf0}.catbtn.active{background:#111;color:#fff;border-color:#111}label{display:block;font-weight:800;font-size:13px;margin:0 0 6px}select,input{width:100%;padding:11px;border:1px solid #cfd4dc;border-radius:9px;background:#fff;font-size:15px}.status{margin:10px 0}.ok{background:#eaf7ee;color:#146c3a;border:1px solid #cdebd8;padding:10px 12px;border-radius:9px}.bad{background:#fff0ee;color:#9d261d;border:1px solid #ffd5cf;padding:10px 12px;border-radius:9px}.groups{display:flex;flex-direction:column;gap:12px}.group{border:1px solid #dfe3e8;border-radius:12px;background:#fff;overflow:hidden}.grouphead{display:flex;align-items:center;gap:10px;padding:12px 14px;background:#fafafa;border-bottom:1px solid #e8eaed}.grouphead b{font-size:17px;flex:1}.move{display:flex;gap:6px}.move button{width:38px;height:36px;border:1px solid #cfd4dc;background:#fff;border-radius:8px;font-size:18px;font-weight:900;cursor:pointer}.options{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;padding:12px}.choice{display:flex;align-items:center;gap:9px;border:1px solid #e3e6ea;border-radius:9px;padding:10px;background:#fff;cursor:pointer;min-height:48px}.choice input{width:20px;height:20px;flex:0 0 auto}.choice span{font-weight:700}.choice small{margin-left:auto;color:#8a6b1a;font-weight:800}.drag-handle{cursor:grab;font-size:18px;color:#7b8490;padding:2px 5px;user-select:none}.dragging{opacity:.45}.group-title{cursor:pointer}.group-title:after{content:' ✎';font-size:12px;color:#8a94a3;font-weight:700}.max-choice-wrap{display:flex;align-items:center;gap:6px;font-size:12px;font-weight:800;color:#667085}.max-choice-wrap input{width:58px;padding:6px 7px;border:1px solid #cfd4dc;border-radius:7px;font-size:14px;text-align:center}.choice.on{background:#fff8e5;border-color:#d9a62b}.savebar{position:sticky;bottom:10px;display:flex;justify-content:flex-end;margin-top:16px}.primary{border:0;border-radius:10px;padding:13px 20px;background:#111;color:#fff;font-weight:900;font-size:15px;cursor:pointer;box-shadow:0 5px 14px #0002;transition:background .18s ease,transform .12s ease,box-shadow .18s ease}.primary:active{transform:scale(.98)}.primary.saving{background:#6b7280!important;color:#fff!important}.primary.saved{background:#15803d!important;color:#fff!important;box-shadow:0 0 0 3px rgba(21,128,61,.16),0 5px 14px #0002}.gold{background:#d99a18;color:#111}.addgrid{display:grid;grid-template-columns:1fr 1.3fr 150px auto;gap:9px;align-items:end}.hint{font-size:13px;color:#667085;line-height:1.45}.advanced{margin-top:18px}.advanced summary{cursor:pointer;font-weight:800;color:#667085}.advanced iframe{width:100%;border:0;height:720px;margin-top:10px}.empty{padding:18px;color:#667085;text-align:center}@media(max-width:850px){.options{grid-template-columns:repeat(2,minmax(0,1fr))}.addgrid{grid-template-columns:1fr 1fr}.addgrid .primary{width:100%}}@media(max-width:560px){.options{grid-template-columns:1fr}.wrap{padding:18px 10px 30px}h1{font-size:25px}.addgrid{grid-template-columns:1fr}}
</style></head><body><div class="top"><b>BÉCHÉFAA • Options & suppléments</b></div><main class="wrap"><h1>Options par produit</h1><p class="intro">Choisissez un produit, cochez simplement les options proposées au client et classez les groupes avec ↑ / ↓.</p>
<div class="card"><label>1. Choisir une catégorie</label><div id="category-buttons" class="category-buttons"></div><div class="field" style="margin-top:14px"><label>2. Choisir un produit</label><select id="product" disabled><option value="">Choisissez d’abord une catégorie…</option></select></div><div id="status" class="status"></div></div>
<div class="card"><h2 style="margin-top:0">Ajouter une nouvelle option</h2><p class="hint">Exemple : groupe « Suppléments », nom « Double bacon », prix 3,00 €.</p><div class="addgrid"><div><label>Groupe</label><select id="add-group"></select></div><div><label>Nom</label><input id="add-name" placeholder="Double bacon"></div><div><label>Prix supplémentaire</label><input id="add-price" type="number" min="0" step="0.01" value="0.00"></div><button class="primary gold" id="add-option" type="button">Ajouter</button></div></div>
<div class="card"><h2 style="margin-top:0">Choix proposés au client</h2><div id="groups" class="groups"><div class="empty">Choisissez d’abord un produit.</div></div><div class="savebar"><button class="primary" id="save" type="button" disabled>Enregistrer les options et l’ordre</button></div></div>
<details class="advanced"><summary>Gestion avancée (règles, noms et prix)</summary><iframe src="/administration/options-ajout-test" title="Gestion avancée"></iframe></details>
</main><script>
const $=id=>document.getElementById(id),E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let products=[],groups=[],current='',currentCategory='';
function status(t,ok=true){$('status').innerHTML=t?'<div class="'+(ok?'ok':'bad')+'">'+E(t)+'</div>':''}
async function j(url,opts){const r=await fetch(url,opts);let d;try{d=await r.json()}catch(e){throw Error('Réponse serveur invalide')}if(!r.ok||!d.ok)throw Error(d.error||'Erreur');return d}
function categoryList(){const seen=[];products.forEach(p=>{const c=String(p.category||'').trim();if(c&&!seen.includes(c))seen.push(c)});return seen}
function renderCategories(){const cats=categoryList();$('category-buttons').innerHTML=cats.map(c=>'<button type="button" class="catbtn '+(c===currentCategory?'active':'')+'" data-cat="'+E(c)+'">'+E(c)+'</button>').join('')||'<span class="hint">Aucune catégorie disponible.</span>'}
function renderProductSelect(){const select=$('product');if(!currentCategory){select.disabled=true;select.innerHTML='<option value="">Choisissez d’abord une catégorie…</option>';return}const rows=products.filter(p=>String(p.category||'')===currentCategory);select.disabled=false;select.innerHTML='<option value="">Choisir un produit de '+E(currentCategory)+'…</option>'+rows.map(p=>'<option value="'+E(p.id)+'">'+E(p.name)+'</option>').join('')}
async function loadProducts(){const d=await j('/api/admin/options-products-list?t='+Date.now());products=d.products||[];renderCategories();renderProductSelect()}
function render(){if(!groups.length){$('groups').innerHTML='<div class="empty">Aucun groupe d’options disponible.</div>';return}$('groups').innerHTML=groups.map((g,gi)=>'<section class="group" draggable="true" data-group-drag="'+gi+'" data-key="'+E(g.key)+'"><div class="grouphead"><span class="drag-handle" title="Glisser pour déplacer">☰</span><b class="group-title" data-group-rename="'+gi+'" title="Cliquer pour renommer le titre">'+E(g.name)+'</b><label class="max-choice-wrap">Max <input type="number" min="0" max="'+Math.max(0,g.selected.length)+'" value="'+Number(g.max||0)+'" data-group-max="'+gi+'" title="0 = sans limite"></label><span class="hint">'+g.selected.length+' sélectionnée(s)</span></div><div class="options">'+g.options.map((o,oi)=>{const on=g.selected.includes(Number(o.index));return '<div class="choice '+(on?'on':'')+'" draggable="true" data-choice-drag="'+gi+':'+oi+'"><span class="drag-handle" title="Glisser pour déplacer">⋮⋮</span><input type="checkbox" data-gi="'+gi+'" data-index="'+Number(o.index)+'" '+(on?'checked':'')+'><span>'+E(o.name)+'</span>'+(Number(o.price||0)?'<small>+'+Number(o.price).toFixed(2).replace('.',',')+' €</small>':'')+'</div>'}).join('')+'</div></section>').join('')}
async function loadProduct(){current=$('product').value;if(!current){groups=[];$('save').disabled=true;render();return}status('Chargement…');try{const d=await j('/api/admin/simple-product-options/'+encodeURIComponent(current)+'?t='+Date.now());groups=d.groups||[];$('save').disabled=false;render();status('Configuration de « '+d.product.name+' » chargée.')}catch(e){status(e.message,false)}}
$('category-buttons').addEventListener('click',e=>{const b=e.target.closest('[data-cat]');if(!b)return;currentCategory=b.dataset.cat||'';current='';groups=[];$('save').disabled=true;renderCategories();renderProductSelect();render();status('Catégorie « '+currentCategory+' » sélectionnée. Choisissez maintenant un produit.')});
$('product').onchange=loadProduct;
$('groups').addEventListener('change',e=>{
 const m=e.target.closest('input[data-group-max]');
 if(m){const gi=Number(m.dataset.groupMax),g=groups[gi];if(!g)return;let v=parseInt(m.value||'0',10);if(!Number.isFinite(v)||v<0)v=0;if(v>g.selected.length)v=g.selected.length;g.max=v;m.value=String(v);return}
 const cb=e.target.closest('input[type=checkbox][data-gi]');
 if(!cb)return;
 const g=groups[Number(cb.dataset.gi)],idx=Number(cb.dataset.index);
 if(cb.checked&&!g.selected.includes(idx))g.selected.push(idx);
 if(!cb.checked)g.selected=g.selected.filter(x=>Number(x)!==idx);
 if(Number(g.max||0)>g.selected.length)g.max=g.selected.length;
 render();
});
$('groups').addEventListener('click',async e=>{
 const title=e.target.closest('[data-group-rename]');
 if(!title)return;
 const gi=Number(title.dataset.groupRename),g=groups[gi];
 if(!g||!current)return;
 const val=prompt('Nouveau titre du groupe :',g.name);
 if(val===null)return;
 const name=String(val||'').trim();
 if(!name||name===g.name)return;
 status('Renommage…');
 try{
   await j('/api/admin/product-group-rename-phase25',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({productId:current,groupKey:'central_'+g.key,newTitle:name})});
   g.name=name;render();status('Titre renommé « '+name+' ».');
 }catch(err){status(err.message,false)}
});
let dragData=null;
$('groups').addEventListener('dragstart',e=>{
 if(e.target.closest('input')){e.preventDefault();return}
 const choice=e.target.closest('[data-choice-drag]');
 if(choice){const [gi,oi]=choice.dataset.choiceDrag.split(':').map(Number);dragData={type:'choice',gi,oi};choice.classList.add('dragging');e.stopPropagation();return}
 const group=e.target.closest('[data-group-drag]');
 if(group){dragData={type:'group',gi:Number(group.dataset.groupDrag)};group.classList.add('dragging')}
});
$('groups').addEventListener('dragend',e=>{document.querySelectorAll('.dragging').forEach(x=>x.classList.remove('dragging'));dragData=null});
$('groups').addEventListener('dragover',e=>{if(dragData)e.preventDefault()});
$('groups').addEventListener('drop',e=>{
 if(!dragData)return;e.preventDefault();
 if(dragData.type==='group'){
   const target=e.target.closest('[data-group-drag]');if(!target)return;
   const to=Number(target.dataset.groupDrag),from=dragData.gi;if(from===to)return;
   const moved=groups.splice(from,1)[0];groups.splice(to,0,moved);render();return;
 }
 const target=e.target.closest('[data-choice-drag]');if(!target)return;
 const [tgi,toi]=target.dataset.choiceDrag.split(':').map(Number);
 if(tgi!==dragData.gi)return;
 const g=groups[tgi],from=dragData.oi;if(!g||from===toi)return;
 const moved=g.options.splice(from,1)[0];g.options.splice(toi,0,moved);render();
});
$('save').onclick=async()=>{if(!current)return;const btn=$('save'),old=btn.textContent;btn.disabled=true;btn.classList.remove('saved');btn.classList.add('saving');btn.textContent='Enregistrement…';status('Enregistrement…');try{await j('/api/admin/simple-product-options/'+encodeURIComponent(current),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({groups:groups.map(g=>({key:g.key,selected:g.selected,max:Number(g.max||0),optionOrder:(g.options||[]).map(o=>Number(o.index))}))})});status('Options et ordre enregistrés.');btn.classList.remove('saving');btn.classList.add('saved');btn.textContent='Enregistré ✓';await loadProduct();setTimeout(()=>{btn.classList.remove('saved');btn.textContent=old},1600)}catch(e){btn.classList.remove('saving','saved');btn.textContent=old;status(e.message,false)}finally{btn.disabled=false}};
async function loadAddGroups(){try{const d=await j('/api/admin/option-lists?t='+Date.now());$('add-group').innerHTML=(d.groups||[]).map(g=>'<option value="'+E(g.key)+'">'+E(g.name)+'</option>').join('')}catch(e){status(e.message,false)}}
$('add-option').onclick=async()=>{const group=$('add-group').value,name=$('add-name').value.trim(),price=$('add-price').value;if(!group||!name)return status('Choisissez un groupe et saisissez un nom.',false);$('add-option').disabled=true;try{await j('/api/admin/simple-option-add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({group,name,price})});$('add-name').value='';$('add-price').value='0.00';status('Option « '+name+' » ajoutée. Vous pouvez maintenant la cocher sur le produit.');if(current)await loadProduct()}catch(e){status(e.message,false)}finally{$('add-option').disabled=false}};
(async()=>{try{await Promise.all([loadProducts(),loadAddGroups()]);status('Choisissez une catégorie, puis un produit à configurer.')}catch(e){status(e.message,false)}})();
</script></body></html>''',content_type='text/html; charset=utf-8')
