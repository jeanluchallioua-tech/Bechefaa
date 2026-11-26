"""Read-only Google Ads administration, isolated from checkout and POS."""
from flask import Response, request, session, redirect, render_template_string
from .google_ads_reporting import report

LINKS = (
    ("Commande en ligne", "/"),
    ("Découvrez notre carte", "/notre-carte"),
    ("Nos burgers casher", "/burgers"),
    ("Sandwichs et shawarmas", "/sandwichs-shawarma"),
    ("Nos assiettes casher", "/assiettes"),
    ("Contact et horaires", "/contact"),
)

PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Google Ads</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f7fb;color:#14213d;font:16px Arial,sans-serif}
header{background:#111;color:#f0bd45;padding:20px}header a{color:white;float:right}
main{max-width:1100px;margin:auto;padding:22px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px}
article,section{background:white;border:1px solid #e5eaf1;border-radius:14px;padding:20px;margin-bottom:16px}
article small{color:#607086}article strong{display:block;font-size:26px;margin-top:12px}
h1,h2{margin-top:0}li{margin:12px 0}a{color:#145bb0}code{overflow-wrap:anywhere}
</style></head><body><header>BÉCHÉFAA • Administration <a href="/administration">Retour</a></header>
<main><h1>Google Ads</h1><p>Suivi publicitaire en lecture seule. Les données non disponibles ne sont pas assimilées à zéro.</p>
<div class="grid"><article><small>Budget journalier de référence (manuel)</small><strong>10 €</strong></article>
{% for label in metrics %}<article><small>{{ label }}</small><strong>{{ values[label] if values else "—" }}</strong><small>{{ "14 derniers jours complets" if values else "API non connectée ou données indisponibles" }}</small></article>{% endfor %}</div>
<section><h2>Diagnostic technique</h2><p>Conteneur prévu : <code>GTM-5CLSV6BG</code></p>
<p>Destination prévue : <code>AW-18595709642</code></p><p>Événement : <code>bechefaa_purchase</code></p>
<p>Configuration de référence uniquement : la réception effective des achats et le consentement restent à vérifier.</p>
<p>API Google Ads : {{ api_status }}</p><p><a href="https://ads.google.com/" target="_blank" rel="noopener noreferrer">Ouvrir Google Ads</a></p></section>
<section><h2>Liens publicitaires</h2><ul>{% for label,path in links %}<li><a href="https://www.bechefaa.fr{{ path }}" target="_blank" rel="noopener noreferrer">{{ label }}</a></li>{% endfor %}</ul></section>
</main></body></html>"""

def register_google_ads_admin(app):
    @app.get("/administration/google-ads")
    def google_ads_admin():
        if session.get("caisse_auth") is not True:
            return redirect("/", code=303)
        status, data = report()
        values = None if data is None else {label: ("—" if value is None else (f"{value:.2f}" + (" ×" if label == "ROAS" else "" if label == "Conversions attribuées" else " €")).replace(".", ",")) for label, value in data.items()}
        response = Response(render_template_string(PAGE, links=LINKS, values=values,
            metrics=("Dépenses", "Conversions attribuées", "Valeur des conversions", "Coût par acquisition", "Panier moyen attribué", "ROAS"),
            api_status=status), content_type="text/html; charset=utf-8")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.after_request
    def google_ads_card(response):
        if request.path != "/administration" or response.status_code != 200 or response.mimetype != "text/html" or session.get("caisse_auth") is not True:
            return response
        html = response.get_data(as_text=True)
        marker = '<a class="card" href="/administration/publicite-site">'
        if marker in html and '/administration/google-ads' not in html:
            card = '<a class="card" href="/administration/google-ads"><div class="icon">📊</div><b>Google Ads</b><span>Suivi des performances publicitaires.</span></a>'
            response.set_data(html.replace(marker, card + marker, 1))
        return response
