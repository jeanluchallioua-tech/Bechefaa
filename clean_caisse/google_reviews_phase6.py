"""Phase 6 — réglage manuel de la note et du nombre d'avis Google.

Module isolé : les valeurs sont persistées en PostgreSQL et exposées au site.
Aucune table n'est créée au démarrage ; l'initialisation se fait uniquement à
l'ouverture de l'admin ou lors de la lecture/écriture de ces réglages.
"""
from flask import Response, jsonify, request
from .app import db


def _ensure_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS caisse_google_reviews_settings (
        id INTEGER PRIMARY KEY,
        rating NUMERIC(2,1) NOT NULL DEFAULT 5.0,
        review_count INTEGER NOT NULL DEFAULT 120
    )""")
    conn.execute("""INSERT INTO caisse_google_reviews_settings(id,rating,review_count)
                  VALUES (1,5.0,120)
                  ON CONFLICT(id) DO NOTHING""")


def read_google_reviews():
    try:
        with db() as conn:
            _ensure_schema(conn)
            row = conn.execute(
                "SELECT rating,review_count FROM caisse_google_reviews_settings WHERE id=1"
            ).fetchone()
            conn.commit()
        return {
            "rating": float(row["rating"]),
            "review_count": int(row["review_count"]),
        }
    except Exception:
        return {"rating": 5.0, "review_count": 120}


def register_google_reviews_phase6(app):
    @app.get('/api/google-reviews-settings')
    def google_reviews_settings_get():
        data = read_google_reviews()
        return jsonify({'ok': True, **data})

    @app.put('/api/google-reviews-settings')
    def google_reviews_settings_put():
        payload = request.get_json(silent=True) or {}
        try:
            rating = round(float(payload.get('rating', 5.0)), 1)
            review_count = int(payload.get('review_count', 120))
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'Valeurs invalides'}), 400
        if rating < 0 or rating > 5:
            return jsonify({'ok': False, 'error': 'La note doit être comprise entre 0 et 5'}), 400
        if review_count < 0:
            return jsonify({'ok': False, 'error': "Le nombre d'avis ne peut pas être négatif"}), 400
        try:
            with db() as conn:
                _ensure_schema(conn)
                conn.execute(
                    "UPDATE caisse_google_reviews_settings SET rating=%s,review_count=%s WHERE id=1",
                    (rating, review_count),
                )
                conn.commit()
            return jsonify({'ok': True, 'rating': rating, 'review_count': review_count})
        except Exception as exc:
            return jsonify({'ok': False, 'error': 'Enregistrement impossible', 'detail': str(exc)}), 500

    @app.get('/administration/avis-google')
    def google_reviews_admin():
        html = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Avis Google</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f5f7;color:#111827;font-family:Arial,sans-serif}.top{background:#d99a18;color:#fff;padding:15px 22px;font-weight:900}.wrap{max-width:760px;margin:28px auto;padding:0 16px}.box{background:#fff;border-radius:16px;padding:22px;margin-bottom:16px;box-shadow:0 4px 18px #0001}h1{margin-top:0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}label{font-size:13px;font-weight:900;display:block;margin-bottom:6px}input{width:100%;min-height:46px;border:1px solid #d0d5dd;border-radius:9px;padding:9px;font-size:16px}button{border:0;border-radius:9px;padding:11px 15px;font-weight:900;cursor:pointer;background:#111827;color:#fff}.actions{display:flex;gap:10px;flex-wrap:wrap}.secondary{background:#e5e7eb;color:#111}.preview{margin-top:18px;padding:18px;border-radius:12px;background:#111;color:#fff;text-align:center}.stars{color:#f0bd45;letter-spacing:2px;font-size:24px}.rating{font-size:18px;font-weight:900}.rating strong{color:#f0bd45}.muted{color:#667085;font-size:13px;line-height:1.45}.msg{margin-top:12px;font-weight:800}@media(max-width:600px){.grid{grid-template-columns:1fr}.actions button{flex:1}}
</style></head><body><div class="top">BÉCHÉFAA • Avis Google</div><main class="wrap"><section class="box"><h1>Avis Google affichés sur le site</h1><p class="muted">Modifiez ici la note et le nombre d'avis. Le site récupère automatiquement ces valeurs.</p><div class="grid"><div><label for="rating">Note Google</label><input id="rating" type="number" min="0" max="5" step="0.1"></div><div><label for="count">Nombre d'avis</label><input id="count" type="number" min="0" step="1"></div></div><div class="preview"><div class="stars">★★★★★</div><div id="preview" class="rating"><strong>5,0/5</strong> — 120 avis clients</div></div></section><section class="box"><div class="actions"><button onclick="save()">Enregistrer</button><button class="secondary" onclick="location.href='/administration'">Retour Administration</button></div><div id="msg" class="msg"></div></section></main><script>
const $=id=>document.getElementById(id);function fmt(v){return Number(v||0).toLocaleString('fr-FR',{minimumFractionDigits:1,maximumFractionDigits:1})}function preview(){$('preview').innerHTML='<strong>'+fmt($('rating').value)+'/5</strong> — '+Number($('count').value||0)+' avis clients'}$('rating').addEventListener('input',preview);$('count').addEventListener('input',preview);async function load(){try{let r=await fetch('/api/google-reviews-settings',{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Lecture impossible');$('rating').value=d.rating;$('count').value=d.review_count;preview()}catch(e){$('msg').textContent='Erreur : '+e.message}}async function save(){try{let body={rating:Number($('rating').value),review_count:Number($('count').value)},r=await fetch('/api/google-reviews-settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Enregistrement impossible');$('msg').textContent='Avis Google enregistrés. Le site utilisera '+fmt(d.rating)+'/5 et '+d.review_count+' avis.';preview()}catch(e){$('msg').textContent='Erreur : '+e.message}}load();
</script></body></html>'''
        return Response(html, content_type='text/html; charset=utf-8')

    @app.after_request
    def inject_google_reviews_admin_card(response):
        if request.path != '/administration' or response.status_code != 200 or response.mimetype != 'text/html':
            return response
        html = response.get_data(as_text=True)
        if '/administration/avis-google' in html:
            return response
        card = '<a class="card" href="/administration/avis-google"><div class="icon">⭐</div><b>Avis Google</b><span>Modifier la note et le nombre d\'avis affichés sur le site.</span></a>'
        marker = '<a class="card" href="/administration/livraison"'
        pos = html.find(marker)
        if pos >= 0:
            end = html.find('</a>', pos)
            if end >= 0:
                end += 4
                html = html[:end] + card + html[end:]
        else:
            html = html.replace('</section><h2 class="section-title">Caisse & clôture</h2>', card + '</section><h2 class="section-title">Caisse & clôture</h2>', 1)
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
