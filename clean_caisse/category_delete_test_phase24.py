"""Phase 2.4 — suppression isolée d'une catégorie vide uniquement.
Refuse toute suppression si un produit référence la catégorie.
Ne touche jamais aux commandes historiques.
"""
import json,time
from flask import Response,jsonify,request


def register_category_delete_test_phase24(app,db):
 def name_of(c):
  return (c if isinstance(c,str) else str(c.get('name') or c.get('label') or '') if isinstance(c,dict) else '').strip()
 @app.post('/api/admin/categories-delete-test')
 def category_delete_test_phase24_api():
  name=str((request.get_json(silent=True) or {}).get('name') or '').strip()
  if not name:return jsonify({'ok':False,'error':'Nom de catégorie obligatoire'}),400
  try:
   with db() as conn:
    with conn.transaction():
     row=conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1 FOR UPDATE").fetchone()
     if not row:raise RuntimeError('Catalogue introuvable')
     data=json.loads(row['data_json'] or '{}'); categories=data.get('categories')
     if not isinstance(categories,list):raise RuntimeError('Structure categories invalide')
     matches=[i for i,c in enumerate(categories) if name_of(c).casefold()==name.casefold()]
     if len(matches)!=1:return jsonify({'ok':False,'error':'Catégorie introuvable ou ambiguë'}),409
     attached=[]
     for p in data.get('products') or []:
      if not isinstance(p,dict):continue
      cat=str(p.get('category') or p.get('cat') or '').strip()
      if cat.casefold()==name.casefold():attached.append(str(p.get('name') or p.get('title') or p.get('id') or 'Produit'))
     if attached:
      return jsonify({'ok':False,'error':'Suppression refusée : cette catégorie contient des produits','productsCount':len(attached),'products':attached[:20]}),409
     idx=matches[0]; categories.pop(idx)
     conn.execute("UPDATE catalog_admin_v2 SET data_json=%s::jsonb,updated_at=%s WHERE id=1",(json.dumps(data,ensure_ascii=False),int(time.time()*1000)))
   return jsonify({'ok':True,'category':name,'oldIndex':idx,'message':'Catégorie vide supprimée. Aucun produit ni historique de commande modifié.'})
  except Exception as e:return jsonify({'ok':False,'error':'Suppression impossible','detail':str(e)}),500
 @app.get('/administration/categories-suppression-test')
 def category_delete_test_phase24_page():
  return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Test suppression catégorie</title><style>*{box-sizing:border-box}body{margin:0;font-family:Arial;background:#f4f5f7;color:#17191c}.wrap{max-width:680px;margin:auto;padding:28px}.card{background:#fff;padding:22px;border-radius:14px}input{width:100%;padding:12px;margin:7px 0 14px;border:1px solid #ccd1d8;border-radius:9px;font-size:16px}button{border:0;border-radius:9px;padding:12px 16px;background:#b42318;color:#fff;font-weight:800;cursor:pointer}.msg{margin-top:15px;padding:11px;border-radius:8px}.ok{background:#e8f7ee}.err{background:#fff0ee;color:#9d261d}.hint{color:#667085;font-size:13px}</style></head><body><div class="wrap"><h1>Test — Supprimer une catégorie vide</h1><p class="hint">Sécurité : si un seul produit utilise la catégorie, la suppression est refusée. Les commandes historiques ne sont jamais modifiées.</p><div class="card"><b>Catégorie</b><input id="name" value="TEST PHASE 2.4 FINAL"><button id="go">Tester la suppression</button><div id="msg"></div></div></div><script>const $=i=>document.getElementById(i),E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));$('go').onclick=async()=>{if(!confirm('Supprimer cette catégorie uniquement si elle est vide ?'))return;try{let r=await fetch('/api/admin/categories-delete-test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('name').value})}),d=await r.json();if(!r.ok||!d.ok){let x=d.error||'Erreur';if(d.productsCount)x+=' ('+d.productsCount+' produit(s))';throw Error(x)}$('msg').innerHTML='<div class="msg ok">'+E(d.message)+'</div>';$('go').disabled=true}catch(e){$('msg').innerHTML='<div class="msg err">'+E(e.message)+'</div>'}};</script></body></html>''',content_type='text/html; charset=utf-8')
