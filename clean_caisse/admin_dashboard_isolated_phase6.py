"""Phase 6 — tableau de bord Administration BÉCHÉFAA.

Point d'entrée isolé et en lecture seule vers les modules déjà validés.
Aucune logique métier de caisse, paiement, cuisine, catalogue ou Z n'est modifiée.
"""
from flask import Response, request
import re

BECHÉFAA_GOLD = "#d99a18"
BECHÉFAA_GOLD_DARK = "#8c5b08"


def register_admin_dashboard_isolated_phase6(app):
    @app.after_request
    def admin_navigation_phase6(response):
        """Uniformise la navigation des écrans de gestion sans toucher au métier."""
        if response.status_code != 200 or response.mimetype != "text/html":
            return response

        path = request.path
        is_admin_module = (
            path.startswith("/administration/")
            or path.startswith("/parametres")
            or path.startswith("/securite")
            or path.startswith("/clients")
            or path.startswith("/historique-modification")
            or path.startswith("/statistiques")
            or path.startswith("/maintenance/phase44/cash-")
            or path.startswith("/caisse/x")
            or path.startswith("/caisse/z")
        )
        if not is_admin_module:
            return response

        html = response.get_data(as_text=True)
        if "admin-global-nav-phase6" in html:
            return response

        html = re.sub(
            r'<a\b[^>]*href\s*=\s*["\']/(?:administration|pos)["\'][^>]*>.*?</a>',
            '', html, flags=re.I | re.S
        )

        addon = r'''
<style>
.admin-global-nav-phase6{position:fixed;top:10px;right:12px;z-index:99999;display:flex;gap:8px;align-items:center}
.admin-global-nav-phase6 a{display:inline-flex;align-items:center;justify-content:center;min-height:40px;padding:8px 12px;border:1px solid #d99a18;border-radius:8px;background:#111;color:#f0bd45!important;text-decoration:none!important;font:800 13px Arial,sans-serif;box-shadow:0 2px 8px #0005}
.admin-global-nav-phase6 a:hover{background:#d99a18;color:#111!important}
body > header, body > .top, header.top, .topbar{background:#111!important;border-bottom:1px solid rgba(217,154,24,.55)!important}
@media(max-width:620px){.admin-global-nav-phase6{top:6px;right:6px;gap:5px}.admin-global-nav-phase6 a{min-height:36px;padding:6px 9px;font-size:12px}}
</style>
<nav class="admin-global-nav-phase6" aria-label="Navigation administration"><a href="/administration">Administration</a><a href="/pos">Caisse</a></nav>
'''
        html = html.replace("<body>", "<body>" + addon, 1)
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response

    @app.get("/administration")
    def admin_dashboard_phase6():
        html = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Administration</title><style>
