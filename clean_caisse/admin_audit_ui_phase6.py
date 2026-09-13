"""Phase 6 — interface d'administration du journal d'audit.

Lecture seule. Réutilise l'API sécurisée /api/security/audit-phase44 existante.
Aucune écriture caisse, paiement, cuisine ou Z.
"""
from flask import Response


def register_admin_audit_ui_phase6(app):
    @app.get('/administration/audit')
    def admin_audit_ui_phase6():
        html = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Journal d'audit</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f5f7;color:#111827;font-family:Arial,sans-serif}.top{background:#111827;color:#fff;padding:15px 22px;display:flex;gap:10px;align-items:center}.top b{font-size:20px}.top a{margin-left:auto;color:#fff;text-decoration:none;background:#263244;padding:9px 12px;border-radius:8px;font-weight:800}.wrap{max-width:1050px;margin:28px auto;padding:0 16px}.box{background:#fff;border-radius:16px;padding:20px;box-shadow:0 4px 18px #0001}.muted{color:#667085;font-size:13px}.msg{padding:12px;border-radius:10px;background:#f3f4f6;font-weight:800;margin:14px 0}.event{display:grid;grid-template-columns:180px 1fr 170px 100px;gap:12px;padding:13px 0;border-top:1px solid #e5e7eb;align-items:center}.event:first-child{border-top:0}.action{font-weight:900}.user{font-weight:800}.ok{color:#027a48;font-weight:900}.ko{color:#b42318;font-weight:900}@media(max-width:760px){.event{grid-template-columns:1fr;gap:5px;padding:15px 0}}
</style></head><body><header class="top"><b>BÉCHÉFAA • Journal d'audit</b><a href="/administration">← Administration</a></header><main class="wrap"><div class="box"><h1>Traçabilité des actions</h1><p class="muted">Les opérations sensibles enregistrées par le système apparaissent ici. L'accès nécessite une session PIN active.</p><div id="msg" class="msg">Chargement…</div><div id="events"></div></div></main><script>
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function dateFr(ms){try{return new Date(Number(ms)).toLocaleString('fr-FR')}catch(e){return ''}}
async function load(){const msg=document.getElementById('msg'),events=document.getElementById('events');try{const r=await fetch('/api/security/audit-phase44',{cache:'no-store'}),d=await r.json();if(r.status===403){msg.innerHTML='Authentification PIN requise. <a href="/securite">Ouvrir la zone Sécurité / Accès</a>';return}if(!r.ok||!d.ok)throw new Error(d.error||'Journal indisponible');const rows=Array.isArray(d.events)?d.events:[];msg.textContent=rows.length?rows.length+' événement(s) affiché(s).':'Aucun événement enregistré.';events.innerHTML=rows.map(e=>'<div class="event"><div>'+esc(dateFr(e.created_at))+'</div><div class="action">'+esc(e.action)+'</div><div class="user">'+esc(e.user_label||'Non identifié')+'</div><div class="'+(Number(e.status_code)<400?'ok':'ko')+'">HTTP '+esc(e.status_code)+'</div></div>').join('')}catch(e){msg.textContent='Erreur : '+(e.message||'Journal indisponible')}}load();
</script></body></html>'''
        return Response(html, content_type='text/html; charset=utf-8')
