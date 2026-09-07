"""Phase 2.5 — renommage local d'un groupe d'options d'un produit.
Modifie uniquement le titre/label/name d'affichage du groupe direct choisi.
Ne modifie jamais sa clé, ses choix/prix, optionSelections, groupes centraux ou historique.
"""
import json,time
from flask import Response,jsonify,request

def _key(g): return str(g.get('key') or g.get('name') or '').strip()
def _title(g): return str(g.get('title') or g.get('label') or g.get('name') or _key(g)).strip()

def register_product_group_rename_phase25(app,db):
 @app.post('/api/admin/product-group-rename-phase25')
 def product_group_rename_phase25_post():
  b=request.get_json(silent=True) or {}; pid=str(b.get('productId') or '').strip(); key=str(b.get('groupKey') or '').strip(); new=str(b.get('newTitle') or '').strip()
  if not pid or not key or not new:return jsonify({'ok':False,'error':'Produit, groupe et nouveau nom obligatoires'}),400
  if len(new)>100:return jsonify({'ok':False,'error':'Nom trop long (100 caractères maximum)'}),400
  try:
   with db() as conn:
    with conn.transaction():
     row=conn.execute("SELECT data_json::text AS data_json FROM catalog_admin_v2 WHERE id=1 FOR UPDATE").fetchone()
     if not row:return jsonify({'ok':False,'error':'Catalogue introuvable'}),404
     data=json.loads(row['data_json'] or '{}'); products=data.get('products') or []
     pm=[p for p in products if isinstance(p,dict) and str(p.get('id') or '')==pid]
     if len(pm)!=1:return jsonify({'ok':False,'error':'Produit introuvable ou ambigu'}),409
     p=pm[0]; groups=p.get('options') if isinstance(p.get('options'),list) else []
     gm=[g for g in groups if isinstance(g,dict) and _key(g)==key]
     if len(gm)!=1:return jsonify({'ok':False,'error':'Groupe introuvable ou ambigu : opération refusée'}),409
     g=gm[0]; old=_title(g)
     # Conserve la clé technique. Le titre est le champ d'affichage privilégié par le POS.
     g['title']=new
     if 'label' in g:g['label']=new
     # Ne pas modifier name lorsqu'il sert de clé de secours.
     conn.execute("UPDATE catalog_admin_v2 SET data_json=%s::jsonb,updated_at=%s WHERE id=1",(json.dumps(data,ensure_ascii=False),int(time.time()*1000)))
   return jsonify({'ok':True,'message':f'Groupe « {old} » renommé « {new} » uniquement pour ce produit. Clé, choix, prix et historique inchangés.'})
  except Exception as e:return jsonify({'ok':False,'error':str(e)}),500

 @app.get('/administration/renommer-groupe-produit')
 def product_group_rename_phase25_page():
  return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Renommer groupe</title><style>body{font-family:Arial;background:#f4f5f7;margin:0;color:#17191c}.wrap{max-width:760px;margin:auto;padding:24px}.card{background:#fff;padding:18px;border-radius:14px}select,input{width:100%;padding:11px;margin:7px 0 15px;box-sizing:border-box}button{width:100%;padding:12px;background:#111827;color:#fff;border:0;border-radius:8px;font-weight:700}.hint{color:#667085}.ok{background:#e8f7ee;padding:12px;margin-top:12px}.err{background:#fff0ee;color:#9d261d;padding:12px;margin-top:12px}</style></head><body><div class="wrap"><h1>Renommer un groupe d'options</h1><p class="hint">Le renommage est limité au produit sélectionné.</p><div class="card"><b>Produit</b><select id="p" onchange="groups()"></select><b>Groupe</b><select id="g" onchange="fill()"></select><b>Nouveau nom</b><input id="n" maxlength="100"><button onclick="save()">Enregistrer le nouveau nom</button><div id="msg"></div></div></div><script>let gs=[];const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));async function load(){let r=await fetch('/api/admin/options-products-list?t='+Date.now()),d=await r.json();if(!r.ok||!d.ok){msg.innerHTML='<div class="err">Erreur chargement produits</div>';return}p.innerHTML=d.products.map(x=>'<option value="'+E(x.id)+'">'+E(x.name)+'</option>').join('');groups()}async function groups(){let r=await fetch('/api/admin/product-group-order-phase25/'+encodeURIComponent(p.value)+'?t='+Date.now()),d=await r.json();if(!r.ok||!d.ok){gs=[];g.innerHTML='';n.value='';msg.innerHTML='<div class="err">'+E(d.error||'Erreur')+'</div>';return}gs=d.groups;g.innerHTML=gs.map(x=>'<option value="'+E(x.key)+'">'+E(x.title)+'</option>').join('');msg.innerHTML='';fill()}function fill(){let x=gs.find(x=>x.key===g.value);n.value=x?x.title:''}async function save(){let val=n.value.trim();if(!val)return;if(!confirm('Renommer ce groupe uniquement pour ce produit ?'))return;let r=await fetch('/api/admin/product-group-rename-phase25',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({productId:p.value,groupKey:g.value,newTitle:val})}),d=await r.json();msg.innerHTML='<div class="'+(r.ok&&d.ok?'ok':'err')+'">'+E(d.message||d.error||'Erreur')+'</div>';if(r.ok&&d.ok)await groups()}load();</script></body></html>''',content_type='text/html; charset=utf-8')
