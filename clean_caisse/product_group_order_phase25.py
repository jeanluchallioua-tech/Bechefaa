"""Phase 2.5 — ordre des groupes d'options d'un produit.
Réordonne uniquement product.options. Ne modifie ni choix/prix, ni optionSelections, ni historique.
"""
import json,time
from flask import Response,jsonify,request

def _gid(g): return str(g.get('key') or g.get('name') or '').strip()
def _title(g): return str(g.get('title') or g.get('label') or g.get('name') or _gid(g)).strip()

def register_product_group_order_phase25(app,db):
 @app.get('/api/admin/product-group-order-phase25/<product_id>')
 def product_group_order_phase25_get(product_id):
  try:
   with db() as conn: row=conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1").fetchone()
   data=json.loads(row['data_json'] or '{}') if row else {}
   matches=[p for p in (data.get('products') or []) if isinstance(p,dict) and str(p.get('id') or '')==str(product_id)]
   if len(matches)!=1:return jsonify({'ok':False,'error':'Produit introuvable ou ambigu'}),404
   p=matches[0]; groups=p.get('options') if isinstance(p.get('options'),list) else []
   clean=[g for g in groups if isinstance(g,dict)]
   if len(clean)!=len(groups):return jsonify({'ok':False,'error':'Structure des groupes invalide : opération refusée'}),409
   ids=[_gid(g) for g in clean]
   if any(not x for x in ids) or len(set(ids))!=len(ids):return jsonify({'ok':False,'error':'Clés de groupes manquantes ou dupliquées : opération refusée'}),409
   return jsonify({'ok':True,'product':{'id':p.get('id'),'name':p.get('name')},'groups':[{'key':_gid(g),'title':_title(g),'required':bool(g.get('required',False)),'max':g.get('max',0) or 0} for g in clean]})
  except Exception as e:return jsonify({'ok':False,'error':str(e)}),500

 @app.post('/api/admin/product-group-order-phase25')
 def product_group_order_phase25_post():
  b=request.get_json(silent=True) or {}; pid=str(b.get('productId') or ''); wanted=b.get('groupKeys')
  if not pid or not isinstance(wanted,list):return jsonify({'ok':False,'error':'Produit ou ordre invalide'}),400
  wanted=[str(x) for x in wanted]
  try:
   with db() as conn:
    with conn.transaction():
     row=conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1 FOR UPDATE").fetchone()
     if not row:return jsonify({'ok':False,'error':'Catalogue introuvable'}),404
     data=json.loads(row['data_json'] or '{}'); products=data.get('products') or []
     matches=[p for p in products if isinstance(p,dict) and str(p.get('id') or '')==pid]
     if len(matches)!=1:return jsonify({'ok':False,'error':'Produit introuvable ou ambigu'}),409
     p=matches[0]; groups=p.get('options') if isinstance(p.get('options'),list) else []
     if any(not isinstance(g,dict) for g in groups):return jsonify({'ok':False,'error':'Structure des groupes invalide'}),409
     current=[_gid(g) for g in groups]
     if any(not x for x in current) or len(set(current))!=len(current):return jsonify({'ok':False,'error':'Clés de groupes manquantes ou dupliquées'}),409
     if len(wanted)!=len(current) or len(set(wanted))!=len(wanted) or set(wanted)!=set(current):return jsonify({'ok':False,'error':'La liste doit contenir exactement tous les groupes du produit, une seule fois'}),409
     bykey={_gid(g):g for g in groups}; p['options']=[bykey[x] for x in wanted]
     conn.execute("UPDATE catalog_admin_v2 SET data_json=%s::jsonb,updated_at=%s WHERE id=1",(json.dumps(data,ensure_ascii=False),int(time.time()*1000)))
   return jsonify({'ok':True,'message':'Ordre des groupes enregistré. Choix, prix et historique inchangés.'})
  except Exception as e:return jsonify({'ok':False,'error':str(e)}),500

 @app.get('/administration/ordre-groupes-produit')
 def product_group_order_phase25_page():
  return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Ordre groupes</title><style>body{font-family:Arial;background:#f4f5f7;margin:0;color:#17191c}.wrap{max-width:800px;margin:auto;padding:24px}.card{background:#fff;padding:18px;border-radius:14px}.row{display:flex;align-items:center;gap:10px;padding:11px;border-bottom:1px solid #eee}.name{flex:1;font-weight:700}.meta{font-size:12px;color:#667085}.move{width:44px;padding:8px}.save{margin-top:18px;width:100%;padding:12px;background:#111827;color:#fff;border:0;border-radius:8px;font-weight:700}select{width:100%;padding:11px;margin:8px 0 16px}.ok{background:#e8f7ee;padding:12px;margin-top:12px}.err{background:#fff0ee;color:#9d261d;padding:12px;margin-top:12px}</style></head><body><div class="wrap"><h1>Ordre des groupes d'options</h1><p>Choisissez un produit puis déplacez ses groupes avec ↑ / ↓.</p><div class="card"><select id="p" onchange="pick()"></select><div id="list"></div></div><button class="save" onclick="save()">Enregistrer l'ordre</button><div id="msg"></div></div><script>let items=[];const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));function draw(){list.innerHTML=items.map((g,i)=>'<div class="row"><div class="name">'+(i+1)+'. '+E(g.title)+'<div class="meta">'+(g.required?'obligatoire':'facultatif')+' • max '+E(g.max)+'</div></div><button class="move" onclick="mv('+i+',-1)">↑</button><button class="move" onclick="mv('+i+',1)">↓</button></div>').join('')||'<p>Aucun groupe direct sur ce produit.</p>'}function mv(i,d){let j=i+d;if(j<0||j>=items.length)return;[items[i],items[j]]=[items[j],items[i]];draw()}async function load(){let r=await fetch('/api/admin/options-products-list?t='+Date.now()),d=await r.json();if(!r.ok||!d.ok){msg.innerHTML='<div class="err">Erreur chargement produits</div>';return}p.innerHTML=d.products.map(x=>'<option value="'+E(x.id)+'">'+E(x.name)+'</option>').join('');await pick()}async function pick(){let r=await fetch('/api/admin/product-group-order-phase25/'+encodeURIComponent(p.value)+'?t='+Date.now()),d=await r.json();if(!r.ok||!d.ok){items=[];draw();msg.innerHTML='<div class="err">'+E(d.error||'Erreur')+'</div>';return}items=d.groups;msg.innerHTML='';draw()}async function save(){if(!items.length)return;if(!confirm('Enregistrer ce nouvel ordre ?'))return;let r=await fetch('/api/admin/product-group-order-phase25',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({productId:p.value,groupKeys:items.map(g=>g.key)})}),d=await r.json();msg.innerHTML='<div class="'+(r.ok&&d.ok?'ok':'err')+'">'+E(d.message||d.error||'Erreur')+'</div>';if(r.ok&&d.ok)await pick()}load();</script></body></html>''',content_type='text/html; charset=utf-8')
