"""Phase 2.3 — affichage lecture seule des options existantes de catalog_admin_v2.
Aucune réécriture des données catalogue.
"""
import json
from decimal import Decimal, InvalidOperation
from flask import Response, jsonify


def register_product_options_admin_phase2(app, db):
    LABELS = {
        'pain':'Pain','poulet':'Poulet','sauces':'Sauces','tender':'Type de tender',
        'cuisson':'Cuisson','viandes':'Viandes','boissons':'Boissons','garnitures':'Garnitures',
        'saucesSupp':'Sauces supplémentaires','supplements':'Suppléments',
        'accompagnements':'Accompagnements'
    }

    def load_catalog():
        with db() as conn:
            row = conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1").fetchone()
        if not row:
            raise RuntimeError('Catalogue catalog_admin_v2 introuvable')
        data = json.loads(row['data_json'] or '{}')
        return data if isinstance(data, dict) else {}

    def item(v):
        if isinstance(v, (list, tuple)):
            name = str(v[0] if v else '').strip(); price = v[1] if len(v)>1 else 0
        elif isinstance(v, dict):
            name = str(v.get('name') or v.get('label') or v.get('title') or '').strip(); price=v.get('price',0)
        else:
            name=str(v or '').strip(); price=0
        try: price=float(Decimal(str(price or 0)).quantize(Decimal('0.01')))
        except (InvalidOperation,ValueError,TypeError): price=0.0
        return {'name':name,'price':price}

    @app.get('/api/admin/option-lists')
    def option_lists():
        try:
            data=load_catalog(); lists=data.get('optionLists') or {}; defs=data.get('optionListDefs') or {}
            orders=data.get('optionListOrders') or {}; modes=data.get('optionListOrderModes') or {}
            groups=[]
            for key, vals in lists.items():
                if not isinstance(vals,list): continue
                meta=defs.get(key) if isinstance(defs.get(key),dict) else {}
                order=orders.get(key); ordered=[]; used=set()
                if isinstance(order,list):
                    for x in order:
                        try: i=int(x)
                        except (TypeError,ValueError): continue
                        if 0<=i<len(vals) and i not in used: ordered.append(vals[i]); used.add(i)
                ordered.extend(v for i,v in enumerate(vals) if i not in used)
                options=[item(v) for v in ordered]; options=[o for o in options if o['name']]
                groups.append({'key':key,'name':str(meta.get('title') or meta.get('label') or LABELS.get(key) or key),
                               'required':bool(meta.get('required',False)),'max':meta.get('max',0) or 0,
                               'priceMode':meta.get('priceMode','extra'),'orderMode':modes.get(key,'source'),'options':options})
            return jsonify({'ok':True,'count':len(groups),'groups':groups,'source':'catalog_admin_v2.optionLists'})
        except Exception as exc:
            return jsonify({'ok':False,'error':'Groupes indisponibles','detail':str(exc)}),500

    @app.get('/api/admin/options-products-list')
    def options_products_list():
        try:
            data=load_catalog(); products=[]
            for p in data.get('products') or []:
                if isinstance(p,dict): products.append({'id':p.get('id'),'name':p.get('name') or 'Sans nom'})
            return jsonify({'ok':True,'products':products})
        except Exception as exc:
            return jsonify({'ok':False,'error':'Produits indisponibles','detail':str(exc)}),500

    @app.get('/api/admin/options-product/<product_id>')
    def options_product(product_id):
        try:
            data=load_catalog(); p=next((x for x in data.get('products') or [] if isinstance(x,dict) and str(x.get('id'))==str(product_id)),None)
            if not p: return jsonify({'ok':False,'error':'Produit introuvable'}),404
            return jsonify({'ok':True,'product':{'id':p.get('id'),'name':p.get('name')},
                            'optionSelections':p.get('optionSelections') if isinstance(p.get('optionSelections'),dict) else {},
                            'directOptions':p.get('options') if isinstance(p.get('options'),list) else []})
        except Exception as exc:
            return jsonify({'ok':False,'error':'Options produit indisponibles','detail':str(exc)}),500

    @app.get('/administration/options-produits')
    def page():
        return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Options</title><style>*{box-sizing:border-box}body{margin:0;font-family:Arial;background:#f4f5f7;color:#17191c}.top{background:#111827;color:white;padding:14px 22px}.top a{color:white;margin-left:18px}.wrap{max-width:1100px;margin:auto;padding:24px}.card,.group{background:white;border-radius:14px;padding:18px;margin:14px 0}.group{border:1px solid #d9dde3}.opts{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px;margin-top:12px}.opt{border:1px solid #e4e7ec;border-radius:9px;padding:10px;display:flex;justify-content:space-between}.key,.hint{color:#667085;font-size:13px}.good{background:#e8f7ee;padding:10px;border-radius:8px}.bad{background:#fff0ee;color:#9d261d;padding:10px;border-radius:8px}select{width:100%;padding:11px}</style></head><body><div class="top"><b>BÉCHÉFAA • Administration</b><a href="/administration/produits">Produits</a><a href="/pos">Caisse</a></div><div class="wrap"><h1>Options et suppléments</h1><p class="hint">Lecture directe de catalog_admin_v2 — aucune ressaisie.</p><div id="status">Chargement…</div><div class="card"><h2>Groupes existants</h2><div id="groups"></div></div><div class="card"><h2>Affectation par produit</h2><select id="product"></select><div id="assignment"></div></div></div><script>
const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>Number(n||0).toFixed(2).replace('.',',')+' €';
async function json(url){const r=await fetch(url+'?t='+Date.now(),{cache:'no-store'});let d;try{d=await r.json()}catch(e){throw Error('Réponse serveur invalide ('+r.status+')')}if(!r.ok||!d.ok)throw Error((d&&d.error)||('Erreur '+r.status));return d}
async function groups(){const d=await json('/api/admin/option-lists');document.getElementById('groups').innerHTML=d.groups.map(g=>'<div class="group"><b>'+E(g.name)+'</b> <span class="key">('+E(g.key)+')</span><div class="opts">'+g.options.map(o=>'<div class="opt"><span>'+E(o.name)+'</span><b>'+(o.price?('+'+money(o.price)):'0,00 €')+'</b></div>').join('')+'</div></div>').join('');return d.count}
async function products(){const d=await json('/api/admin/options-products-list');const s=document.getElementById('product');s.innerHTML=d.products.map(p=>'<option value="'+E(p.id)+'">'+E(p.name)+'</option>').join('');s.onchange=assignment;if(s.value)await assignment()}
async function assignment(){const id=document.getElementById('product').value;if(!id)return;const d=await json('/api/admin/options-product/'+encodeURIComponent(id));const s=d.optionSelections||{};const refs=Object.keys(s);const chosen=refs.filter(k=>Array.isArray(s[k])&&s[k].length);document.getElementById('assignment').innerHTML='<p><b>'+E(d.product.name)+'</b></p><p>Groupes référencés : '+(refs.length?refs.map(E).join(', '):'aucun')+'</p><p>Groupes avec choix : '+(chosen.length?chosen.map(k=>E(k)+' ('+s[k].length+')').join(', '):'aucun')+'</p>'}
(async()=>{try{const n=await groups();await products();document.getElementById('status').innerHTML='<div class="good">'+n+' groupes chargés depuis PostgreSQL.</div>'}catch(e){document.getElementById('status').innerHTML='<div class="bad">'+E(e.message)+'</div>';document.getElementById('groups').innerHTML='<div class="bad">Impossible de charger les groupes.</div>'}})();
</script></body></html>''',content_type='text/html; charset=utf-8')
