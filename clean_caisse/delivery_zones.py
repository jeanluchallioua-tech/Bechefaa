"""Zones de livraison administrables — PostgreSQL uniquement."""
from decimal import Decimal, InvalidOperation
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
                row=conn.execute("""SELECT c.city,c.postal_code,z.code,z.minimum_order FROM caisse_delivery_cities c JOIN caisse_delivery_zones z ON z.code=c.zone_code WHERE c.active=TRUE AND z.active=TRUE AND c.postal_code=%s AND (%s='' OR LOWER(c.city)=LOWER(%s)) LIMIT 1""",(postal,city,city)).fetchone()
            if not row:return jsonify({'ok':True,'deliverable':False,'reason':'OUT_OF_ZONE','message':'Désolé, cette adresse se situe actuellement hors de notre zone de livraison.'})
            minimum=Decimal(str(row['minimum_order']))
            if amount<minimum:return jsonify({'ok':True,'deliverable':False,'reason':'MINIMUM_NOT_REACHED','zone':row['code'],'minimum_order':float(minimum),'missing':float(minimum-amount),'message':f'Le minimum de commande pour votre zone de livraison est de {minimum:.2f} €.'})
            return jsonify({'ok':True,'deliverable':True,'zone':row['code'],'minimum_order':float(minimum),'message':'Adresse livrable.'})
        except Exception as exc:return jsonify({'ok':False,'error':'Contrôle livraison indisponible','detail':str(exc)}),500

    @app.get('/administration/livraison')
    def delivery_admin():
        html=r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Zones de livraison</title><style>*{box-sizing:border-box}body{margin:0;font-family:Arial;background:#f4f5f7;color:#17191c}.top{background:#111827;color:white;padding:14px 22px;display:flex;gap:10px;align-items:center}.top a{color:white;text-decoration:none;background:#263244;padding:9px 12px;border-radius:8px;font-weight:700}.wrap{max-width:1100px;margin:auto;padding:24px}.zones{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.zone{background:white;border-radius:14px;padding:18px}.zone h2{margin-top:0}.minimum{display:flex;gap:8px}.minimum input,.add input,.add select{padding:10px;border:1px solid #ccd1d8;border-radius:8px;width:100%;background:#fff}button{border:0;border-radius:8px;padding:10px 12px;font-weight:700;cursor:pointer;background:#111827;color:white}.add{display:grid;grid-template-columns:110px 1fr auto;gap:7px;margin-top:15px}.lookup-row{display:grid;grid-template-columns:110px auto;gap:7px;margin-top:8px}.lookup-row button{background:#475467}.city{display:flex;justify-content:space-between;gap:8px;border-top:1px solid #eee;padding:10px 0}.city button{background:#b42318;padding:6px 9px}.msg{margin:12px 0;padding:10px;border-radius:8px;background:#e8f7ee}.hint{color:#667085}.lookup{font-size:12px;color:#667085;margin:6px 0 0}@media(max-width:800px){.zones{grid-template-columns:1fr}.add,.lookup-row{grid-template-columns:1fr}}</style></head><body><div class="top"><b>BÉCHÉFAA-Caisse</b><a href="/pos">Caisse</a><a href="/cuisine">Cuisine</a><a href="/historique">Historique</a></div><div class="wrap"><h1>Administration • Zones de livraison</h1><p class="hint">Aucun frais de livraison. Vous définissez uniquement les villes livrables et le minimum de commande de chaque zone.</p><div id="msg"></div><div id="zones" class="zones"></div></div><script>
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function load(){let r=await fetch('/api/delivery-zones'),d=await r.json();if(!d.ok)return;document.getElementById('zones').innerHTML=d.zones.map(z=>`<div class="zone"><h2>Zone ${z.code}</h2><div class="minimum"><input id="min-${z.code}" type="number" min="0" step="0.01" value="${z.minimum_order}" placeholder="Minimum €"><button onclick="save('${z.code}')">Enregistrer</button></div><div class="add"><input id="cp-${z.code}" maxlength="5" inputmode="numeric" placeholder="Code postal"><span id="city-wrap-${z.code}"><input id="city-${z.code}" placeholder="Ville"></span><button onclick="add('${z.code}')">Ajouter</button></div><div class="lookup-row"><button onclick="lookupCity('${z.code}')">Rechercher la ville</button><div id="lookup-${z.code}" class="lookup">Saisissez un code postal puis cliquez sur Rechercher.</div></div><div>${z.cities.length?z.cities.map(c=>`<div class="city"><span><b>${esc(c.postal_code)}</b> ${esc(c.city)}</span><button onclick="del(${c.id})">Supprimer</button></div>`).join(''):'<p class="hint">Aucune ville dans cette zone.</p>'}</div></div>`).join('')}
async function save(z){let r=await fetch('/api/delivery-zones/'+z,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({minimum_order:document.getElementById('min-'+z).value,active:true})}),d=await r.json();message(d.ok?'Zone '+z+' enregistrée':d.error)}
async function lookupCity(z){let cp=document.getElementById('cp-'+z),code=String(cp.value||'').replace(/[^0-9]/g,'').slice(0,5);cp.value=code;let note=document.getElementById('lookup-'+z),wrap=document.getElementById('city-wrap-'+z);if(code.length!==5){note.textContent='Le code postal doit contenir 5 chiffres.';return}note.textContent='Recherche de la ville…';try{let r=await fetch('/api/postal-code/'+encodeURIComponent(code)+'?t='+Date.now(),{cache:'no-store'}),d=await r.json(),cities=Array.isArray(d.cities)?d.cities:[];if(r.ok&&d.ok&&cities.length===1){wrap.innerHTML='<input id="city-'+z+'" value="'+esc(cities[0])+'" placeholder="Ville">';note.textContent='Ville trouvée automatiquement.'}else if(r.ok&&d.ok&&cities.length>1){wrap.innerHTML='<select id="city-'+z+'">'+cities.map(c=>'<option value="'+esc(c)+'">'+esc(c)+'</option>').join('')+'</select>';note.textContent='Plusieurs communes trouvées : choisissez la ville.'}else{wrap.innerHTML='<input id="city-'+z+'" placeholder="Ville">';note.textContent=(d&&d.error)?d.error:'Ville non trouvée — saisissez-la manuellement.'}}catch(e){wrap.innerHTML='<input id="city-'+z+'" placeholder="Ville">';note.textContent='Recherche indisponible — saisissez la ville manuellement.'}}
async function add(z){let r=await fetch('/api/delivery-zones/'+z+'/cities',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({postal_code:document.getElementById('cp-'+z).value,city:document.getElementById('city-'+z).value})}),d=await r.json();if(d.ok){message(d.city+' ajoutée en zone '+z);load()}else message(d.error)}
async function del(id){let r=await fetch('/api/delivery-cities/'+id,{method:'DELETE'}),d=await r.json();if(d.ok)load();else message(d.error)}function message(t){document.getElementById('msg').innerHTML='<div class="msg">'+esc(t)+'</div>'}load()
</script></body></html>'''
        return Response(html,content_type='text/html; charset=utf-8')