*{box-sizing:border-box}body{margin:0;background:#070707;color:#f7f7f7;font-family:Arial,sans-serif}.top{position:sticky;top:0;z-index:50;background:#0b0b0b;border-bottom:1px solid rgba(217,154,24,.6);padding:14px 22px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}.top b{font-size:21px;color:#f0bd45;letter-spacing:.2px}.top .spacer{flex:1}.top a{color:#f0bd45;text-decoration:none;background:#141414;border:1px solid #d99a18;padding:9px 12px;border-radius:8px;font-weight:800}.top a:hover{background:#d99a18;color:#111}.wrap{max-width:1240px;margin:0 auto;padding:24px 18px 42px}.hero{position:relative;overflow:hidden;background:linear-gradient(135deg,#161616,#090909);border:1px solid rgba(217,154,24,.55);border-radius:18px;padding:24px;margin-bottom:18px;box-shadow:0 12px 30px #0008}.hero:after{content:'';position:absolute;width:260px;height:260px;border-radius:50%;right:-80px;top:-110px;background:radial-gradient(circle,rgba(217,154,24,.24),transparent 68%)}.hero h1{position:relative;z-index:1;margin:0 0 7px;font-size:31px;color:#fff}.hero p{position:relative;z-index:1;margin:0;color:#b9b9b9}.status{position:relative;z-index:1;display:inline-flex;align-items:center;gap:7px;margin-top:14px;padding:7px 10px;border:1px solid rgba(217,154,24,.35);border-radius:99px;background:#111;font-size:13px;font-weight:800;color:#ddd}.dot{width:9px;height:9px;border-radius:50%;background:#22c55e;box-shadow:0 0 9px #22c55e88}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:12px}.metric{background:#111;border:1px solid #252525;border-radius:14px;padding:17px;box-shadow:0 5px 18px #0005}.metric.main{border-color:rgba(217,154,24,.55)}.metric .label{font-size:11px;text-transform:uppercase;color:#9a9a9a;font-weight:900;letter-spacing:.6px}.metric .value{font-size:25px;font-weight:900;margin-top:7px;color:#fff}.metric.main .value{color:#f0bd45}.payment-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:22px}.payment-metric{display:flex;align-items:center;gap:12px;background:#0d0d0d;border:1px solid #202020;border-radius:12px;padding:13px 14px}.payment-icon{width:38px;height:38px;display:grid;place-items:center;border-radius:10px;border:1px solid #d99a18;color:#f0bd45;font-size:19px;flex:0 0 auto}.payment-text{min-width:0}.payment-text small{display:block;color:#8e8e8e;font-size:11px;text-transform:uppercase;font-weight:900}.payment-text b{display:block;color:#fff;font-size:18px;margin-top:3px}.section-title{display:flex;align-items:center;gap:10px;margin:27px 0 11px;font-size:20px;color:#fff}.section-title:after{content:'';height:1px;background:linear-gradient(90deg,rgba(217,154,24,.6),transparent);flex:1}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.card{display:block;background:#101010;color:#f7f7f7;text-decoration:none;border:1px solid #262626;border-radius:15px;padding:18px;min-height:125px;box-shadow:0 4px 16px #0005;transition:.15s transform,.15s border-color,.15s background}.card:hover{transform:translateY(-2px);border-color:#d99a18;background:#151515}.icon{font-size:25px;margin-bottom:9px}.card b{display:block;font-size:17px;margin-bottom:5px;color:#fff}.card span{display:block;color:#9d9d9d;font-size:13px;line-height:1.4}.danger{border-color:#5c2020}.danger b{color:#ff8b8b}.cash{border-color:#5f4715}.cash b{color:#f0bd45}.note{margin-top:22px;background:#0e0e0e;border:1px solid #242424;border-left:4px solid #d99a18;border-radius:10px;padding:13px 15px;color:#999;font-size:13px}.note b{color:#f0bd45}@media(max-width:950px){.metrics,.payment-metrics{grid-template-columns:1fr 1fr}.grid{grid-template-columns:1fr 1fr}}@media(max-width:620px){.metrics,.payment-metrics,.grid{grid-template-columns:1fr}.hero h1{font-size:25px}.wrap{padding:16px 12px 28px}.top{padding:12px 10px}.top b{font-size:18px}.top a{padding:8px 9px;font-size:12px}}
</style></head><body><header class="top"><b>BÉCHÉFAA • Administration</b><span class="spacer"></span><a href="/pos">Caisse</a><a href="/cuisine">Cuisine</a></header><main class="wrap"><section class="hero"><h1>Tableau de bord Administration</h1><p>Gestion centrale de BÉCHÉFAA-Caisse et suivi de l'activité du jour.</p><div class="status"><span class="dot"></span><span id="dbstate">PostgreSQL • vérification…</span></div></section><section class="metrics"><div class="metric main"><div class="label">Commandes aujourd'hui</div><div class="value" id="mOrders">—</div></div><div class="metric main"><div class="label">CA commandes</div><div class="value" id="mGross">—</div></div><div class="metric"><div class="label">Panier moyen</div><div class="value" id="mAvg">—</div></div><div class="metric"><div class="label">Net encaissé</div><div class="value" id="mNet">—</div></div></section><section class="payment-metrics"><div class="payment-metric"><div class="payment-icon">💶</div><div class="payment-text"><small>Espèces</small><b id="mCash">—</b></div></div><div class="payment-metric"><div class="payment-icon">💳</div><div class="payment-text"><small>Carte bancaire</small><b id="mCard">—</b></div></div><div class="payment-metric"><div class="payment-icon">🎫</div><div class="payment-text"><small>Titres restaurant</small><b id="mTR">—</b></div></div><div class="payment-metric"><div class="payment-icon">🌐</div><div class="payment-text"><small>Commandes Site</small><b id="mSite">—</b></div></div></section><h2 class="section-title">Gestion</h2><section class="grid"><a class="card" href="/administration/produits"><div class="icon">🍔</div><b>Produits / Carte</b><span>Créer, modifier et activer les produits du catalogue.</span></a><a class="card" href="/administration/categories"><div class="icon">🗂️</div><b>Catégories</b><span>Ajouter et renommer les catégories. Suppression autorisée uniquement pour une catégorie vide.</span></a><a class="card" href="/administration/options-produits"><div class="icon">⚙️</div><b>Options & suppléments</b><span>Groupes, choix, règles et prix des options produits.</span></a><a class="card" href="/clients"><div class="icon">👤</div><b>Clients</b><span>Rechercher et modifier les fiches clients.</span></a><a class="card" href="/historique-modification"><div class="icon">🧾</div><b>Commandes / Historique</b><span>Consulter l'historique et accéder aux commandes modifiables.</span></a><a class="card" href="/historique-modification"><div class="icon">💳</div><b>Paiements / Remboursements</b><span>Consulter les paiements et gérer les remboursements depuis l'historique.</span></a><a class="card" href="/statistiques"><div class="icon">📊</div><b>Statistiques / Rapports</b><span>CA, panier moyen, remboursements, produits et canaux de vente.</span></a><a class="card" href="/administration/export-comptable"><div class="icon">📄</div><b>Export comptable mensuel</b><span>Choisir un mois, contrôler les chiffres et télécharger le PDF comptable.</span></a><a class="card" href="/administration/livraison"><div class="icon">🛵</div><b>Zones de livraison</b><span>Gérer les villes autorisées et le minimum de commande par zone.</span></a></section><h2 class="section-title">Caisse & clôture</h2><section class="grid"><a class="card cash" href="/maintenance/phase44/cash-float-opening"><div class="icon">💶</div><b>Fond de caisse</b><span>Enregistrer le fond d'ouverture de la journée.</span></a><a class="card cash" href="/maintenance/phase44/cash-count-save"><div class="icon">🪙</div><b>Comptage espèces</b><span>Enregistrer le comptage réel des espèces avant clôture.</span></a><a class="card" href="/caisse/x"><div class="icon">🧮</div><b>X de caisse</b><span>État intermédiaire en lecture seule, sans clôturer.</span></a><a class="card danger" href="/caisse/z"><div class="icon">🔒</div><b>Z de fin de journée</b><span>Clôture définitive après contrôle des commandes et espèces.</span></a><a class="card" href="/caisse/z/archive"><div class="icon">📚</div><b>Archives Z</b><span>Consulter et imprimer les clôtures déjà enregistrées.</span></a></section><h2 class="section-title">Paramètres</h2><section class="grid"><a class="card" href="/parametres"><div class="icon">🖨️</div><b>Matériel</b><span>Imprimante, tiroir-caisse et configuration du poste.</span></a><a class="card" href="/parametres/restaurant"><div class="icon">🏪</div><b>Restaurant</b><span>Identité commerciale et informations administratives.</span></a><a class="card" href="/administration/canaux-vente"><div class="icon">🧭</div><b>Canaux de vente</b><span>Restaurant, Site, Uber Eats et Deliveroo.</span></a><a class="card" href="/securite"><div class="icon">🔐</div><b>Sécurité / Accès</b><span>Configurer les codes PIN et ouvrir la zone interne protégée.</span></a><a class="card" href="/administration/utilisateurs"><div class="icon">👥</div><b>Utilisateurs / Profils</b><span>Contrôler l'état des accès Administrateur et Technicien.</span></a><a class="card" href="/administration/audit"><div class="icon">🧾</div><b>Journal d'audit</b><span>Consulter la traçabilité des actions sensibles après authentification PIN.</span></a></section><div class="note"><b>Dashboard Administration.</b> Les indicateurs affichés sont en lecture seule. Cette finition ne modifie ni les paiements, ni l'historique, ni la cuisine, ni le Z de caisse.</div></main><script>
const euro=n=>Number(n||0).toLocaleString('fr-FR',{style:'currency',currency:'EUR'});
const norm=s=>(s||'').toString().normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase().trim();
function methodTotal(methods,names){return (methods||[]).filter(x=>names.includes(norm(x.method))).reduce((s,x)=>s+Number(x.net||0),0)}
function sourceTotal(sources,names){return (sources||[]).filter(x=>names.some(n=>norm(x.source).includes(n))).reduce((s,x)=>s+Number(x.total||0),0)}
async function loadDashboard(){try{let h=await fetch('/api/health',{cache:'no-store'}),hd=await h.json();document.getElementById('dbstate').textContent=(h.ok&&hd.ok?'PostgreSQL • opérationnel':'Service à vérifier')}catch(e){document.getElementById('dbstate').textContent='Service à vérifier'}try{let r=await fetch('/api/statistics/today-phase44?period=today',{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Erreur');document.getElementById('mOrders').textContent=d.orders.count;document.getElementById('mGross').textContent=euro(d.orders.gross_total);document.getElementById('mAvg').textContent=euro(d.orders.average_ticket);document.getElementById('mNet').textContent=euro(d.cashflow.net);document.getElementById('mCash').textContent=euro(methodTotal(d.methods,['ESPECES','ESPECE','CASH']));document.getElementById('mCard').textContent=euro(methodTotal(d.methods,['CB','CARTE','CARTE BANCAIRE','CARD']));document.getElementById('mTR').textContent=euro(methodTotal(d.methods,['TITRE RESTAURANT','TITRES RESTAURANT','TICKET RESTAURANT','TICKETS RESTAURANT']));document.getElementById('mSite').textContent=euro(sourceTotal(d.sources,['SITE','WEB','WIX']))}catch(e){['mOrders','mGross','mAvg','mNet','mCash','mCard','mTR','mSite'].forEach(id=>document.getElementById(id).textContent='—')}}loadDashboard();
</script></body></html>'''
        return Response(html, content_type="text/html; charset=utf-8")
