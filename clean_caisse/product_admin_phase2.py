"""Phase 2 — administration produits, PostgreSQL catalog_admin_v2 uniquement. Aucun Wix."""
import json,time,uuid
from decimal import Decimal,InvalidOperation
from flask import Response,jsonify,request

def register_product_admin_phase2(app,db):
 def load(conn):
  row=conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1").fetchone()
  if not row: raise RuntimeError("Catalogue catalog_admin_v2 introuvable")
  data=json.loads(row['data_json'] or '{}'); data.setdefault('categories',[]);data.setdefault('products',[]);return data
 def cats(data):
  out=[]
  for c in data.get('categories') or []:
   n=(c if isinstance(c,str) else c.get('name','') if isinstance(c,dict) else '').strip()
   if n and n not in out:out.append(n)
  return out
 def fields(p):
  name=str(p.get('name') or '').strip();category=str(p.get('category') or '').strip();description=str(p.get('description') or '').strip();photo=str(p.get('photo') or '').strip()
  try:price=Decimal(str(p.get('price',''))).quantize(Decimal('0.01'))
  except (InvalidOperation,ValueError,TypeError):return None,'Prix invalide'
  if not name:return None,'Nom du produit obligatoire'
  if not category:return None,'Catégorie obligatoire'
  if price<0:return None,'Prix invalide'
  if photo and not(photo.startswith('data:image/') or photo.startswith('https://')):return None,'Format de photo invalide'
  return {'name':name,'category':category,'price':float(price),'description':description,'photo':photo,'active':bool(p.get('active',True))},None
 def save(conn,data):
  conn.execute("UPDATE catalog_admin_v2 SET data_json=%s::jsonb, updated_at=%s WHERE id=1",(json.dumps(data,ensure_ascii=False),int(time.time()*1000)));conn.commit()
 @app.get('/api/admin/products')
 def admin_products():
  try:
   with db() as conn:data=load(conn)
   return jsonify({'ok':True,'categories':cats(data),'products':data['products']})
  except Exception as e:return jsonify({'ok':False,'error':'Catalogue indisponible','detail':str(e)}),500
 @app.post('/api/admin/products')
 def create_product():
  values,error=fields(request.get_json(silent=True) or {})
  if error:return jsonify({'ok':False,'error':error}),400
  try:
   with db() as conn:
    data=load(conn)
    if values['category'] not in cats(data):return jsonify({'ok':False,'error':'Catégorie inconnue'}),400
    product={'id':'p-'+uuid.uuid4().hex[:12],**values,'options':[]};data['products'].append(product);save(conn,data)
   return jsonify({'ok':True,'product':product}),201
  except Exception as e:return jsonify({'ok':False,'error':'Enregistrement impossible','detail':str(e)}),500
 @app.put('/api/admin/products/<product_id>')
 def update_product(product_id):
  values,error=fields(request.get_json(silent=True) or {})
  if error:return jsonify({'ok':False,'error':error}),400
  try:
   with db() as conn:
    data=load(conn)
    if values['category'] not in cats(data):return jsonify({'ok':False,'error':'Catégorie inconnue'}),400
    product=next((x for x in data['products'] if isinstance(x,dict) and str(x.get('id'))==product_id),None)
    if not product:return jsonify({'ok':False,'error':'Produit introuvable'}),404
    product.update(values);save(conn,data)
   return jsonify({'ok':True,'product':product})
  except Exception as e:return jsonify({'ok':False,'error':'Modification impossible','detail':str(e)}),500
 @app.get('/administration/produits')
 def page():
  return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Produits</title><style>*{box-sizing:border-box}body{margin:0;font-family:Arial;background:#f4f5f7;color:#17191c}.top{background:#111827;color:#fff;padding:14px 22px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}.top a{color:#fff;text-decoration:none;background:#263244;padding:9px 12px;border-radius:8px;font-weight:700}.wrap{max-width:1050px;margin:auto;padding:24px}.card{background:#fff;border-radius:14px;padding:20px;margin-bottom:20px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.full{grid-column:1/-1}label{display:block;font-weight:800;font-size:13px;margin-bottom:6px}input,select,textarea{width:100%;padding:12px;border:1px solid #ccd1d8;border-radius:9px;font-size:15px}textarea{min-height:70px}.photo{max-width:160px;max-height:120px;margin-top:8px;border-radius:8px;display:none}button{border:0;border-radius:9px;padding:11px 14px;background:#14804a;color:white;font-weight:800;cursor:pointer}.secondary{background:#344054}.msg{margin:12px 0;padding:11px;border-radius:8px}.ok{background:#e8f7ee}.err{background:#fff0ee;color:#9d261d}.hint{color:#667085;font-size:13px}.check{display:flex;gap:8px;align-items:center}.check input{width:auto}.products{width:100%;border-collapse:collapse}.products td,.products th{padding:10px;border-bottom:1px solid #eee;text-align:left}.inactive{opacity:.5}@media(max-width:650px){.grid{grid-template-columns:1fr}.full{grid-column:auto}.products th:nth-child(2),.products td:nth-child(2){display:none}}</style></head><body><div class="top"><b>BÉCHÉFAA • Administration</b><a href="/pos">Caisse</a><a href="/historique">Historique</a><a href="/administration/livraison">Livraison</a></div><div class="wrap"><h1>Produits</h1><p class="hint">Prix de base BÉCHÉFAA. Aucun Wix.</p><div id="msg"></div><div class="card"><h2 id="title">Nouveau produit</h2><div class="grid"><div><label>Nom *</label><input id="name"></div><div><label>Catégorie *</label><select id="category"></select></div><div><label>Prix de base € *</label><input id="price" type="number" min="0" step="0.01"></div><div class="check"><input id="active" type="checkbox" checked><label for="active" style="margin:0">Produit actif</label></div><div class="full"><label>Description</label><textarea id="description"></textarea></div><div class="full"><label>Photo</label><input id="photo" type="file" accept="image/*"><img id="preview" class="photo"></div><div class="full"><button id="save" type="button">Enregistrer le produit</button> <button id="cancel" type="button" class="secondary" style="display:none">Annuler modification</button></div></div></div><div class="card"><h2>Produits existants</h2><table class="products"><thead><tr><th>Produit</th><th>Catégorie</th><th>Prix</th><th>État</th><th></th></tr></thead><tbody id="list"></tbody></table></div></div><script>let products=[],photo='',editing=null;const $=i=>document.getElementById(i),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));function msg(t,o){$('msg').innerHTML='<div class="msg '+(o?'ok':'err')+'">'+esc(t)+'</div>'}async function load(){let r=await fetch('/api/admin/products',{cache:'no-store'}),d=await r.json();if(!d.ok)return msg(d.error,false);products=d.products;$('category').innerHTML=d.categories.map(c=>'<option>'+esc(c)+'</option>').join('');$('list').innerHTML=products.map(p=>'<tr class="'+(p.active===false?'inactive':'')+'"><td>'+esc(p.name)+'</td><td>'+esc(p.category||p.cat||'')+'</td><td>'+Number(p.price||0).toFixed(2)+' €</td><td>'+(p.active===false?'Inactif':'Actif')+'</td><td><button type="button" class="editbtn" data-id="'+esc(String(p.id))+'">Modifier</button></td></tr>').join('')}function startEdit(id){let p=products.find(x=>String(x.id)===String(id));if(!p){msg('Produit introuvable.',false);return}editing=String(p.id);$('title').textContent='Modifier : '+p.name;$('name').value=p.name||'';$('category').value=p.category||p.cat||'';$('price').value=p.price||0;$('description').value=p.description||'';$('active').checked=p.active!==false;photo=p.photo||'';if(photo){$('preview').src=photo;$('preview').style.display='block'}else{$('preview').removeAttribute('src');$('preview').style.display='none'}$('save').textContent='Enregistrer les modifications';$('cancel').style.display='inline-block';msg('Modification de « '+p.name+' » chargée.',true);window.scrollTo(0,0)}function reset(){editing=null;photo='';$('title').textContent='Nouveau produit';$('name').value='';$('price').value='';$('description').value='';$('active').checked=true;$('photo').value='';$('preview').removeAttribute('src');$('preview').style.display='none';$('save').textContent='Enregistrer le produit';$('cancel').style.display='none'}document.addEventListener('click',e=>{let b=e.target.closest('.editbtn');if(b){e.preventDefault();startEdit(b.getAttribute('data-id'))}});$('cancel').addEventListener('click',reset);$('photo').addEventListener('change',e=>{let f=e.target.files[0];if(!f)return;if(f.size>1500000){msg('Photo trop volumineuse (maximum 1,5 Mo).',false);e.target.value='';return}let rd=new FileReader();rd.onload=()=>{photo=rd.result;$('preview').src=photo;$('preview').style.display='block'};rd.readAsDataURL(f)});$('save').addEventListener('click',async()=>{let body={name:$('name').value,category:$('category').value,price:$('price').value,description:$('description').value,photo,active:$('active').checked},url='/api/admin/products'+(editing?'/'+encodeURIComponent(editing):''),method=editing?'PUT':'POST';try{let r=await fetch(url,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Erreur');msg(editing?'Produit modifié.':'Produit enregistré.',true);reset();await load()}catch(e){msg(e.message,false)}});load()</script></body></html>''',content_type='text/html; charset=utf-8')
