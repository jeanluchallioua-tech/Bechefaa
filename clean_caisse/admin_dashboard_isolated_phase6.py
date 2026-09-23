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
        # Ces deux écrans sont intégrés en iframe dans Options & suppléments.
        # La navigation Administration / Caisse existe déjà sur la page parente.
        if path in ("/administration/options-ajout-test", "/administration/options-regles-test"):
            return response

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
*{box-sizing:border-box}
:root{--navy:#10243f;--navy2:#17385f;--gold:#d99a18;--ink:#14213d;--muted:#6b7a90;--line:#e5eaf1;--bg:#f4f7fb}
body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}
.top{position:sticky;top:0;z-index:50;min-height:66px;background:linear-gradient(135deg,var(--navy),#0b1a2d);border-bottom:1px solid #203d61;padding:13px 22px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;box-shadow:0 4px 18px #10243f22}
.top b{font-size:21px;color:#fff;letter-spacing:.2px}.top .spacer{flex:1}
.top a{color:#fff;text-decoration:none;background:#ffffff12;border:1px solid #ffffff2b;padding:9px 13px;border-radius:11px;font-weight:800}
.top a:hover{background:#fff;color:var(--navy)}
.wrap{max-width:1380px;margin:0 auto;padding:24px 20px 42px}
.hero{position:relative;overflow:hidden;background:linear-gradient(135deg,#fff,#f9fbff);border:1px solid var(--line);border-radius:20px;padding:24px;margin-bottom:18px;box-shadow:0 10px 28px #25466e12}
.hero:after{content:'';position:absolute;width:260px;height:260px;border-radius:50%;right:-80px;top:-110px;background:radial-gradient(circle,#2d77dd18,transparent 68%)}
.hero h1{position:relative;z-index:1;margin:0 0 7px;font-size:31px;color:var(--ink)}
.hero p{position:relative;z-index:1;margin:0;color:var(--muted)}
.status{position:relative;z-index:1;display:inline-flex;align-items:center;gap:7px;margin-top:14px;padding:7px 11px;border:1px solid #dce4ee;border-radius:99px;background:#f8fafc;font-size:13px;font-weight:800;color:#506078}
.dot{width:9px;height:9px;border-radius:50%;background:#22c55e;box-shadow:0 0 9px #22c55e66}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:12px}
.metric{background:#fff;border:1px solid var(--line);border-radius:16px;padding:17px;box-shadow:0 5px 18px #25466e0d}
.metric.main{border-color:#d8e5f7}.metric .label{font-size:11px;text-transform:uppercase;color:#8794a6;font-weight:900;letter-spacing:.6px}.metric .value{font-size:25px;font-weight:900;margin-top:7px;color:var(--ink)}.metric.main .value{color:#1769d2}
.payment-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}
.payment-metric{display:flex;align-items:center;gap:12px;background:#fff;border:1px solid var(--line);border-radius:14px;padding:13px 14px;box-shadow:0 4px 14px #25466e0b}
.payment-icon{width:40px;height:40px;display:grid;place-items:center;border-radius:12px;background:linear-gradient(145deg,#2f8eff,#1769d2);color:#fff;font-size:19px;flex:0 0 auto;box-shadow:0 5px 12px #1769d233}
.payment-text{min-width:0}.payment-text small{display:block;color:#8a97aa;font-size:11px;text-transform:uppercase;font-weight:900}.payment-text b{display:block;color:var(--ink);font-size:18px;margin-top:3px}
.section-title{display:flex;align-items:center;gap:10px;margin:26px 0 0;padding:17px 20px 0;background:#fff;border:1px solid var(--line);border-bottom:0;border-radius:20px 20px 0 0;font-size:20px;color:var(--ink)}
.section-title:after{content:'';height:1px;background:linear-gradient(90deg,#d9e2ee,transparent);flex:1}
.grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;background:#fff;border:1px solid var(--line);border-top:0;border-radius:0 0 20px 20px;padding:17px 14px 20px;margin-bottom:4px;box-shadow:0 8px 24px #25466e0c}
.card{display:flex;flex-direction:column;align-items:center;justify-content:flex-start;text-align:center;color:var(--ink);text-decoration:none;border:0;background:transparent;border-radius:18px;padding:8px 5px 10px;min-height:142px;transition:.16s transform,.16s background}
.card:hover{transform:translateY(-3px);background:#f7f9fc}
.icon{width:78px;height:78px;display:grid;place-items:center;border-radius:19px;margin:0 auto 10px;color:#fff;font-size:34px;line-height:1;box-shadow:0 9px 18px #243d6625,inset 0 1px 0 #ffffff66;background:linear-gradient(145deg,#2f8eff,#1769d2)}
.card:nth-child(5n+2) .icon{background:linear-gradient(145deg,#42d985,#10aa55)}
.card:nth-child(5n+3) .icon{background:linear-gradient(145deg,#bf62f4,#7c35d9)}
.card:nth-child(5n+4) .icon{background:linear-gradient(145deg,#ffb12c,#ff7a18)}
.card:nth-child(5n+5) .icon{background:linear-gradient(145deg,#ff6684,#e53459)}
.card b{display:block;font-size:14px;line-height:1.2;margin:0 0 5px;color:var(--ink);font-weight:850}
.card span{display:block;color:#718096;font-size:11.5px;line-height:1.28;max-width:155px}
.cash b,.danger b{color:var(--ink)}
.cash .icon{background:linear-gradient(145deg,#2fcf72,#0aa553)}
.danger .icon{background:linear-gradient(145deg,#ff607b,#d92d4f)}
.note{margin-top:22px;background:#fff;border:1px solid var(--line);border-left:4px solid var(--gold);border-radius:12px;padding:13px 15px;color:#7a8798;font-size:13px}.note b{color:var(--ink)}
@media(max-width:1100px){.grid{grid-template-columns:repeat(4,minmax(0,1fr))}}
@media(max-width:950px){.metrics,.payment-metrics{grid-template-columns:1fr 1fr}.grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:620px){.metrics,.payment-metrics{grid-template-columns:1fr 1fr}.grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;padding:14px 8px 17px}.card{min-height:132px}.icon{width:68px;height:68px;border-radius:17px;font-size:30px}.hero h1{font-size:25px}.wrap{padding:16px 10px 28px}.top{padding:12px 10px}.top b{font-size:18px}.top a{padding:8px 9px;font-size:12px}.section-title{padding:15px 14px 0}}
@media(max-width:390px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.card b{font-size:13px}.card span{font-size:11px}}
</style></head><body><header class="top"><b>BÉCHÉFAA • Administration</b><span class="spacer"></span><a href="/pos">Caisse</a><a href="/cuisine">Cuisine</a></header><main class="wrap"><section class="hero"><h1>Tableau de bord Administration</h1><p>Gestion centrale de BÉCHÉFAA-Caisse et suivi de l'activité du jour.</p><div class="status"><span class="dot"></span><span id="dbstate">PostgreSQL • vérification…</span></div></section><section class="metrics"><div class="metric main"><div class="label">Commandes aujourd'hui</div><div class="value" id="mOrders">—</div></div><div class="metric main"><div class="label">CA commandes</div><div class="value" id="mGross">—</div></div><div class="metric"><div class="label">Panier moyen</div><div class="value" id="mAvg">—</div></div><div class="metric"><div class="label">Net encaissé</div><div class="value" id="mNet">—</div></div></section><section class="payment-metrics"><div class="payment-metric"><div class="payment-icon">💶</div><div class="payment-text"><small>Espèces</small><b id="mCash">—</b></div></div><div class="payment-metric"><div class="payment-icon">💳</div><div class="payment-text"><small>Carte bancaire</small><b id="mCard">—</b></div></div><div class="payment-metric"><div class="payment-icon">🎫</div><div class="payment-text"><small>Titres restaurant</small><b id="mTR">—</b></div></div><div class="payment-metric"><div class="payment-icon">🌐</div><div class="payment-text"><small>Commandes Site</small><b id="mSite">—</b></div></div></section><h2 class="section-title">Gestion</h2><section class="grid"><a class="card" href="/administration/produits"><div class="icon">🍔</div><b>Produits / Carte</b><span>Gérer la carte et les produits.</span></a><a class="card" href="/administration/ordre-produits"><div class="icon">↕️</div><b>Ordre des produits</b><span>Classer les produits par catégorie.</span></a><a class="card" href="/administration/categories"><div class="icon">🗂️</div><b>Catégories</b><span>Organiser les catégories du menu.</span></a><a class="card" href="/administration/options-produits"><div class="icon">⚙️</div><b>Options & suppléments</b><span>Choix, règles et suppléments.</span></a><a class="card" href="/clients"><div class="icon">👤</div><b>Clients</b><span>Fiches et informations clients.</span></a><a class="card" href="/historique-modification"><div class="icon">🧾</div><b>Commandes / Historique</b><span>Suivi et historique des commandes.</span></a><a class="card" href="/historique-modification"><div class="icon">💳</div><b>Paiements / Remboursements</b><span>Paiements et remboursements.</span></a><a class="card" href="/statistiques"><div class="icon">📊</div><b>Statistiques / Rapports</b><span>Chiffres et rapports d'activité.</span></a><a class="card" href="/administration/export-comptable"><div class="icon">📄</div><b>Export comptable mensuel</b><span>Export PDF comptable mensuel.</span></a><a class="card" href="/administration/livraison"><div class="icon">🛵</div><b>Zones de livraison</b><span>Villes et minimums de livraison.</span></a></section><h2 class="section-title">Caisse & clôture</h2><section class="grid"><a class="card cash" href="/maintenance/phase44/cash-float-opening"><div class="icon">💶</div><b>Fond de caisse</b><span>Ouverture de caisse.</span></a><a class="card cash" href="/maintenance/phase44/cash-count-save"><div class="icon">🪙</div><b>Comptage espèces</b><span>Comptage avant clôture.</span></a><a class="card" href="/caisse/x"><div class="icon">🧮</div><b>X de caisse</b><span>État intermédiaire de caisse.</span></a><a class="card danger" href="/caisse/z"><div class="icon">🔒</div><b>Z de fin de journée</b><span>Clôture définitive de la journée.</span></a><a class="card" href="/caisse/z/archive"><div class="icon">📚</div><b>Archives Z</b><span>Historique des clôtures.</span></a></section><h2 class="section-title">Paramètres</h2><section class="grid"><a class="card" href="/parametres"><div class="icon">🖨️</div><b>Matériel</b><span>Imprimante et tiroir-caisse.</span></a><a class="card" href="/parametres/restaurant"><div class="icon">🏪</div><b>Restaurant</b><span>Identité du restaurant.</span></a><a class="card" href="/administration/canaux-vente"><div class="icon">🧭</div><b>Canaux de vente</b><span>Site et plateformes de vente.</span></a><a class="card" href="/securite"><div class="icon">🔐</div><b>Sécurité / Accès</b><span>Codes PIN et accès.</span></a><a class="card" href="/administration/utilisateurs"><div class="icon">👥</div><b>Utilisateurs / Profils</b><span>Comptes et profils utilisateurs.</span></a><a class="card" href="/administration/audit"><div class="icon">🧾</div><b>Journal d'audit</b><span>Traçabilité des actions.</span></a></section><div class="note"><b>Dashboard Administration.</b> Les indicateurs affichés sont en lecture seule. Cette finition ne modifie ni les paiements, ni l'historique, ni la cuisine, ni le Z de caisse.</div></main><script>
const euro=n=>Number(n||0).toLocaleString('fr-FR',{style:'currency',currency:'EUR'});
const norm=s=>(s||'').toString().normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase().trim();
function methodTotal(methods,names){return (methods||[]).filter(x=>names.includes(norm(x.method))).reduce((s,x)=>s+Number(x.net||0),0)}
function sourceTotal(sources,names){return (sources||[]).filter(x=>names.some(n=>norm(x.source).includes(n))).reduce((s,x)=>s+Number(x.total||0),0)}
async function loadDashboard(){try{let h=await fetch('/api/health',{cache:'no-store'}),hd=await h.json();document.getElementById('dbstate').textContent=(h.ok&&hd.ok?'PostgreSQL • opérationnel':'Service à vérifier')}catch(e){document.getElementById('dbstate').textContent='Service à vérifier'}try{let r=await fetch('/api/statistics/today-phase44?period=today',{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Erreur');document.getElementById('mOrders').textContent=d.orders.count;document.getElementById('mGross').textContent=euro(d.orders.gross_total);document.getElementById('mAvg').textContent=euro(d.orders.average_ticket);document.getElementById('mNet').textContent=euro(d.cashflow.net);document.getElementById('mCash').textContent=euro(methodTotal(d.methods,['ESPECES','ESPECE','CASH']));document.getElementById('mCard').textContent=euro(methodTotal(d.methods,['CB','CARTE','CARTE BANCAIRE','CARD']));document.getElementById('mTR').textContent=euro(methodTotal(d.methods,['TITRE RESTAURANT','TITRES RESTAURANT','TICKET RESTAURANT','TICKETS RESTAURANT']));document.getElementById('mSite').textContent=euro(sourceTotal(d.sources,['SITE','WEB','WIX']))}catch(e){['mOrders','mGross','mAvg','mNet','mCash','mCard','mTR','mSite'].forEach(id=>document.getElementById(id).textContent='—')}}loadDashboard();
</script></body></html>'''
        return Response(html, content_type="text/html; charset=utf-8")
