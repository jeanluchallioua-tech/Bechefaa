"""Central sound settings by screen and marketplace, without changing orders."""
from flask import Response, jsonify, request
from .app import db
from .notification_sound_policy_phase6 import SOUND_POLICY_JS

GROUPS = (
    ('pos', 'Caisse', 82), ('kitchen', 'Cuisine', 82),
    ('deliveroo', 'Deliveroo', 100), ('ubereats', 'Uber Eats', 100),
)
FIELDS = tuple(field for key, _, _ in GROUPS for field in (key + '_enabled', key + '_volume'))


def register_notification_settings_phase6(app):
    def ensure_schema(conn):
        conn.execute('''CREATE TABLE IF NOT EXISTS caisse_notification_settings (
            id INTEGER PRIMARY KEY,
            pos_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            pos_volume INTEGER NOT NULL DEFAULT 82,
            kitchen_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            kitchen_volume INTEGER NOT NULL DEFAULT 82
        )''')
        # Defaults preserve the existing screen volume on upgrade.
        conn.execute('''ALTER TABLE caisse_notification_settings
            ADD COLUMN IF NOT EXISTS deliveroo_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            ADD COLUMN IF NOT EXISTS deliveroo_volume INTEGER NOT NULL DEFAULT 100,
            ADD COLUMN IF NOT EXISTS ubereats_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            ADD COLUMN IF NOT EXISTS ubereats_volume INTEGER NOT NULL DEFAULT 100''')
        conn.execute('''INSERT INTO caisse_notification_settings
            (id,pos_enabled,pos_volume,kitchen_enabled,kitchen_volume)
            VALUES (1,TRUE,82,TRUE,82) ON CONFLICT(id) DO NOTHING''')

    def read_settings(conn):
        ensure_schema(conn)
        row = conn.execute('SELECT ' + ','.join(FIELDS) + ' FROM caisse_notification_settings WHERE id=1').fetchone()
        return {field: bool(row[field]) if field.endswith('_enabled') else int(row[field]) for field in FIELDS}

    def json_response(data, status=200):
        response = jsonify(data)
        response.status_code = status
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.after_request
    def inject_notification_admin_card(response):
        if request.path != '/administration' or response.status_code != 200 or response.mimetype != 'text/html':
            return response
        html = response.get_data(as_text=True)
        if '/administration/notifications' in html:
            return response
        card = '<a class="card" href="/administration/notifications"><div class="icon">🔊</div><b>Notifications sonores</b><span>Régler les sons de la Caisse, de la Cuisine, de Deliveroo et d’Uber Eats.</span></a>'
        marker = '</section><div class="note">'
        if marker in html:
            response.set_data(html.replace(marker, card + marker, 1))
        return response

    @app.get('/api/notification-settings')
    def notification_settings_get():
        try:
            with db() as conn:
                data = read_settings(conn)
                conn.commit()
            return json_response({'ok': True, **data})
        except Exception:
            return json_response({'ok': False, 'error': 'Réglages notifications indisponibles'}, 500)

    @app.put('/api/notification-settings')
    def notification_settings_put():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return json_response({'ok': False, 'error': 'Réglages invalides'}, 400)
        updates = {}
        for field in FIELDS:
            if field not in payload:
                continue
            value = payload[field]
            if field.endswith('_enabled'):
                if type(value) is not bool:
                    return json_response({'ok': False, 'error': 'Activation invalide'}, 400)
            else:
                try:
                    if type(value) is bool:
                        raise ValueError('not a volume')
                    value = max(0, min(100, int(value)))
                except (TypeError, ValueError, OverflowError):
                    return json_response({'ok': False, 'error': 'Volume invalide'}, 400)
            updates[field] = value
        try:
            with db() as conn:
                data = read_settings(conn)
                # Partial saves, including old cached screens, retain all omitted
                # settings. Update only supplied fields to avoid lost updates.
                if updates:
                    conn.execute('UPDATE caisse_notification_settings SET ' +
                        ','.join(field + '=%s' for field in updates) + ' WHERE id=1', tuple(updates.values()))
                    data.update(updates)
                conn.commit()
            return json_response({'ok': True, **data})
        except Exception:
            return json_response({'ok': False, 'error': 'Enregistrement impossible'}, 500)

    @app.get('/administration/notifications')
    def notification_settings_admin():
        sections = []
        for key, label, volume in GROUPS:
            tests = (f'<button class="test" type="button" onclick="testTone(\'{key}\')">Tester la {label}</button>'
                if key in ('pos', 'kitchen') else
                f'<button class="test" type="button" onclick="testTone(\'pos\',\'{key}\')">Tester en caisse</button>'
                f'<button class="test" type="button" onclick="testTone(\'kitchen\',\'{key}\')">Tester en cuisine</button>')
            sections.append(f'''<section class="box"><h2>{label}</h2>
<label class="row" for="{key}Enabled"><b>Son activé</b><input id="{key}Enabled" class="switch" type="checkbox"></label>
<label class="range" for="{key}Volume"><input aria-label="Volume {label}" id="{key}Volume" type="range" min="0" max="100" step="1"><span class="value"><span id="{key}Value">{volume}</span> %</span></label>
<div class="actions">{tests}</div></section>''')
        html = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Notifications</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f5f7;color:#111827;font-family:Arial,sans-serif}.top{background:#d99a18;color:white;padding:15px 22px;font-weight:900}.wrap{max-width:820px;margin:28px auto;padding:0 16px}.box{background:white;border-radius:16px;padding:22px;margin-bottom:16px;box-shadow:0 4px 18px #0001}h1,h2{margin-top:0}.row{display:grid;grid-template-columns:1fr auto;gap:14px;align-items:center;margin:15px 0}.switch{width:22px;height:22px}.range{display:grid;grid-template-columns:1fr 70px;gap:12px;align-items:center}.range input{width:100%}.value{font-weight:900;text-align:center}.actions{display:flex;gap:10px;flex-wrap:wrap}.actions button{border:0;border-radius:9px;padding:11px 15px;font-weight:900;cursor:pointer}.save{background:#111827;color:white}.test{background:#d99a18;color:#111}.msg{margin:12px 0;font-weight:800}.muted{color:#667085;font-size:13px;line-height:1.5}@media(max-width:600px){.actions button{flex:1}}
