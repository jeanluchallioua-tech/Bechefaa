"""Phase 2.5 — ordre des produits dans chaque catégorie.
Réordonne uniquement la liste products du catalogue, sans modifier le contenu des produits ni l'historique.
"""
import json,time
from flask import Response,jsonify,request

def _cat(p): return str(p.get('category') or p.get('cat') or '')
def _pid(p): return str(p.get('id') or '')

def register_product_order_phase25(app,db):
 @app.after_request
 def products_order_no_cache(response):
  if request.path in ('/api/admin/products-order-phase25','/administration/ordre-produits'):
   response.headers['Cache-Control']='no-store'
  return response

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
     expected=body.get('expectedIds')
     if expected is not None and (not isinstance(expected,list) or [str(x) for x in expected]!=current):return jsonify({'ok':False,'error':'Le classement a été modifié depuis un autre écran. Rechargez la page avant de réessayer.'}),409
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
  return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA · Classement des produits</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f5f7;color:#17212f;font:16px Arial,sans-serif}.wrap{max-width:960px;margin:72px auto 30px;padding:18px}h1{font-size:28px;margin:0 0 10px}p{line-height:1.5}.hint{color:#647080}.card{background:white;border:1px solid #dce0e5;border-radius:15px;padding:20px}.row{display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid #e8eaee}.name{flex:1;min-width:0;font-weight:700;overflow-wrap:anywhere}.number{font-size:13px;font-weight:bold;background:#fff3d2;border-radius:8px;padding:8px;color:#805600;min-width:34px;text-align:center}.off{display:block;color:#777;font-size:12px;margin-top:5px}.controls{display:flex;align-items:center;gap:7px}.controls input{width:64px;text-align:center}.controls button{width:44px;padding:0;font-size:22px}.controls label{font-size:12px;color:#647080;margin:0}button,input,select{font:inherit;min-height:44px;border:1px solid #ccd2da;border-radius:8px;padding:10px;background:#fff;color:#17212f}button{cursor:pointer;font-weight:bold}button:disabled{opacity:.4;cursor:default}select{width:100%;margin:8px 0 12px}.savebar{position:sticky;bottom:0;display:flex;gap:10px;align-items:center;padding:15px 0;background:#f4f5f7}.save{background:#111827;color:white;flex:1;border:0}.reset{background:white}#msg{padding:12px;border-radius:9px;line-height:1.5}#msg:empty{display:none}.ok{background:#e8f7ee;color:#176438}.err{background:#fff0ee;color:#9d261d}.pending{background:#fff3d2;color:#805600}@media(max-width:600px){.wrap{padding:12px}h1{font-size:24px}.card{padding:12px}.row{flex-wrap:wrap;gap:8px}.name{flex-basis:calc(100% - 50px)}.controls{margin-left:auto}.savebar{flex-wrap:wrap}.save{min-width:200px}}
