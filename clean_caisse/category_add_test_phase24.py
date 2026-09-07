"""Phase 2.4 — création isolée d'une catégorie, append-only.
Écrit uniquement catalog_admin_v2.categories. Aucun renommage/suppression/réordre.
"""
import json,time
from flask import Response,jsonify,request


def register_category_add_test_phase24(app,db):
 def load_locked(conn):
  row=conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1 FOR UPDATE").fetchone()
  if not row: raise RuntimeError('Catalogue catalog_admin_v2 introuvable')
  data=json.loads(row['data_json'] or '{}')
  if not isinstance(data.get('categories'),list): raise RuntimeError('Structure categories invalide')
  return data
 def name_of(c):
  return (c if isinstance(c,str) else str(c.get('name') or c.get('label') or '') if isinstance(c,dict) else '').strip()
 @app.post('/api/admin/categories-add-test')
 def category_add_test_phase24_api():
  name=str((request.get_json(silent=True) or {}).get('name') or '').strip()
  if not name:return jsonify({'ok':False,'error':'Nom de catégorie obligatoire'}),400
  if len(name)>80:return jsonify({'ok':False,'error':'Nom trop long'}),400
  try:
   with db() as conn:
    with conn.transaction():
     data=load_locked(conn); categories=data['categories']
     if any(name_of(c).casefold()==name.casefold() for c in categories):
      return jsonify({'ok':False,'error':'Cette catégorie existe déjà'}),409
     categories.append(name)
     conn.execute("UPDATE catalog_admin_v2 SET data_json=%s::jsonb,updated_at=%s WHERE id=1",(json.dumps(data,ensure_ascii=False),int(time.time()*1000)))
   return jsonify({'ok':True,'category':name,'index':len(categories)-1,'message':'Catégorie ajoutée en fin de liste. Aucune catégorie existante modifiée.'}),201
  except Exception as e:return jsonify({'ok':False,'error':'Ajout impossible','detail':str(e)}),500
 @app.get('/administration/categories-ajout-test')
 def category_add_test_phase24_page():
  return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Test ajout catégorie</title><style>*{box-sizing:border-box}body{margin:0;font-family:Arial;background:#f4f5f7;color:#17191c}.wrap{max-width:650px;margin:auto;padding:28px}.card{background:#fff;padding:22px;border-radius:14px}input{width:100%;padding:12px;border:1px solid #ccd1d8;border-radius:9px;font-size:16px}button{margin-top:12px;border:0;border-radius:9px;padding:12px 16px;background:#14804a;color:#fff;font-weight:800;cursor:pointer}.msg{margin-top:15px;padding:11px;border-radius:8px}.ok{background:#e8f7ee}.err{background:#fff0ee;color:#9d261d}.hint{color:#667085;font-size:13px}</style></head><body><div class="wrap"><h1>Test — Ajouter une catégorie</h1><p class="hint">Phase 2.4 isolée : ajout uniquement en fin de liste. Aucun renommage, suppression ou réorganisation.</p><div class="card"><label><b>Nom de la nouvelle catégorie</b></label><input id="name" value="TEST PHASE 2.4" maxlength="80"><button id="add" type="button">Ajouter la catégorie</button><div id="msg"></div></div></div><script>const $=i=>document.getElementById(i),E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));$('add').onclick=async()=>{try{let r=await fetch('/api/admin/categories-add-test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('name').value})}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Erreur');$('msg').innerHTML='<div class="msg ok">'+E(d.message)+' — « '+E(d.category)+' » index '+d.index+'.</div>';$('add').disabled=true}catch(e){$('msg').innerHTML='<div class="msg err">'+E(e.message)+'</div>'}};</script></body></html>''',content_type='text/html; charset=utf-8')