</style></head><body><div class="top">BÉCHÉFAA • Réglage des notifications</div><main class="wrap">
<section class="box"><h1>Notifications sonores</h1><p class="muted">Les réglages sont enregistrés pour tous les postes. Les volumes Deliveroo et Uber Eats complètent le volume de la Caisse ou de la Cuisine.</p><p id="msg" class="msg" role="status">Chargement des réglages…</p></section>
__SECTIONS__
<section class="box"><div class="actions"><button id="saveButton" class="save" onclick="save()" disabled>Enregistrer les réglages</button><button onclick="location.href='/administration'">Retour Administration</button></div></section>
<section class="box"><h2>Tester une arrivée de commande</h2><p>Aucune commande enregistrée, aucun paiement, aucune impression.</p><div class="actions"><a href="/pos?test_notifications=1">Ouvrir le test caisse</a><a href="/cuisine-preparation?test_notifications=1">Ouvrir le test cuisine</a></div></section>
</main><script>
__SOUND_POLICY__
const $=id=>document.getElementById(id),groups=['pos','kitchen','deliveroo','ubereats'];let settingsLoaded=false,previewContext=null;
groups.forEach(key=>$(key+'Volume').addEventListener('input',()=>$(key+'Value').textContent=$(key+'Volume').value));
function formSettings(){const data={};groups.forEach(key=>{data[key+'_enabled']=$(key+'Enabled').checked;data[key+'_volume']=Number($(key+'Volume').value)});return data;}
async function load(){try{const r=await fetch('/api/notification-settings',{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Erreur');groups.forEach(key=>{$(key+'Enabled').checked=d[key+'_enabled']!==false;$(key+'Volume').value=d[key+'_volume'];$(key+'Value').textContent=d[key+'_volume']});settingsLoaded=true;$('saveButton').disabled=false;$('msg').textContent='';}catch(e){$('msg').textContent='Erreur : '+e.message;}}
async function save(){if(!settingsLoaded)return;$('saveButton').disabled=true;try{const r=await fetch('/api/notification-settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(formSettings())}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Erreur');$('msg').textContent='Réglages enregistrés.';}catch(e){$('msg').textContent='Erreur : '+e.message;}finally{$('saveButton').disabled=false;}}
async function testTone(page,channel='general'){if(!settingsLoaded)return;try{const policy=notificationSoundPolicy(formSettings(),page,channel);if(!policy.enabled||policy.volume<=0){$('msg').textContent='Son désactivé ou volume à zéro pour ce test.';return;}const C=window.AudioContext||window.webkitAudioContext;if(!C)throw Error('Son indisponible');if(!previewContext||previewContext.state==='closed')previewContext=new C();await previewContext.resume();if(previewContext.state!=='running')throw Error('Son bloqué par le navigateur');const ctx=previewContext,v=policy.volume,t=ctx.currentTime+.02;[[920,.22],[1080,.22],[920,.30]].forEach((p,i)=>{const o=ctx.createOscillator(),g=ctx.createGain(),s=t+i*.28;o.type='square';o.frequency.value=p[0];g.gain.setValueAtTime(.001,s);g.gain.exponentialRampToValueAtTime(Math.max(.001,v*[.88,.95,1][i]),s+.015);g.gain.setValueAtTime(Math.max(.001,v*[.88,.95,1][i]),s+p[1]-.055);g.gain.exponentialRampToValueAtTime(.001,s+p[1]);o.connect(g);g.connect(ctx.destination);o.start(s);o.stop(s+p[1]+.02)});$('msg').textContent='Test sonore '+(page==='pos'?'caisse':'cuisine')+' déclenché.';}catch(e){$('msg').textContent=e.message;}}
load();
</script></body></html>'''
        response = Response(html.replace('__SECTIONS__', ''.join(sections)).replace('__SOUND_POLICY__', SOUND_POLICY_JS), content_type='text/html; charset=utf-8')
        response.headers['Cache-Control'] = 'no-store'
        return response

