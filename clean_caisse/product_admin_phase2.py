"""Phase 2.1 — administration des produits, PostgreSQL catalog_admin_v2 uniquement.
Aucun Wix. Prix de base unique; majorations canaux traitées séparément.
"""
import json
import time
import uuid
from decimal import Decimal, InvalidOperation
from flask import Response, jsonify, request


def register_product_admin_phase2(app, db):
    def load(conn):
        row=conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1").fetchone()
        if not row: raise RuntimeError("Catalogue catalog_admin_v2 introuvable")
        data=json.loads(row['data_json'] or '{}')
        if not isinstance(data,dict): raise RuntimeError("Catalogue invalide")
        data.setdefault('categories',[]); data.setdefault('products',[])
        return data

    def categories(data):
        out=[]
        for c in data.get('categories') or []:
            name=(c if isinstance(c,str) else c.get('name','') if isinstance(c,dict) else '').strip()
            if name and name not in out: out.append(name)
        return out

    @app.get('/api/admin/products')
    def admin_products():
        try:
            with db() as conn:data=load(conn)
            return jsonify({'ok':True,'categories':categories(data),'products':data.get('products') or []})
        except Exception as exc:return jsonify({'ok':False,'error':'Catalogue indisponible','detail':str(exc)}),500

    @app.post('/api/admin/products')
    def admin_product_create():
        p=request.get_json(silent=True) or {}
        name=str(p.get('name') or '').strip(); category=str(p.get('category') or '').strip(); description=str(p.get('description') or '').strip(); photo=str(p.get('photo') or '').strip()
        try:price=Decimal(str(p.get('price',''))).quantize(Decimal('0.01'))
        except (InvalidOperation,ValueError,TypeError):return jsonify({'ok':False,'error':'Prix invalide'}),400
        if not name:return jsonify({'ok':False,'error':'Nom du produit obligatoire'}),400
        if not category:return jsonify({'ok':False,'error':'Catégorie obligatoire'}),400
        if price<0:return jsonify({'ok':False,'error':'Prix invalide'}),400
        if photo and not (photo.startswith('data:image/') or photo.startswith('https://')):return jsonify({'ok':False,'error':'Format de photo invalide'}),400
        try:
            with db() as conn:
                data=load(conn)
                if category not in categories(data):return jsonify({'ok':False,'error':'Catégorie inconnue'}),400
                product={'id':'p-'+uuid.uuid4().hex[:12],'name':name,'category':category,'price':float(price),'description':description,'photo':photo,'active':bool(p.get('active',True)),'options':[]}
                data['products'].append(product)
                now=int(time.time()*1000)
                conn.execute("UPDATE catalog_admin_v2 SET data_json=%s::jsonb, updated_at=%s WHERE id=1",(json.dumps(data,ensure_ascii=False),now));conn.commit()
            return jsonify({'ok':True,'product':product}),201
        except Exception as exc:return jsonify({'ok':False,'error':'Enregistrement impossible','detail':str(exc)}),500

    @app.get('/administration/produits')
    def products_admin_page():
        return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Produits</title><style>*{box-sizing:border-box}body{margin:0;font-family:Arial;background:#f4f5f7;color:#17191c}.top{background:#111827;color:#fff;padding:14px 22px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}.top a{color:#fff;text-decoration:none;background:#263244;padding:9px 12px;border-radius:8px;font-weight:700}.wrap{max-width:900px;margin:auto;padding:24px}.card{background:#fff;border-radius:14px;padding:20px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.full{grid-column:1/-1}label{display:block;font-weight:800;font-size:13px;margin-bottom:6px}input,select,textarea{width:100%;padding:12px;border:1px solid #ccd1d8;border-radius:9px;font-size:15px}textarea{min-height:90px;resize:vertical}.photo{max-width:180px;max-height:140px;margin-top:10px;border-radius:9px;display:none}button{border:0;border-radius:9px;padding:13px 16px;background:#14804a;color:#fff;font-weight:800;cursor:pointer}.msg{margin:12px 0;padding:11px;border-radius:8px}.ok{background:#e8f7ee}.err{background:#fff0ee;color:#9d261d}.hint{color:#667085;font-size:13px}.check{display:flex;gap:8px;align-items:center}.check input{width:auto}@media(max-width:650px){.grid{grid-template-columns:1fr}.full{grid-column:auto}}</style></head><body><div class="top"><b>BÉCHÉFAA • Administration</b><a href="/pos">Caisse</a><a href="/historique">Historique</a><a href="/administration/livraison">Livraison</a></div><div class="wrap"><h1>Nouveau produit</h1><p class="hint">Prix de base BÉCHÉFAA. Uber Eats et Deliveroo utiliseront leurs majorations administrables séparément. Aucun Wix.</p><div id="msg"></div><div class="card"><div class="grid"><div><label>Nom du produit *</label><input id="name"></div><div><label>Catégorie *</label><select id="category"><option>Chargement…</option></select></div><div><label>Prix de base € *</label><input id="price" type="number" min="0" step="0.01"></div><div class="check"><input id="active" type="checkbox" checked><label for="active" style="margin:0">Produit actif</label></div><div class="full"><label>Description</label><textarea id="description"></textarea></div><div class="full"><label>Photo</label><input id="photo" type="file" accept="image/*"><p class="hint">La photo est enregistrée dans le catalogue PostgreSQL.</p><img id="preview" class="photo"></div><div class="full"><button id="save">Enregistrer le produit</button></div></div></div></div><script>let photo='';const $=id=>document.getElementById(id);const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));function message(t,ok){$('msg').innerHTML='<div class="msg '+(ok?'ok':'err')+'">'+esc(t)+'</div>'}async function load(){let r=await fetch('/api/admin/products'),d=await r.json();if(!d.ok)return message(d.error,false);$('category').innerHTML=d.categories.map(c=>'<option value="'+esc(c)+'">'+esc(c)+'</option>').join('')}$('photo').onchange=e=>{let f=e.target.files[0];if(!f){photo='';return}if(f.size>1500000){message('Photo trop volumineuse (maximum 1,5 Mo).',false);e.target.value='';return}let rd=new FileReader();rd.onload=()=>{photo=rd.result;$('preview').src=photo;$('preview').style.display='block'};rd.readAsDataURL(f)};$('save').onclick=async()=>{let b=$('save');b.disabled=true;b.textContent='Enregistrement…';try{let r=await fetch('/api/admin/products',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('name').value,category:$('category').value,price:$('price').value,description:$('description').value,photo:photo,active:$('active').checked})}),d=await r.json();if(!r.ok||!d.ok)throw new Error(d.error||'Erreur');message('Produit « '+d.product.name+' » enregistré. Il est maintenant disponible dans la caisse.',true);$('name').value='';$('price').value='';$('description').value='';$('photo').value='';$('preview').style.display='none';photo=''}catch(e){message(e.message,false)}finally{b.disabled=false;b.textContent='Enregistrer le produit'}};load()</script></body></html>''',content_type='text/html; charset=utf-8')
