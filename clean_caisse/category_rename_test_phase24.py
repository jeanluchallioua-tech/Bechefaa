"""Phase 2.4 — renommage isolé et sûr d'une catégorie.
Met à jour la catégorie centrale et les produits qui la référencent.
Ne touche jamais aux commandes historiques.
"""
import json,time
from flask import Response,jsonify,request


def register_category_rename_test_phase24(app,db):
 def name_of(c):
  return (c if isinstance(c,str) else str(c.get('name') or c.get('label') or '') if isinstance(c,dict) else '').strip()
 @app.post('/api/admin/categories-rename-test')
 def category_rename_test_phase24_api():
  body=request.get_json(silent=True) or {}
  old=str(body.get('old') or '').strip(); new=str(body.get('new') or '').strip()
  if not old or not new:return jsonify({'ok':False,'error':'Ancien et nouveau nom obligatoires'}),400
  if len(new)>80:return jsonify({'ok':False,'error':'Nouveau nom trop long'}),400
  try:
   with db() as conn:
    with conn.transaction():
     row=conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1 FOR UPDATE").fetchone()
     if not row:raise RuntimeError('Catalogue introuvable')
     data=json.loads(row['data_json'] or '{}'); categories=data.get('categories')
     if not isinstance(categories,list):raise RuntimeError('Structure categories invalide')
     matches=[i for i,c in enumerate(categories) if name_of(c).casefold()==old.casefold()]
     if len(matches)!=1:return jsonify({'ok':False,'error':'Catégorie source introuvable ou ambiguë'}),409
     if any(i!=matches[0] and name_of(c).casefold()==new.casefold() for i,c in enumerate(categories)):
      return jsonify({'ok':False,'error':'Une catégorie porte déjà ce nom'}),409
     i=matches[0]; original=categories[i]
     if isinstance(original,str):categories[i]=new
     elif isinstance(original,dict):
      original=dict(original)
      if 'name' in original or 'label' not in original:original['name']=new
      else:original['label']=new
      categories[i]=original
     else:raise RuntimeError('Format de catégorie non pris en charge')
     changed=0
     for p in data.get('products') or []:
      if isinstance(p,dict):
       key='category' if p.get('category') is not None else ('cat' if p.get('cat') is not None else None)
       if key and str(p.get(key) or '').strip().casefold()==old.casefold():p[key]=new;changed+=1
     conn.execute("UPDATE catalog_admin_v2 SET data_json=%s::jsonb,updated_at=%s WHERE id=1",(json.dumps(data,ensure_ascii=False),int(time.time()*1000)))
   return jsonify({'ok':True,'old':old,'new':new,'productsUpdated':changed,'message':'Catégorie renommée et références produits mises à jour. Historique des commandes inchangé.'})
  except Exception as e:return jsonify({'ok':False,'error':'Renommage impossible','detail':str(e)}),500
 @app.get('/administration/categories-renommage-test')
 def category_rename_test_phase24_page():
  return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Test renommage catégorie</title><style>*{box-sizing:border-box}body{margin:0;font-family:Arial;background:#f4f5f7;color:#17191c}.wrap{max-width:650px;margin:auto;padding:28px}.card{background:#fff;padding:22px;border-radius:14px}input{width:100%;padding:12px;margin:5px 0 14px;border:1px solid #ccd1d8;border-radius:9px;font-size:16px}button{border:0;border-radius:9px;padding:12px 16px;background:#143d53;color:#fff;font-weight:800;cursor:pointer}.msg{margin-top:15px;padding:11px;border-radius:8px}.ok{background:#e8f7ee}.err{background:#fff0ee;color:#9d261d}.hint{color:#667085;font-size:13px}</style></head><body><div class="wrap"><h1>Test — Renommer une catégorie</h1><p class="hint">Test isolé. La catégorie centrale et ses références produits sont mises à jour dans catalog_admin_v2. Les commandes historiques ne sont jamais modifiées.</p><div class="card"><b>Catégorie actuelle</b><input id="old" value="TEST PHASE 2.4"><b>Nouveau nom</b><input id="new" value="TEST PHASE 2.4 RENOMMEE"><button id="go">Renommer</button><div id="msg"></div></div></div><script>const $=i=>document.getElementById(i),E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));$('go').onclick=async()=>{try{let r=await fetch('/api/admin/categories-rename-test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({old:$('old').value,new:$('new').value})}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Erreur');$('msg').innerHTML='<div class="msg ok">'+E(d.message)+' Produits mis à jour : '+d.productsUpdated+'.</div>';$('go').disabled=true}catch(e){$('msg').innerHTML='<div class="msg err">'+E(e.message)+'</div>'}};</script></body></html>''',content_type='text/html; charset=utf-8')
