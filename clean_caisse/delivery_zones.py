"""Zones de livraison administrables — PostgreSQL uniquement."""
import json
from decimal import Decimal, InvalidOperation
from urllib.parse import quote
from urllib.request import Request, urlopen

from flask import Response, jsonify, request


def register_delivery_zones(app, db):
    def ensure_schema(conn):
        conn.execute("""CREATE TABLE IF NOT EXISTS caisse_delivery_zones (
            code TEXT PRIMARY KEY,
            minimum_order NUMERIC(12,2) NOT NULL DEFAULT 0,
            active BOOLEAN NOT NULL DEFAULT TRUE
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS caisse_delivery_cities (
            id BIGSERIAL PRIMARY KEY,
            zone_code TEXT NOT NULL REFERENCES caisse_delivery_zones(code) ON DELETE CASCADE,
            postal_code TEXT NOT NULL,
            city TEXT NOT NULL,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            UNIQUE(postal_code, city)
        )""")
        for code in ('A','B','C'):
            conn.execute("INSERT INTO caisse_delivery_zones(code,minimum_order,active) VALUES (%s,0,TRUE) ON CONFLICT(code) DO NOTHING",(code,))

    @app.get('/api/delivery-zones')
    def zones_list():
        try:
            with db() as conn:
                ensure_schema(conn); conn.commit()
                zones=conn.execute("SELECT code,minimum_order,active FROM caisse_delivery_zones ORDER BY code").fetchall()
                cities=conn.execute("SELECT id,zone_code,postal_code,city,active FROM caisse_delivery_cities ORDER BY zone_code,postal_code,city").fetchall()
            return jsonify({'ok':True,'zones':[{'code':z['code'],'minimum_order':float(z['minimum_order']),'active':bool(z['active']),'cities':[dict(c) for c in cities if c['zone_code']==z['code']]} for z in zones]})
        except Exception as exc:return jsonify({'ok':False,'error':'Zones indisponibles','detail':str(exc)}),500

    @app.get('/api/delivery-city-search')
    def delivery_city_search():
        q=str(request.args.get('q') or '').strip()
        if len(q)<2:return jsonify({'ok':False,'error':'Saisissez au moins 2 caractères','cities':[]}),400
        try:
            url='https://geo.api.gouv.fr/communes?nom='+quote(q)+'&fields=nom,codesPostaux&boost=population&limit=12'
            req=Request(url,headers={'User-Agent':'BECHEFAA-Caisse/1.0'})
            with urlopen(req,timeout=5) as res:
                rows=json.loads(res.read().decode('utf-8'))
            cities=[]; seen=set()
            for row in rows if isinstance(rows,list) else []:
                if not isinstance(row,dict):continue
                name=str(row.get('nom') or '').strip()
                postals=row.get('codesPostaux') if isinstance(row.get('codesPostaux'),list) else []
                for postal in postals:
                    postal=''.join(ch for ch in str(postal) if ch.isdigit())[:5]
                    key=(name.lower(),postal)
                    if name and len(postal)==5 and key not in seen:
                        seen.add(key);cities.append({'city':name,'postal_code':postal})
            return jsonify({'ok':True,'query':q,'cities':cities[:20]})
        except Exception as exc:
            return jsonify({'ok':False,'error':'Recherche de ville indisponible','cities':[],'detail':str(exc)}),502

    @app.put('/api/delivery-zones/<code>')
    def zone_update(code):
        code=code.upper()
        if code not in ('A','B','C'):return jsonify({'ok':False,'error':'Zone invalide'}),400
        p=request.get_json(silent=True) or {}
        try:minimum=Decimal(str(p.get('minimum_order',0))).quantize(Decimal('0.01'))
        except (InvalidOperation,ValueError,TypeError):return jsonify({'ok':False,'error':'Minimum invalide'}),400
        if minimum<0:return jsonify({'ok':False,'error':'Minimum invalide'}),400
        try:
            with db() as conn:
                ensure_schema(conn)
                conn.execute("UPDATE caisse_delivery_zones SET minimum_order=%s,active=%s WHERE code=%s",(minimum,bool(p.get('active',True)),code))
                conn.commit()
            return jsonify({'ok':True,'code':code,'minimum_order':float(minimum)})
        except Exception as exc:return jsonify({'ok':False,'error':'Modification impossible','detail':str(exc)}),500

    @app.post('/api/delivery-zones/<code>/cities')
    def city_add(code):
        code=code.upper();p=request.get_json(silent=True) or {};postal=''.join(x for x in str(p.get('postal_code','')) if x.isdigit())[:5];city=str(p.get('city','')).strip()
        if code not in ('A','B','C') or len(postal)!=5 or not city:return jsonify({'ok':False,'error':'Zone, code postal ou ville invalide'}),400
        try:
            with db() as conn:
                ensure_schema(conn)
                conn.execute("INSERT INTO caisse_delivery_cities(zone_code,postal_code,city,active) VALUES(%s,%s,%s,TRUE) ON CONFLICT(postal_code,city) DO UPDATE SET zone_code=EXCLUDED.zone_code,active=TRUE",(code,postal,city));conn.commit()
            return jsonify({'ok':True,'zone':code,'postal_code':postal,'city':city}),201
        except Exception as exc:return jsonify({'ok':False,'error':'Ajout impossible','detail':str(exc)}),500

    @app.delete('/api/delivery-cities/<int:city_id>')
    def city_delete(city_id):
        try:
            with db() as conn:
                ensure_schema(conn);conn.execute("DELETE FROM caisse_delivery_cities WHERE id=%s",(city_id,));conn.commit()
            return jsonify({'ok':True})
        except Exception as exc:return jsonify({'ok':False,'error':'Suppression impossible','detail':str(exc)}),500

    @app.get('/api/delivery/check')
    def delivery_check():
        postal=''.join(x for x in str(request.args.get('postal_code','')) if x.isdigit())[:5];city=str(request.args.get('city','')).strip();total=request.args.get('total','0')
        try:amount=Decimal(str(total))
        except Exception:amount=Decimal('0')
        try:
            with db() as conn:
                ensure_schema(conn);conn.commit()
                if city:
                    rows=conn.execute("""SELECT c.city,c.postal_code,z.code,z.minimum_order FROM caisse_delivery_cities c JOIN caisse_delivery_zones z ON z.code=c.zone_code WHERE c.active=TRUE AND z.active=TRUE AND LOWER(TRIM(c.city))=LOWER(TRIM(%s)) ORDER BY c.id""",(city,)).fetchall()
                    if postal:
                        matching=[r for r in rows if str(r['postal_code'])==postal]
                        if matching:rows=matching
                    row=rows[0] if rows else None
                else:
                    row=conn.execute("""SELECT c.city,c.postal_code,z.code,z.minimum_order FROM caisse_delivery_cities c JOIN caisse_delivery_zones z ON z.code=c.zone_code WHERE c.active=TRUE AND z.active=TRUE AND c.postal_code=%s LIMIT 1""",(postal,)).fetchone()
            if not row:return jsonify({'ok':True,'deliverable':False,'reason':'OUT_OF_ZONE','message':'Désolé, cette adresse se situe actuellement hors de notre zone de livraison.'})
            minimum=Decimal(str(row['minimum_order']))
            if amount<minimum:return jsonify({'ok':True,'deliverable':False,'reason':'MINIMUM_NOT_REACHED','zone':row['code'],'minimum_order':float(minimum),'missing':float(minimum-amount),'message':f'Le minimum de commande pour votre zone de livraison est de {minimum:.2f} €.'})
            return jsonify({'ok':True,'deliverable':True,'zone':row['code'],'minimum_order':float(minimum),'message':'Adresse livrable.'})
        except Exception as exc:return jsonify({'ok':False,'error':'Contrôle livraison indisponible','detail':str(exc)}),500

    @app.get('/administration/livraison')
    def delivery_admin():
        html=r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Zones de livraison</title><style>*{box-sizing:border-box}body{margin:0;font-family:Arial;background:#f4f5f7;color:#17191c}.top{background:#111827;color:white;padding:14px 22px;display:flex;gap:10px;align-items:center}.top a{color:white;text-decoration:none;background:#263244;padding:9px 12px;border-radius:8px;font-weight:700}.wrap{max-width:1100px;margin:auto;padding:24px}.zones{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.zone{background:white;border-radius:14px;padding:18px}.zone h2{margin-top:0}.minimum{display:flex;gap:8px}.minimum input,.add input,.add select{padding:10px;border:1px solid #ccd1d8;border-radius:8px;width:100%;background:#fff}button{border:0;border-radius:8px;padding:10px 12px;font-weight:700;cursor:pointer;background:#111827;color:white}.add{margin-top:15px}.searchline{display:grid;grid-template-columns:1fr auto;gap:7px}.resultline{display:grid;grid-template-columns:1fr auto;gap:7px;margin-top:7px}.city{display:flex;justify-content:space-between;gap:8px;border-top:1px solid #eee;padding:10px 0}.city button{background:#b42318;padding:6px 9px}.msg{margin:12px 0;padding:10px;border-radius:8px;background:#e8f7ee}.hint{color:#667085}.lookup{font-size:12px;color:#667085;margin:6px 0 0}@media(max-width:800px){.zones{grid-template-columns:1fr}.searchline,.resultline{grid-template-columns:1fr}}</style></head><body><div class="top"><b>BÉCHÉFAA-Caisse</b><a href="/pos">Caisse</a><a href="/cuisine">Cuisine</a><a href="/historique">Historique</a></div><div class="wrap"><h1>Administration • Zones de livraison</h1><p class="hint">Aucun frais de livraison. Saisissez simplement le nom d'une ville : le code postal est récupéré automatiquement.</p><div id="msg"></div><div id="zones" class="zones"></div></div><script>const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));async function load(){let r=await fetch('/api/delivery-zones'),d=await r.json();if(!d.ok)return;document.getElementById('zones').innerHTML=d.zones.map(z=>`<div class="zone"><h2>Zone ${z.code}</h2><div class="minimum"><input id="min-${z.code}" type="number" min="0" step="0.01" value="${z.minimum_order}" placeholder="Minimum €"><button onclick="save('${z.code}')">Enregistrer</button></div><div class="add"><div class="searchline"><input id="city-query-${z.code}" placeholder="Nom de la ville, ex. Villemomble" onkeydown="if(event.key==='Enter'){event.preventDefault();searchCity('${z.code}')} "><button onclick="searchCity('${z.code}')">Rechercher</button></div><div id="result-${z.code}"></div><div id="lookup-${z.code}" class="lookup">Le code postal sera ajouté automatiquement.</div></div><div>${z.cities.length?z.cities.map(c=>`<div class="city"><span><b>${esc(c.city)}</b> <small>${esc(c.postal_code)}</small></span><button onclick="del(${c.id})">Supprimer</button></div>`).join(''):'<p class="hint">Aucune ville dans cette zone.</p>'}</div></div>`).join('')}async function save(z){let r=await fetch('/api/delivery-zones/'+z,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({minimum_order:document.getElementById('min-'+z).value,active:true})}),d=await r.json();message(d.ok?'Zone '+z+' enregistrée':d.error)}async function searchCity(z){let q=document.getElementById('city-query-'+z).value.trim(),note=document.getElementById('lookup-'+z),box=document.getElementById('result-'+z);if(q.length<2){note.textContent='Saisissez au moins 2 caractères.';box.innerHTML='';return}note.textContent='Recherche…';box.innerHTML='';try{let r=await fetch('/api/delivery-city-search?q='+encodeURIComponent(q)),d=await r.json(),rows=Array.isArray(d.cities)?d.cities:[];if(!r.ok||!d.ok||!rows.length){note.textContent='Aucune ville trouvée.';return}box.innerHTML=`<div class="resultline"><select id="city-choice-${z}">${rows.map((c,i)=>`<option value="${i}">${esc(c.city)} — ${esc(c.postal_code)}</option>`).join('')}</select><button onclick="addFound('${z}')">Ajouter</button></div>`;box.dataset.rows=JSON.stringify(rows);note.textContent=rows.length===1?'Ville trouvée. Cliquez sur Ajouter.':'Plusieurs résultats : choisissez la bonne ville.'}catch(e){note.textContent='Recherche indisponible.'}}async function addFound(z){let box=document.getElementById('result-'+z),rows=[];try{rows=JSON.parse(box.dataset.rows||'[]')}catch(e){}let sel=document.getElementById('city-choice-'+z),c=sel?rows[Number(sel.value)]:null;if(!c)return;let r=await fetch('/api/delivery-zones/'+z+'/cities',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({postal_code:c.postal_code,city:c.city})}),d=await r.json();if(d.ok){message(d.city+' ajoutée en zone '+z);load()}else message(d.error)}async function del(id){let r=await fetch('/api/delivery-cities/'+id,{method:'DELETE'}),d=await r.json();if(d.ok)load();else message(d.error)}function message(t){document.getElementById('msg').innerHTML='<div class="msg">'+esc(t)+'</div>'}load()</script></body></html>'''
        return Response(html,content_type='text/html; charset=utf-8')
