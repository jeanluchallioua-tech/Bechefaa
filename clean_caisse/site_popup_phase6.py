"""Fenêtre promotionnelle du site : image et programmation, stockage PostgreSQL."""
import base64
import binascii
import io
import json
import warnings
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit

from flask import Response, jsonify, request
from PIL import Image

PARIS = ZoneInfo('Europe/Paris')
MAX_IMAGE_BYTES = 2 * 1024 * 1024


def paris_datetime(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value))
        if result.tzinfo is None:
            result = result.replace(tzinfo=PARIS)
            # Refuse une heure locale inexistante lors du passage à l'heure d'été.
            back = result.astimezone(timezone.utc).astimezone(PARIS)
            if back.replace(tzinfo=None) != result.replace(tzinfo=None):
                raise ValueError('Heure inexistante')
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError):
        raise ValueError('Date ou heure invalide (heure de Paris)')


def validate_image(data):
    if not data:
        return ''
    if not isinstance(data, str) or len(data) > MAX_IMAGE_BYTES * 4 // 3 + 100:
        raise ValueError('Image trop volumineuse : maximum 2 Mo après optimisation')
    head, separator, encoded = data.partition(',')
    formats = {'data:image/png;base64': 'PNG', 'data:image/jpeg;base64': 'JPEG', 'data:image/webp;base64': 'WEBP'}
    if not separator or head not in formats:
        raise ValueError('Choisissez une image JPG, PNG ou WebP')
    try:
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError('Image trop volumineuse')
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as picture:
                if picture.format != formats[head] or max(picture.size) > 5000 or picture.width * picture.height > 16000000:
                    raise ValueError('Dimensions de l’image trop importantes')
                picture.verify()
    except (binascii.Error, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('Fichier image invalide')
    return data


def validate_link(value):
    value = str(value or '').strip()
    if not value:
        return ''
    if len(value) > 2048 or chr(92) in value or any(ord(ch) <= 32 or ord(ch) == 127 for ch in value):
        raise ValueError('Lien invalide : indiquez une adresse https://… ou une page /notre-carte')
    try:
        parts = urlsplit(value)
        if value.startswith('/') and not value.startswith('//') and not parts.netloc:
            return value
        if parts.scheme.lower() in {'http', 'https'} and parts.hostname and not parts.username and not parts.password:
            return value
    except ValueError:
        pass
    raise ValueError('Lien invalide : indiquez une adresse https://… ou une page /notre-carte')


def popup_live(config, now=None):
    if not config.get('active') or not config.get('image_data'):
        return False
    start, end = paris_datetime(config.get('starts_at')), paris_datetime(config.get('ends_at'))
    now = now or datetime.now(timezone.utc)
    return bool(start and end and start <= now < end)


def register_site_popup_phase6(app, db):
    def ensure(conn):
        conn.execute('''CREATE TABLE IF NOT EXISTS site_popup_config (
            id INTEGER PRIMARY KEY CHECK (id=1), config JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())''')

    def read(conn):
        row = conn.execute('SELECT config::text AS config FROM site_popup_config WHERE id=1').fetchone()
        return json.loads(row['config']) if row else {'active': False, 'image_data': '', 'title': '', 'starts_at': '', 'ends_at': ''}

    @app.after_request
    def popup_no_cache(response):
        if request.path in ('/api/admin/site-popup-phase6', '/api/public/site-popup-phase6', '/administration/publicite-site'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.route('/api/admin/site-popup-phase6', methods=['GET', 'POST'])
    def admin_site_popup():
        try:
            if request.method == 'GET':
                with db() as conn:
                    with conn.transaction():
                        ensure(conn)
                        config = read(conn)
                return jsonify(ok=True, config=config, visible_now=popup_live(config))
            payload = request.get_json(silent=True) or {}
            if request.content_length and request.content_length > 3000000:
                return jsonify(ok=False, error='Image trop volumineuse'), 413
            image = validate_image(payload.get('image_data') or '')
            start, end = paris_datetime(payload.get('starts_at')), paris_datetime(payload.get('ends_at'))
            active = payload.get('active') is True
            if active and (not image or not start or not end):
                raise ValueError('Pour activer la fenêtre, choisissez une image et les deux dates')
            if start and end and end <= start:
                raise ValueError('La fin doit être postérieure au début')
            config = {
                'title': str(payload.get('title') or 'Offre BÉCHÉFAA').strip()[:160],
                'active': active, 'image_data': image,
                'link_url': validate_link(payload.get('link_url')),
                'starts_at': start.isoformat() if start else '',
                'ends_at': end.isoformat() if end else '',
                'revision': datetime.now(timezone.utc).isoformat(),
            }
            with db() as conn:
                with conn.transaction():
                    ensure(conn)
                    conn.execute('''INSERT INTO site_popup_config(id,config) VALUES(1,%s::jsonb)
                        ON CONFLICT(id) DO UPDATE SET config=EXCLUDED.config, updated_at=NOW()''',
                        (json.dumps(config, ensure_ascii=False),))
            return jsonify(ok=True, config=config, visible_now=popup_live(config))
        except ValueError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        except Exception:
            app.logger.exception('Fenêtre promotionnelle : administration indisponible')
            return jsonify(ok=False, error='Enregistrement ou lecture impossible. Réessayez.'), 503

    @app.get('/api/public/site-popup-phase6')
    def public_site_popup():
        try:
            with db() as conn:
                with conn.transaction():
                    ensure(conn)
                    config = read(conn)
            if not popup_live(config):
                return jsonify(ok=True, active=False)
            return jsonify(ok=True, active=True, title=config.get('title') or 'Offre BÉCHÉFAA',
                           link_url=validate_link(config.get('link_url')), image_data=config['image_data'], ends_at=config['ends_at'], revision=config.get('revision', ''))
        except Exception:
            app.logger.exception('Fenêtre promotionnelle : lecture publique indisponible')
            return jsonify(ok=False, active=False), 503

    @app.get('/administration/publicite-site')
    def admin_site_popup_page():
        return Response(ADMIN_HTML, content_type='text/html; charset=utf-8')


ADMIN_HTML = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA · Fenêtre publicitaire</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f5f7;color:#17212f;font:16px Arial,sans-serif}main{max-width:1040px;margin:75px auto 30px;padding:18px}h1{font-size:28px;margin:0 0 10px}p{line-height:1.5}.muted{color:#647080}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.card{padding:22px;background:white;border:1px solid #dce0e5;border-radius:16px}label{display:block;font-weight:bold;margin:16px 0 7px}input,select,button{font:inherit;width:100%;min-height:46px;padding:11px;border:1px solid #ccd0d7;border-radius:9px}button{cursor:pointer;font-weight:bold;background:#111827;color:white}button:disabled{opacity:.55;cursor:wait}.buttons{display:flex;gap:10px;margin-top:20px}.secondary{background:white;color:#111827}#preview{display:block;max-width:100%;max-height:500px;object-fit:contain;margin:auto}#preview[hidden]{display:none}#msg{margin-top:16px;line-height:1.5;font-weight:bold}#state{padding:10px 12px;border-radius:10px;background:#fff5d6;color:#72520a}.preview-wrap{background:#f1f2f4;padding:12px;border-radius:12px}dialog{border:0;border-radius:14px;padding:12px;max-width:calc(100vw - 24px);background:#111}dialog::backdrop{background:#000b}dialog img{display:block;max-width:100%;max-height:75vh;object-fit:contain}dialog button{margin-bottom:10px;background:white;color:#111}@media(max-width:760px){.grid{grid-template-columns:1fr}main{padding:12px}h1{font-size:24px}.card{padding:16px}.buttons{flex-wrap:wrap}}
</style></head><body><main><h1>Fenêtre publicitaire du site</h1><p class="muted">Une image s’ouvre à l’arrivée sur le site, sur ordinateur, tablette et mobile. Elle est affichée une fois par visite et se ferme avec la croix. Les dates sont en heure de Paris.</p>
<div class="grid"><section class="card"><form id="form"><label for="title">Description de l’image</label><input id="title" maxlength="160" placeholder="Ex. Offre spéciale à emporter"><label for="image">Image publicitaire</label><input id="image" type="file" accept="image/jpeg,image/png,image/webp"><p class="muted">JPG, PNG ou WebP. L’image est optimisée automatiquement et affichée en entier, sans recadrage.</p><label for="link">Lien de destination (facultatif)</label><input id="link" type="text" inputmode="url" maxlength="2048" placeholder="https://www.bechefaa.fr/notre-carte ou /notre-carte"><p class="muted">Un clic sur l’image ouvre cette page. Laissez vide pour une image sans lien.</p><label for="start">Début de diffusion (heure de Paris)</label><input id="start" type="datetime-local"><label for="end">Fin de diffusion (heure de Paris)</label><input id="end" type="datetime-local"><label for="active">Diffusion</label><select id="active"><option value="0">Désactivée</option><option value="1">Activée selon les dates</option></select><div class="buttons"><button id="save" disabled type="submit">Enregistrer</button><button id="try" class="secondary" type="button" disabled>Aperçu de la fenêtre</button></div><div id="msg" role="status" aria-live="polite"></div></form></section>
<section class="card"><h2>Aperçu de l’image</h2><p id="state">Chargement…</p><div class="preview-wrap"><p id="empty" class="muted">Aucune image sélectionnée.</p><img id="preview" hidden alt="Aperçu de la publicité"></div></section></div>
<dialog id="demo"><button type="button" id="close">Fermer l’aperçu ×</button><a id="demo-link" target="_blank" rel="noopener noreferrer"><img id="demo-img" alt="Aperçu de la publicité"></a></dialog></main>
<script>
(()=>{'use strict';const $=id=>document.getElementById(id);let imageData='',ready=false,processing=false;
const say=(text,bad=false)=>{$('msg').textContent=text;$('msg').style.color=bad?'#b42318':'#166534'};
function busy(){ $('save').disabled=!ready||processing;$('try').disabled=!imageData||processing;for(const id of ['title','image','link','start','end','active'])$(id).disabled=!ready||processing; }
function show(){ $('preview').hidden=!imageData;$('empty').hidden=!!imageData;if(imageData)$('preview').src=imageData;else $('preview').removeAttribute('src');busy(); }
function localParis(value){if(!value)return '';const parts=new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Paris',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(value));const p=Object.fromEntries(parts.map(x=>[x.type,x.value]));return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;}
function fill(c,live){imageData=c.image_data||'';$('title').value=c.title||'';$('link').value=c.link_url||'';$('start').value=localParis(c.starts_at);$('end').value=localParis(c.ends_at);$('active').value=c.active?'1':'0';$('state').textContent=live?'Diffusion en cours':c.active?'Programmée ou terminée selon les dates':'Diffusion désactivée';show();}
async function json(url,options){const r=await fetch(url,{...options,cache:'no-store'});if(r.status===401)throw Error('Session expirée : rouvrez l’administration.');const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Opération impossible');return d;}
$('image').addEventListener('change',async()=>{const f=$('image').files[0];if(!f)return;if(f.size>15*1024*1024||!['image/jpeg','image/png','image/webp'].includes(f.type)){say('Choisissez un JPG, PNG ou WebP de moins de 15 Mo.',true);$('image').value='';return;}processing=true;busy();say('Optimisation de l’image…');const url=URL.createObjectURL(f);try{const img=new Image();img.src=url;await img.decode();const scale=Math.min(1,1600/Math.max(img.naturalWidth,img.naturalHeight));const canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(img.naturalWidth*scale));canvas.height=Math.max(1,Math.round(img.naturalHeight*scale));canvas.getContext('2d').drawImage(img,0,0,canvas.width,canvas.height);const data=canvas.toDataURL('image/webp',.88);if(data.length>2796300)throw Error('Image trop volumineuse après optimisation. Choisissez une image plus petite.');imageData=data;show();say('Image prête. Enregistrez pour appliquer les modifications.');}catch(e){say(e.message||'Image illisible',true);}finally{URL.revokeObjectURL(url);processing=false;busy();}});
$('form').addEventListener('submit',async e=>{e.preventDefault();if(!ready||processing)return;processing=true;busy();say('Enregistrement…');try{const d=await json('/api/admin/site-popup-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:$('title').value,image_data:imageData,link_url:$('link').value,starts_at:$('start').value,ends_at:$('end').value,active:$('active').value==='1'})});fill(d.config,d.visible_now);say('Fenêtre publicitaire enregistrée.');}catch(e){say(e.message,true);}finally{processing=false;busy();}});
$('try').addEventListener('click',()=>{if(!imageData)return;$('demo-img').src=imageData;const link=$('link').value.trim();const anchor=$('demo-link');anchor.removeAttribute('href');if(link){try{const url=new URL(link,location.origin);if(!['http:','https:'].includes(url.protocol))throw Error();anchor.href=url.href;}catch(_){say('Lien invalide : indiquez une adresse https://… ou une page /notre-carte',true);return;}}$('demo').showModal();});$('close').addEventListener('click',()=>$('demo').close());
busy();json('/api/admin/site-popup-phase6').then(d=>{ready=true;fill(d.config,d.visible_now);}).catch(e=>say(e.message,true));
})();
</script></body></html>'''