</style></head><body><main class="wrap"><h1>Classement des produits</h1><p>Choisissez une catégorie, puis placez ses produits dans l’ordre souhaité avec les flèches ou le numéro de position.</p><p class="hint">Le classement enregistré est commun à la caisse et au site internet. Les produits masqués ou inactifs conservent leur place dans le classement.</p><section class="card"><label for="cat"><b>Produits de la catégorie</b></label><select id="cat" disabled></select><p id="count" class="hint"></p><div id="list"></div></section><div class="savebar"><button class="save" id="save" type="button" disabled>Enregistrer le classement</button><button class="reset" id="reset" type="button" disabled>Rétablir l’ordre enregistré</button></div><div id="msg" role="status" aria-live="polite"></div></main><script>
(()=>{'use strict';const $=id=>document.getElementById(id);const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));let all=[],items=[],category='',baseline=[],busy=false;
function message(text,kind=''){ $('msg').textContent=text;$('msg').className=kind; }
const ids=()=>items.map(p=>String(p.id));const dirty=()=>JSON.stringify(ids())!==JSON.stringify(baseline);
function controls(){ $('cat').disabled=busy||!all.length;$('save').disabled=busy||!items.length||!dirty();$('reset').disabled=busy||!dirty();$('list').querySelectorAll('button,input').forEach(el=>el.disabled=busy||el.dataset.edge==='1'); }
function draw(){ $('count').textContent=items.length+' produit(s) · même ordre sur le site et la caisse';$('list').innerHTML=items.map((p,i)=>'<div class="row"><span class="number">'+(i+1)+'</span><span class="name">'+E(p.name)+(p.active?'':'<small class="off">Inactif sur la caisse</small>')+'</span><div class="controls"><label for="position-'+i+'">Position</label><input id="position-'+i+'" type="number" min="1" max="'+items.length+'" value="'+(i+1)+'" data-position="'+i+'" aria-label="Position de '+E(p.name)+'"><button type="button" data-index="'+i+'" data-delta="-1" data-edge="'+(i===0?'1':'0')+'" aria-label="Monter '+E(p.name)+'">↑</button><button type="button" data-index="'+i+'" data-delta="1" data-edge="'+(i===items.length-1?'1':'0')+'" aria-label="Descendre '+E(p.name)+'">↓</button></div></div>').join('')||'<p>Aucun produit dans cette catégorie.</p>';controls(); }
function pick(){ items=all.filter(p=>p.category===category);baseline=ids();draw(); }
function move(from,to){ if(busy||from===to||from<0||to<0||from>=items.length||to>=items.length)return;items.splice(to,0,items.splice(from,1)[0]);draw();message(dirty()?'Classement modifié : cliquez sur Enregistrer.':'Ordre enregistré rétabli.',dirty()?'pending':''); }
$('list').addEventListener('click',e=>{const b=e.target.closest('button[data-index]');if(b)move(Number(b.dataset.index),Number(b.dataset.index)+Number(b.dataset.delta));});
$('list').addEventListener('change',e=>{const input=e.target.closest('input[data-position]');if(!input)return;const from=Number(input.dataset.position),value=Number(input.value);if(!Number.isInteger(value)||value<1||value>items.length){draw();message('La position doit être comprise entre 1 et '+items.length+'.','err');return;}move(from,value-1);});
$('cat').addEventListener('change',()=>{if(dirty()&&!confirm('Changer de catégorie sans enregistrer le classement modifié ?')){$('cat').value=category;return;}category=$('cat').value;pick();message('');});
$('reset').addEventListener('click',()=>{pick();message('Ordre enregistré rétabli.');});
async function read(){const r=await fetch('/api/admin/products-order-phase25',{cache:'no-store'});const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Lecture impossible');return d;}
function accept(d,preferred){all=d.products||[];const cats=[...new Set([...(d.categories||[]),...all.map(p=>p.category)].filter(Boolean))];$('cat').innerHTML=cats.map(c=>'<option value="'+E(c)+'">'+E(c)+'</option>').join('');category=cats.includes(preferred)?preferred:(cats[0]||'');$('cat').value=category;pick();}
$('save').addEventListener('click',async()=>{if(busy||!dirty())return;const selected=category,wanted=ids(),expected=[...baseline];busy=true;controls();message('Enregistrement et vérification…');try{const r=await fetch('/api/admin/products-order-phase25',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({category:selected,productIds:wanted,expectedIds:expected})});const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Enregistrement impossible');const fresh=await read();const actual=(fresh.products||[]).filter(p=>p.category===selected).map(p=>String(p.id));if(JSON.stringify(actual)!==JSON.stringify(wanted))throw Error('Le classement relu a changé. Rechargez la page avant de réessayer.');accept(fresh,selected);message('Classement enregistré et vérifié pour la caisse et le site. Actualisez les écrans déjà ouverts pour le voir.','ok');}catch(e){message(e.message||'Enregistrement impossible. Vérifiez la connexion.','err');}finally{busy=false;controls();}});
(async()=>{busy=true;controls();try{accept(await read(),category);}catch(e){message(e.message||'Lecture impossible.','err');}finally{busy=false;controls();}})();
window.addEventListener('beforeunload',e=>{if(dirty()){e.preventDefault();e.returnValue='';}});
})();
</script></body></html>
''',content_type='text/html; charset=utf-8')
