"""Phase 6 — gestion des majorations marketplace BÉCHÉFAA.

Stocke séparément les pourcentages Uber Eats et Deliveroo. Valeur initiale 15 %.
Aucun prix du catalogue RESTO/SITE n'est modifié.
"""
from decimal import Decimal, InvalidOperation
from flask import jsonify, request, Response

DEFAULTS={"UBER_EATS":Decimal("15.00"),"DELIVEROO":Decimal("15.00")}

def register_marketplace_markup_phase6(app, db):
    def ensure(conn):
        conn.execute("""CREATE TABLE IF NOT EXISTS marketplace_markup_settings(
            channel TEXT PRIMARY KEY,
            percentage NUMERIC(6,2) NOT NULL DEFAULT 15.00,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        for channel,value in DEFAULTS.items():
            conn.execute(
                "INSERT INTO marketplace_markup_settings(channel,percentage) VALUES(%s,%s) ON CONFLICT(channel) DO NOTHING",
                (channel,value),
            )

    def read(conn):
        ensure(conn)
        rows=conn.execute("SELECT channel,percentage,updated_at FROM marketplace_markup_settings ORDER BY channel").fetchall()
        out={r["channel"]:float(r["percentage"]) for r in rows}
        return {
            "UBER_EATS":out.get("UBER_EATS",15.0),
            "DELIVEROO":out.get("DELIVEROO",15.0),
        }

    @app.get("/api/marketplace/markups-phase6")
    def marketplace_markups_get_phase6():
        try:
            with db() as conn:
                with conn.transaction():
                    data=read(conn)
            return jsonify({"ok":True,"markups":data})
        except Exception as exc:
            return jsonify({"ok":False,"error":"Paramètres marketplace indisponibles","detail":str(exc)}),500

    @app.post("/api/marketplace/markups-phase6")
    def marketplace_markups_post_phase6():
        payload=request.get_json(silent=True) or {}
        source=payload.get("markups") if isinstance(payload.get("markups"),dict) else payload
        values={}
        for channel in DEFAULTS:
            raw=source.get(channel,15)
            try:
                pct=Decimal(str(raw)).quantize(Decimal("0.01"))
            except (InvalidOperation,ValueError,TypeError):
                return jsonify({"ok":False,"error":"Pourcentage invalide pour "+channel}),400
            if pct < 0 or pct > 100:
                return jsonify({"ok":False,"error":"Le pourcentage doit être compris entre 0 et 100"}),400
            values[channel]=pct
        try:
            with db() as conn:
                with conn.transaction():
                    ensure(conn)
                    for channel,pct in values.items():
                        conn.execute(
                            """INSERT INTO marketplace_markup_settings(channel,percentage,updated_at)
                               VALUES(%s,%s,NOW())
                               ON CONFLICT(channel) DO UPDATE SET percentage=EXCLUDED.percentage,updated_at=NOW()""",
                            (channel,pct),
                        )
                    data=read(conn)
            return jsonify({"ok":True,"markups":data})
        except Exception as exc:
            return jsonify({"ok":False,"error":"Enregistrement impossible","detail":str(exc)}),500

    @app.get("/administration/marketplaces")
    def marketplace_markups_page_phase6():
        return Response(r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Marketplaces</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f7fb;color:#14213d;font-family:Arial,sans-serif}.w{max-width:850px;margin:30px auto;padding:18px}.b{background:#fff;border:1px solid #e5eaf1;border-radius:18px;padding:24px;box-shadow:0 8px 24px #25466e12}h1{margin-top:0}.g{display:grid;grid-template-columns:1fr 1fr;gap:16px}label{display:block;font-weight:900;margin-bottom:6px}input,button{width:100%;min-height:48px;border:1px solid #ccd5e2;border-radius:10px;padding:10px;font-size:16px}button{margin-top:20px;background:#111827;color:#fff;font-weight:900;cursor:pointer}.m{color:#667085;font-size:13px}.s{font-weight:800;margin-top:12px}@media(max-width:650px){.g{grid-template-columns:1fr}}</style></head><body><div class="w"><div class="b"><h1>Majoration marketplaces</h1><p class="m">Pourcentage ajouté aux prix BÉCHÉFAA lors de la génération des menus marketplace. Le prix caisse et le prix du site restent inchangés.</p><div class="g"><div><label>Uber Eats (%)</label><input id="u" type="number" min="0" max="100" step="0.1"></div><div><label>Deliveroo (%)</label><input id="d" type="number" min="0" max="100" step="0.1"></div></div><button onclick="save()">Enregistrer</button><div id="msg" class="s"></div></div></div><script>
const $=x=>document.getElementById(x);async function load(){try{let r=await fetch('/api/marketplace/markups-phase6',{cache:'no-store'}),j=await r.json();if(!r.ok||!j.ok)throw Error(j.error);$('u').value=j.markups.UBER_EATS;$('d').value=j.markups.DELIVEROO;$('msg').textContent='Paramètres chargés.'}catch(e){$('msg').textContent='Erreur : '+e.message}}
async function save(){$('msg').textContent='Enregistrement…';try{let r=await fetch('/api/marketplace/markups-phase6',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({markups:{UBER_EATS:$('u').value,DELIVEROO:$('d').value}})}),j=await r.json();if(!r.ok||!j.ok)throw Error(j.error);$('msg').textContent='Pourcentages enregistrés.'}catch(e){$('msg').textContent='Erreur : '+e.message}}load();
</script></body></html>''',content_type="text/html; charset=utf-8")
