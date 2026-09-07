"""Phase 2.5 — ordre des catégories de caisse.
Réordonne uniquement la liste categories du catalogue; produits et historique inchangés.
"""
import json,time
from flask import Response,jsonify,request

def register_category_order_phase25(app,db):
 @app.get('/api/admin/categories-order-phase25')
 def category_order_phase25_get():
  try:
   with db() as conn: row=conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1").fetchone()
   data=json.loads(row['data_json'] or '{}') if row else {}
   cats=data.get('categories') or []
   names=[str(c.get('name') or '') if isinstance(c,dict) else str(c) for c in cats]
   return jsonify({'ok':True,'categories':names})
  except Exception as e:return jsonify({'ok':False,'error':str(e)}),500
 @app.post('/api/admin/categories-order-phase25')
 def category_order_phase25_post():
  wanted=(request.get_json(silent=True) or {}).get('categories')
  if not isinstance(wanted,list):return jsonify({'ok':False,'error':'Ordre invalide'}),400
  try:
   with db() as conn:
    with conn.transaction():
     row=conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1 FOR UPDATE").fetchone()
     if not row:return jsonify({'ok':False,'error':'Catalogue introuvable'}),404
     data=json.loads(row['data_json'] or '{}'); cats=data.get('categories') or []
     current=[str(c.get('name') or '') if isinstance(c,dict) else str(c) for c in cats]
     wanted=[str(x) for x in wanted]
     if len(wanted)!=len(current) or len(set(wanted))!=len(wanted) or set(wanted)!=set(current):return jsonify({'ok':False,'error':'La liste doit contenir exactement toutes les catégories actuelles, une seule fois'}),409
     byname={str(c.get('name') or ''):c for c in cats if isinstance(c,dict)}
     data['categories']=[byname[n] if n in byname else n for n in wanted]
     conn.execute("UPDATE catalog_admin_v2 SET data_json=%s::jsonb,updated_at=%s WHERE id=1",(json.dumps(data,ensure_ascii=False),int(time.time()*1000)))
   return jsonify({'ok':True,'message':'Ordre des catégories enregistré. Produits et historique inchangés.'})
  except Exception as e:return jsonify({'ok':False,'error':str(e)}),500
 @app.get('/administration/ordre-categories')
 def category_order_phase25_page():
  return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Ordre catégories</title><style>body{font-family:Arial;background:#f4f5f7;margin:0;color:#17191c}.wrap{max-width:760px;margin:auto;padding:24px}.card{background:#fff;padding:18px;border-radius:14px}.row{display:flex;align-items:center;gap:10px;padding:10px;border-bottom:1px solid #eee}.name{flex:1;font-weight:700}.move{width:44px;padding:8px}button{cursor:pointer}.save{margin-top:18px;width:100%;padding:12px;background:#111827;color:#fff;border:0;border-radius:8px;font-weight:700}.ok{background:#e8f7ee;padding:12px;margin-top:12px}.err{background:#fff0ee;color:#9d261d;padding:12px;margin-top:12px}</style></head><body><div class="wrap"><h1>Ordre des catégories</h1><p>Utilisez ↑ et ↓ puis enregistrez. Aucun produit n'est déplacé ou supprimé.</p><div class="card" id="list"></div><button class="save" onclick="save()">Enregistrer l'ordre</button><div id="msg"></div></div><script>let cats=[];const E=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));function draw(){list.innerHTML=cats.map((n,i)=>'<div class="row"><span class="name">'+(i+1)+'. '+E(n)+'</span><button class="move" onclick="mv('+i+',-1)">↑</button><button class="move" onclick="mv('+i+',1)">↓</button></div>').join('')}function mv(i,d){let j=i+d;if(j<0||j>=cats.length)return;[cats[i],cats[j]]=[cats[j],cats[i]];draw()}async function load(){let r=await fetch('/api/admin/categories-order-phase25?t='+Date.now()),d=await r.json();if(!r.ok||!d.ok){msg.innerHTML='<div class="err">'+E(d.error||'Erreur')+'</div>';return}cats=d.categories;draw()}async function save(){if(!confirm('Enregistrer ce nouvel ordre des catégories ?'))return;let r=await fetch('/api/admin/categories-order-phase25',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({categories:cats})}),d=await r.json();msg.innerHTML='<div class="'+(r.ok&&d.ok?'ok':'err')+'">'+E(d.message||d.error||'Erreur')+'</div>'}load();</script></body></html>''',content_type='text/html; charset=utf-8')
