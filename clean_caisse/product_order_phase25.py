"""Phase 2.5 — ordre des produits dans chaque catégorie.
Réordonne uniquement la liste products du catalogue, sans modifier le contenu des produits ni l'historique.
"""
import json,time
from flask import Response,jsonify,request

def _cat(p): return str(p.get('category') or p.get('cat') or '')
def _pid(p): return str(p.get('id') or '')

def register_product_order_phase25(app,db):
 @app.get('/api/admin/products-order-phase25')
 def products_order_phase25_get():
  try:
   with db() as conn: row=conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1").fetchone()
   data=json.loads(row['data_json'] or '{}') if row else {}
   cats=data.get('categories') or []
   catnames=[str(c.get('name') or c.get('label') or '') if isinstance(c,dict) else str(c) for c in cats]
   products=[p for p in (data.get('products') or []) if isinstance(p,dict)]
   return jsonify({'ok':True,'categories':catnames,'products':[{'id':_pid(p),'name':str(p.get('name') or ''),'category':_cat(p),'active':p.get('active',True) is not False} for p in products]})
  except Exception as e:return jsonify({'ok':False,'error':str(e)}),500

 @app.post('/api/admin/products-order-phase25')
 def products_order_phase25_post():
  body=request.get_json(silent=True) or {}; category=str(body.get('category') or ''); wanted=body.get('productIds')
  if not category or not isinstance(wanted,list):return jsonify({'ok':False,'error':'Catégorie ou ordre invalide'}),400
  wanted=[str(x) for x in wanted]
  try:
   with db() as conn:
    with conn.transaction():
     row=conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1 FOR UPDATE").fetchone()
     if not row:return jsonify({'ok':False,'error':'Catalogue introuvable'}),404
     data=json.loads(row['data_json'] or '{}'); products=data.get('products') or []
     target=[p for p in products if isinstance(p,dict) and _cat(p)==category]
     current=[_pid(p) for p in target]
     if not current:return jsonify({'ok':False,'error':'Aucun produit dans cette catégorie'}),404
     if any(not x for x in current) or len(set(current))!=len(current):return jsonify({'ok':False,'error':'Identifiants produits ambigus : opération refusée'}),409
     if len(wanted)!=len(current) or len(set(wanted))!=len(wanted) or set(wanted)!=set(current):return jsonify({'ok':False,'error':'La liste doit contenir exactement tous les produits de cette catégorie, une seule fois'}),409
     ordered=iter([{_pid(p):p for p in target}[x] for x in wanted]); new=[]
     for p in products:
      if isinstance(p,dict) and _cat(p)==category:new.append(next(ordered))
      else:new.append(p)
     data['products']=new
     conn.execute("UPDATE catalog_admin_v2 SET data_json=%s::jsonb,updated_at=%s WHERE id=1",(json.dumps(data,ensure_ascii=False),int(time.time()*1000)))
   return jsonify({'ok':True,'message':'Ordre des produits enregistré. Prix, options et historique inchangés.'})
  except Exception as e:return jsonify({'ok':False,'error':str(e)}),500

 @app.get('/administration/ordre-produits')
 def products_order_phase25_page():
  return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Ordre produits</title><style>body{font-family:Arial;background:#f4f5f7;margin:0;color:#17191c}.wrap{max-width:800px;margin:auto;padding:24px}.card{background:#fff;padding:18px;border-radius:14px}.row{display:flex;align-items:center;gap:10px;padding:10px;border-bottom:1px solid #eee}.name{flex:1;font-weight:700}.off{color:#888}.move{width:44px;padding:8px}.save{margin-top:18px;width:100%;padding:12px;background:#111827;color:#fff;border:0;border-radius:8px;font-weight:700}select{width:100%;padding:11px;margin:8px 0 16px}.ok{background:#e8f7ee;padding:12px;margin-top:12px}.err{background:#fff0ee;color:#9d261d;padding:12px;margin-top:12px}</style></head><body><div class="wrap"><h1>Ordre des produits</h1><p>Choisissez une catégorie, utilisez ↑ et ↓, puis enregistrez.</p><div class="card"><select id="cat" onchange="pick()"></select><div id="list"></div></div><button class="save" onclick="save()">Enregistrer l'ordre de cette catégorie</button><div id="msg"></div></div><script>let all=[],items=[];const E=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));function draw(){list.innerHTML=items.map((p,i)=>'<div class="row"><span class="name '+(p.active?'':'off')+'">'+(i+1)+'. '+E(p.name)+(p.active?'':' (inactif)')+'</span><button class="move" onclick="mv('+i+',-1)">↑</button><button class="move" onclick="mv('+i+',1)">↓</button></div>').join('')||'<p>Aucun produit.</p>'}function pick(){items=all.filter(p=>p.category===cat.value);draw()}function mv(i,d){let j=i+d;if(j<0||j>=items.length)return;[items[i],items[j]]=[items[j],items[i]];draw()}async function load(){let r=await fetch('/api/admin/products-order-phase25?t='+Date.now()),d=await r.json();if(!r.ok||!d.ok){msg.innerHTML='<div class="err">'+E(d.error||'Erreur')+'</div>';return}all=d.products;cat.innerHTML=d.categories.map(c=>'<option>'+E(c)+'</option>').join('');pick()}async function save(){if(!items.length)return;if(!confirm('Enregistrer ce nouvel ordre pour « '+cat.value+' » ?'))return;let r=await fetch('/api/admin/products-order-phase25',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({category:cat.value,productIds:items.map(p=>p.id)})}),d=await r.json();msg.innerHTML='<div class="'+(r.ok&&d.ok?'ok':'err')+'">'+E(d.message||d.error||'Erreur')+'</div>';if(r.ok&&d.ok)await load()}load();</script></body></html>''',content_type='text/html; charset=utf-8')
