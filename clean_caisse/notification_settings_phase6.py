"""Phase 6 — réglages centralisés des notifications sonores.

Module isolé : paramètres persistés en PostgreSQL, sans modifier les commandes.
La table est créée uniquement lors de l'accès au module/API, jamais au démarrage.
"""
from flask import Response, jsonify, request


def register_notification_settings_phase6(app, db):
    def ensure_schema(conn):
        conn.execute("""CREATE TABLE IF NOT EXISTS caisse_notification_settings (
            id INTEGER PRIMARY KEY,
            pos_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            pos_volume INTEGER NOT NULL DEFAULT 82,
            kitchen_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            kitchen_volume INTEGER NOT NULL DEFAULT 82
        )""")
        conn.execute("""INSERT INTO caisse_notification_settings
                      (id,pos_enabled,pos_volume,kitchen_enabled,kitchen_volume)
                      VALUES (1,TRUE,82,TRUE,82)
                      ON CONFLICT(id) DO NOTHING""")

    def read_settings(conn):
        ensure_schema(conn)
        row = conn.execute("""SELECT pos_enabled,pos_volume,kitchen_enabled,kitchen_volume
                            FROM caisse_notification_settings WHERE id=1""").fetchone()
        return {
            'pos_enabled': bool(row['pos_enabled']),
            'pos_volume': int(row['pos_volume']),
            'kitchen_enabled': bool(row['kitchen_enabled']),
            'kitchen_volume': int(row['kitchen_volume']),
        }

    @app.get('/api/notification-settings')
    def notification_settings_get():
        try:
            with db() as conn:
                data = read_settings(conn)
                conn.commit()
            return jsonify({'ok': True, **data})
        except Exception as exc:
            return jsonify({'ok': False, 'error': 'Réglages notifications indisponibles', 'detail': str(exc)}), 500

    @app.put('/api/notification-settings')
    def notification_settings_put():
        payload = request.get_json(silent=True) or {}
        try:
            pv = max(0, min(100, int(payload.get('pos_volume', 82))))
            kv = max(0, min(100, int(payload.get('kitchen_volume', 82))))
        except Exception:
            return jsonify({'ok': False, 'error': 'Volume invalide'}), 400
        pe = bool(payload.get('pos_enabled', True))
        ke = bool(payload.get('kitchen_enabled', True))
        try:
            with db() as conn:
                ensure_schema(conn)
                conn.execute("""UPDATE caisse_notification_settings
                              SET pos_enabled=%s,pos_volume=%s,kitchen_enabled=%s,kitchen_volume=%s
                              WHERE id=1""", (pe, pv, ke, kv))
                conn.commit()
            return jsonify({'ok': True, 'pos_enabled': pe, 'pos_volume': pv,
                            'kitchen_enabled': ke, 'kitchen_volume': kv})
        except Exception as exc:
            return jsonify({'ok': False, 'error': 'Enregistrement impossible', 'detail': str(exc)}), 500

    @app.get('/administration/notifications')
    def notification_settings_admin():
        html = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Notifications</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f5f7;color:#111827;font-family:Arial,sans-serif}.top{background:#d99a18;color:#fff;padding:15px 22px;font-weight:900}.wrap{max-width:820px;margin:28px auto;padding:0 16px}.box{background:#fff;border-radius:16px;padding:22px;margin-bottom:16px;box-shadow:0 4px 18px #0001}h1,h2{margin-top:0}.row{display:grid;grid-template-columns:1fr auto;gap:14px;align-items:center;margin:15px 0}.switch{width:22px;height:22px}.range{display:grid;grid-template-columns:1fr 70px;gap:12px;align-items:center}.range input{width:100%}.value{font-weight:900;text-align:center}.actions{display:flex;gap:10px;flex-wrap:wrap}.actions button{border:0;border-radius:9px;padding:11px 15px;font-weight:900;cursor:pointer}.save{background:#111827;color:#fff}.test{background:#d99a18;color:#111}.msg{margin-top:12px;font-weight:800}.muted{color:#667085;font-size:13px;line-height:1.5}@media(max-width:600px){.row{grid-template-columns:1fr auto}.actions button{flex:1}}
</style></head><body><div class="top">BÉCHÉFAA • Réglage des notifications</div><main class="wrap"><section class="box"><h1>Notifications sonores</h1><p class="muted">Réglez séparément la Caisse et la Cuisine. Le réglage est enregistré pour tous les postes.</p></section><section class="box"><h2>Caisse</h2><div class="row"><label for="posEnabled"><b>Son activé</b></label><input id="posEnabled" class="switch" type="checkbox"></div><div class="range"><input id="posVolume" type="range" min="0" max="100" step="1"><div class="value"><span id="posValue">82</span> %</div></div><div class="actions"><button class="test" onclick="testTone('pos')">Tester la Caisse</button></div></section><section class="box"><h2>Cuisine</h2><div class="row"><label for="kitchenEnabled"><b>Son activé</b></label><input id="kitchenEnabled" class="switch" type="checkbox"></div><div class="range"><input id="kitchenVolume" type="range" min="0" max="100" step="1"><div class="value"><span id="kitchenValue">82</span> %</div></div><div class="actions"><button class="test" onclick="testTone('kitchen')">Tester la Cuisine</button></div></section><section class="box"><div class="actions"><button class="save" onclick="save()">Enregistrer les réglages</button><button onclick="location.href='/administration'">Retour Administration</button></div><div id="msg" class="msg"></div></section></main><script>
const $=id=>document.getElementById(id);['posVolume','kitchenVolume'].forEach(id=>$(id).addEventListener('input',()=>$(id.replace('Volume','Value')).textContent=$(id).value));
async function load(){try{const r=await fetch('/api/notification-settings',{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Erreur');$('posEnabled').checked=!!d.pos_enabled;$('posVolume').value=d.pos_volume;$('posValue').textContent=d.pos_volume;$('kitchenEnabled').checked=!!d.kitchen_enabled;$('kitchenVolume').value=d.kitchen_volume;$('kitchenValue').textContent=d.kitchen_volume;}catch(e){$('msg').textContent='Erreur : '+e.message}}
async function save(){try{const body={pos_enabled:$('posEnabled').checked,pos_volume:Number($('posVolume').value),kitchen_enabled:$('kitchenEnabled').checked,kitchen_volume:Number($('kitchenVolume').value)};const r=await fetch('/api/notification-settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Erreur');$('msg').textContent='Réglages enregistrés.';}catch(e){$('msg').textContent='Erreur : '+e.message}}
function testTone(kind){try{const C=window.AudioContext||window.webkitAudioContext,ctx=new C(),v=Number($(kind==='pos'?'posVolume':'kitchenVolume').value)/100,t=ctx.currentTime+.02;[[920,.22],[1080,.22],[920,.30]].forEach((p,i)=>{const o=ctx.createOscillator(),g=ctx.createGain(),s=t+i*.28;o.type='square';o.frequency.value=p[0];g.gain.setValueAtTime(.001,s);g.gain.exponentialRampToValueAtTime(Math.max(.01,v),s+.015);g.gain.setValueAtTime(Math.max(.01,v),s+p[1]-.055);g.gain.exponentialRampToValueAtTime(.001,s+p[1]);o.connect(g);g.connect(ctx.destination);o.start(s);o.stop(s+p[1]+.02)});}catch(e){$('msg').textContent='Le navigateur bloque le test sonore.'}}
load();
</script></body></html>'''
        return Response(html, content_type='text/html; charset=utf-8')
