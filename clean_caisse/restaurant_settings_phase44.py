"""Phase 4.4 — identité restaurant BÉCHÉFAA.

Stockage isolé des informations administratives. Aucun ticket existant n'est
modifié dans cette étape : raccordement seulement après validation des données.
"""
from flask import jsonify, request, Response

FIELDS = ("name","legal_name","address","postal_code","city","phone","email","siret","vat_number")
DEFAULTS = {"name":"BÉCHÉFAA","legal_name":"","address":"","postal_code":"","city":"Fontenay-sous-Bois","phone":"","email":"","siret":"","vat_number":""}


def register_restaurant_settings_phase44(app, db):
    def ensure(conn):
        conn.execute("""CREATE TABLE IF NOT EXISTS caisse_restaurant_settings(
            setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL DEFAULT '', updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
        for k,v in DEFAULTS.items():
            conn.execute("INSERT INTO caisse_restaurant_settings(setting_key,setting_value) VALUES(%s,%s) ON CONFLICT(setting_key) DO NOTHING",(k,v))

    def read(conn):
        ensure(conn)
        rows=conn.execute("SELECT setting_key,setting_value FROM caisse_restaurant_settings").fetchall()
        values={r["setting_key"]:r["setting_value"] for r in rows}
        return {k:values.get(k,DEFAULTS[k]) for k in FIELDS}

    @app.get('/api/restaurant/settings-phase44')
    def restaurant_settings_get_phase44():
        try:
            with db() as conn:
                with conn.transaction(): data=read(conn)
            return jsonify({"ok":True,"restaurant":data})
        except Exception as exc: return jsonify({"ok":False,"error":"Paramètres restaurant indisponibles","detail":str(exc)}),500

    @app.post('/api/restaurant/settings-phase44')
    def restaurant_settings_post_phase44():
        payload=request.get_json(silent=True) or {}; source=payload.get('restaurant') or payload
        values={k:str(source.get(k,'')).strip()[:200] for k in FIELDS}
        if not values['name']: return jsonify({"ok":False,"error":"Le nom du restaurant est obligatoire"}),400
        try:
            with db() as conn:
                with conn.transaction():
                    ensure(conn)
                    for k,v in values.items(): conn.execute("INSERT INTO caisse_restaurant_settings(setting_key,setting_value,updated_at) VALUES(%s,%s,NOW()) ON CONFLICT(setting_key) DO UPDATE SET setting_value=EXCLUDED.setting_value,updated_at=NOW()",(k,v))
                    data=read(conn)
            return jsonify({"ok":True,"restaurant":data})
        except Exception as exc: return jsonify({"ok":False,"error":"Enregistrement impossible","detail":str(exc)}),500

    @app.get('/parametres/restaurant')
    def restaurant_settings_page_phase44():
        return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Restaurant</title><style>*{box-sizing:border-box}body{margin:0;background:#f4f5f7;font-family:Arial;color:#111827}.w{max-width:850px;margin:30px auto;padding:18px}.b{background:#fff;border-radius:16px;padding:22px;box-shadow:0 5px 20px #0001}h1{margin-top:0}.g{display:grid;grid-template-columns:1fr 1fr;gap:12px}label{display:block;font-size:13px;font-weight:800;margin-bottom:5px}input,button{width:100%;min-height:46px;border:1px solid #d0d5dd;border-radius:9px;padding:9px;font-size:15px}button{margin-top:18px;background:#111827;color:#fff;font-weight:900;cursor:pointer}.m{color:#667085;font-size:13px}.s{font-weight:800;margin-top:10px}@media(max-width:650px){.g{grid-template-columns:1fr}}</style></head><body><div class="w"><div class="b"><h1>Identité du restaurant</h1><p class="m">Ces données sont enregistrées séparément. Les tickets actuels ne sont pas modifiés à cette étape.</p><div class="g"><div><label>Nom commercial</label><input id="name"></div><div><label>Raison sociale</label><input id="legal_name"></div><div><label>Adresse</label><input id="address"></div><div><label>Code postal</label><input id="postal_code"></div><div><label>Ville</label><input id="city"></div><div><label>Téléphone</label><input id="phone"></div><div><label>Email</label><input id="email"></div><div><label>SIRET</label><input id="siret"></div><div><label>N° TVA intracommunautaire</label><input id="vat_number"></div></div><button onclick="save()">Enregistrer</button><div id="msg" class="s"></div></div></div><script>const ids=['name','legal_name','address','postal_code','city','phone','email','siret','vat_number'],$=x=>document.getElementById(x);async function load(){try{let r=await fetch('/api/restaurant/settings-phase44',{cache:'no-store'}),d=await r.json();if(!d.ok)throw Error(d.error);ids.forEach(k=>$(k).value=d.restaurant[k]||'');$('msg').textContent='Données chargées.'}catch(e){$('msg').textContent='Erreur : '+e.message}}async function save(){let restaurant={};ids.forEach(k=>restaurant[k]=$(k).value);$('msg').textContent='Enregistrement…';try{let r=await fetch('/api/restaurant/settings-phase44',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({restaurant})}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error);$('msg').textContent='Informations enregistrées.'}catch(e){$('msg').textContent='Erreur : '+e.message}}load()</script></body></html>''',content_type='text/html; charset=utf-8')
