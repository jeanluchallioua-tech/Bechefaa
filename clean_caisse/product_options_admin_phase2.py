"""Phase 2.3 — administration des options existantes de catalog_admin_v2.
Les écritures nom/prix sont isolées dans option_price_admin_phase23.py.
"""
import json
from decimal import Decimal, InvalidOperation
from flask import Response, jsonify


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
            data=load_catalog(); products=[{'id':p.get('id'),'name':p.get('name') or 'Sans nom'} for p in data.get('products') or [] if isinstance(p,dict)]; return jsonify({'ok':True,'products':products})
        except Exception as exc:return jsonify({'ok':False,'error':'Produits indisponibles','detail':str(exc)}),500
    @app.get('/api/admin/options-product/<product_id>')
    def options_product(product_id):
        try:
            data=load_catalog(); p=next((x for x in data.get('products') or [] if isinstance(x,dict) and str(x.get('id'))==str(product_id)),None)
            if not p:return jsonify({'ok':False,'error':'Produit introuvable'}),404
            return jsonify({'ok':True,'product':{'id':p.get('id'),'name':p.get('name')},'optionSelections':p.get('optionSelections') if isinstance(p.get('optionSelections'),dict) else {},'directOptions':p.get('options') if isinstance(p.get('options'),list) else []})
        except Exception as exc:return jsonify({'ok':False,'error':'Options produit indisponibles','detail':str(exc)}),500
    @app.get('/administration/options-produits')
    def options_admin_page():
        return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Options & suppléments</title><style>
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#f4f5f7;color:#17191c}.top{background:#111;color:#fff;padding:15px 22px}.wrap{max-width:1120px;margin:auto;padding:24px 18px 40px}h1{margin:0 0 5px;font-size:30px}h2{margin:0 0 5px;font-size:20px}.intro{color:#667085;margin:0 0 18px}.statusline{font-size:13px;color:#667085;margin:8px 0 16px}.good{background:#eaf7ee;color:#146c3a;border:1px solid #cdebd8;padding:9px 11px;border-radius:9px}.bad{background:#fff0ee;color:#9d261d;border:1px solid #ffd5cf;padding:9px 11px;border-radius:9px}.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 18px}.tab{border:1px solid #cfd4dc;background:#fff;color:#344054;border-radius:9px;padding:10px 13px;font-weight:800;cursor:pointer}.tab.active{background:#111;color:#fff;border-color:#111}.panel{display:none}.panel.active{display:block}.card{background:#fff;border:1px solid #e1e4e8;border-radius:14px;padding:17px;margin:12px 0;box-shadow:0 2px 8px #00000008}.frame{width:100%;border:0;border-radius:10px;background:#fff}.frame.add{height:650px}.frame.rules{height:520px}.hint{color:#667085;font-size:13px;line-height:1.45}.groups{display:grid;grid-template-columns:1fr 1fr;gap:12px}.group{background:#fff;border:1px solid #e2e5ea;border-radius:12px;padding:0;overflow:hidden}.group summary{cursor:pointer;padding:13px 14px;font-weight:800;background:#fafafa}.group .inside{padding:12px}.opts{display:flex;flex-direction:column;gap:8px}.opt{display:grid;grid-template-columns:minmax(0,1fr) 95px auto;gap:7px;align-items:center}.opt input{width:100%;padding:9px 10px;border:1px solid #cfd4dc;border-radius:8px;font-size:14px}.opt input::placeholder{color:#98a2b3}.opt button{border:0;border-radius:8px;padding:9px 10px;background:#111;color:#fff;font-weight:800;cursor:pointer}.opt .pricebtn{background:#d99a18;color:#111}.productbox{max-width:560px}.productbox select{width:100%;padding:11px;border:1px solid #cfd4dc;border-radius:8px;background:#fff}.assignment{margin-top:12px;padding:12px;background:#fafafa;border-radius:10px;color:#475467;font-size:14px;line-height:1.5}@media(max-width:760px){.groups{grid-template-columns:1fr}.opt{grid-template-columns:minmax(0,1fr) 86px}.opt button{grid-column:auto}.frame.add{height:760px}.wrap{padding:18px 12px 30px}h1{font-size:25px}}
</style></head><body><div class="top"><b>BÉCHÉFAA • Options & suppléments</b></div><main class="wrap"><h1>Options & suppléments</h1><p class="intro">Gérez ici les choix proposés aux clients. Les fonctions ont été regroupées pour éviter les doublons et les écrans techniques.</p><div id="status" class="statusline">Chargement…</div>
<div class="tabs"><button class="tab active" data-tab="add">Ajouter / affecter</button><button class="tab" data-tab="rules">Règles par produit</button><button class="tab" data-tab="edit">Noms & prix</button><button class="tab" data-tab="check">Vérifier un produit</button></div>
<section id="tab-add" class="panel active"><div class="card"><h2>Ajouter ou affecter une option</h2><p class="hint">Ajoutez une option à un groupe ou affectez/retirez une option d’un produit.</p><iframe class="frame add" src="/administration/options-ajout-test" title="Ajouter ou affecter une option"></iframe></div></section>
<section id="tab-rules" class="panel"><div class="card"><h2>Règles par produit</h2><p class="hint">Définissez si un groupe est facultatif ou obligatoire et le nombre maximum de choix.</p><iframe class="frame rules" src="/administration/options-regles-test" title="Règles d'options"></iframe></div></section>
<section id="tab-edit" class="panel"><div class="card"><h2>Modifier les noms et les prix</h2><p class="hint">Ouvrez uniquement le groupe à modifier.</p><div id="groups" class="groups"></div></div></section>
<section id="tab-check" class="panel"><div class="card productbox"><h2>Vérifier les options d’un produit</h2><select id="product"></select><div id="assignment" class="assignment">Choisissez un produit.</div></div></section>
</main><script>
const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const money=n=>Number(n||0).toFixed(2).replace('.',',')+' €';
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.getElementById('tab-'+b.dataset.tab).classList.add('active')});
async function json(url){const r=await fetch(url+(url.includes('?')?'&':'?')+'t='+Date.now(),{cache:'no-store'});let d;try{d=await r.json()}catch(e){throw Error('Réponse serveur invalide ('+r.status+')')}if(!r.ok||!d.ok)throw Error((d&&d.error)||('Erreur '+r.status));return d}
async function groups(){const d=await json('/api/admin/option-lists');document.getElementById('groups').innerHTML=d.groups.map(g=>'<details class="group"><summary>'+E(g.name)+' <span class="hint">('+g.options.length+' choix)</span></summary><div class="inside"><div class="opts">'+g.options.map(o=>'<div class="opt"><input type="text" maxlength="120" value="'+E(o.name)+'" placeholder="Nom de l’option" data-name><input type="number" min="0" step="0.01" value="'+Number(o.price||0).toFixed(2)+'" placeholder="Prix €" data-price><button type="button" data-name-save data-group="'+E(g.key)+'" data-index="'+Number(o.index)+'">Nom</button><button class="pricebtn" type="button" data-price-save data-group="'+E(g.key)+'" data-index="'+Number(o.index)+'">Prix</button></div>').join('')+'</div></div></details>').join('');return d.count}
async function put(btn,kind,value){btn.disabled=true;const old=btn.textContent;btn.textContent='…';try{const r=await fetch('/api/admin/option-lists/'+encodeURIComponent(btn.dataset.group)+'/'+encodeURIComponent(btn.dataset.index)+'/'+kind,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({[kind]:value})});const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Erreur');btn.textContent='OK';document.getElementById('status').innerHTML='<div class="good">'+(kind==='name'?'Nom enregistré : « '+E(d.name)+' »':'Prix de « '+E(d.name)+' » : '+money(d.price))+'</div>';setTimeout(()=>btn.textContent=old,1200)}catch(e){btn.textContent=old;alert(e.message)}finally{btn.disabled=false}}
document.addEventListener('click',e=>{let b=e.target.closest('[data-price-save]');if(b){const i=b.parentElement.querySelector('[data-price]');if(i.value===''||Number(i.value)<0){alert('Prix invalide');return}put(b,'price',i.value);return}b=e.target.closest('[data-name-save]');if(b){const i=b.parentElement.querySelector('[data-name]');if(!i.value.trim()){alert('Nom invalide');return}put(b,'name',i.value.trim())}});
async function products(){const d=await json('/api/admin/options-products-list');const s=document.getElementById('product');s.innerHTML='<option value="">Choisir un produit…</option>'+d.products.map(p=>'<option value="'+E(p.id)+'">'+E(p.name)+'</option>').join('');s.onchange=assignment}
async function assignment(){const id=document.getElementById('product').value;if(!id){document.getElementById('assignment').textContent='Choisissez un produit.';return}const d=await json('/api/admin/options-product/'+encodeURIComponent(id));const s=d.optionSelections||{};const refs=Object.keys(s);const chosen=refs.filter(k=>Array.isArray(s[k])&&s[k].length);document.getElementById('assignment').innerHTML='<b>'+E(d.product.name)+'</b><br>Groupes actifs : '+(chosen.length?chosen.map(k=>E(k)+' ('+s[k].length+')').join(', '):'aucun')}
(async()=>{try{const n=await groups();await products();document.getElementById('status').innerHTML='<div class="good">'+n+' groupes disponibles.</div>'}catch(e){document.getElementById('status').innerHTML='<div class="bad">'+E(e.message)+'</div>'}})();
</script></body></html>''',content_type='text/html; charset=utf-8')
