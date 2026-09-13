"""Phase 6 — vue Administration des profils et accès PIN.

Interface isolée : lecture de l'état des profils de sécurité existants.
Aucun droit, PIN, paiement, commande, cuisine ou clôture n'est modifié ici.
"""
from flask import Response
from .app import db, ensure_order_schema
from .security_pin_phase44 import register_security_pin_phase44


def register_admin_users_ui_phase6(app):
    # Le module Sécurité existait déjà mais n'était pas enregistré dans le
    # point d'entrée WSGI actif. On l'enregistre ici, sans modifier sa logique.
    register_security_pin_phase44(app, db, ensure_order_schema)

    @app.get("/administration/utilisateurs")
    def admin_users_ui_phase6():
        html = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Utilisateurs & accès</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f4f6;color:#111827;font-family:Arial,sans-serif}.top{background:#111827;color:#fff;padding:15px 22px;display:flex;gap:10px;align-items:center}.top b{font-size:20px}.top .spacer{flex:1}.top a{color:#fff;text-decoration:none;background:#263244;padding:9px 12px;border-radius:8px;font-weight:800}.wrap{max-width:980px;margin:0 auto;padding:26px 18px}.box{background:#fff;border-radius:16px;padding:22px;margin-bottom:16px;box-shadow:0 2px 12px #0001}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.profile{border:1px solid #e5e7eb;border-radius:14px;padding:18px}.profile h2{margin:0 0 7px}.muted{color:#667085;font-size:13px;line-height:1.45}.pill{display:inline-block;border-radius:99px;padding:6px 10px;font-size:12px;font-weight:900;margin-top:8px}.ok{background:#ecfdf3;color:#027a48}.warn{background:#fff7ed;color:#b54708}.btn{display:inline-block;background:#111827;color:#fff;text-decoration:none;border-radius:9px;padding:11px 15px;font-weight:900;margin-top:10px}.msg{font-weight:800}@media(max-width:700px){.grid{grid-template-columns:1fr}}
</style></head><body><header class="top"><b>BÉCHÉFAA • Utilisateurs & accès</b><span class="spacer"></span><a href="/administration">Administration</a></header><main class="wrap"><div class="box"><h1>Profils utilisateurs</h1><p class="muted">Deux profils sont prévus pour l'exploitation : <b>Administrateur</b> et <b>Technicien</b>. Les deux conservent actuellement les mêmes droits opérationnels. Cette page affiche uniquement l'état des accès PIN existants.</p></div><div class="grid"><div class="profile"><h2>👤 Administrateur</h2><p class="muted">Profil principal de gestion et d'administration.</p><div id="admin-state" class="pill warn">Vérification…</div></div><div class="profile"><h2>🛠️ Technicien</h2><p class="muted">Profil technique avec les mêmes droits opérationnels que l'Administrateur.</p><div id="tech-state" class="pill warn">Vérification…</div></div></div><div class="box" style="margin-top:16px"><h2>Gestion des codes PIN</h2><p class="muted">La configuration et l'authentification restent assurées par le module de sécurité déjà en place. Aucun PIN n'est affiché sur cette page.</p><a class="btn" href="/securite">Ouvrir Sécurité / Accès</a><div id="msg" class="msg"></div></div></main><script>
function setState(id,configured){let e=document.getElementById(id);e.textContent=configured?'PIN configuré':'PIN à configurer';e.className='pill '+(configured?'ok':'warn')}
async function load(){try{let r=await fetch('/api/security/status-phase44',{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw new Error(d.error||'Lecture impossible');let admin=(d.profiles||[]).find(p=>p.key==='ADMIN');let tech=(d.profiles||[]).find(p=>p.key==='CAISSE');setState('admin-state',!!(admin&&admin.configured));setState('tech-state',!!(tech&&tech.configured));}catch(e){document.getElementById('msg').textContent='Erreur : '+e.message}}load();
</script></body></html>'''
        return Response(html, content_type="text/html; charset=utf-8")
