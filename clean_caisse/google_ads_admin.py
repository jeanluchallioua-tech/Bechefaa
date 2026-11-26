"""Read-only Google Ads administration, isolated from checkout and POS."""
from flask import Response, request, session, redirect, render_template_string
from .google_ads_reporting import report, PERIODS
from .google_ads_site_sales import site_sales

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
form{display:flex;align-items:end;gap:12px;flex-wrap:wrap;margin-bottom:16px}form label{display:grid;gap:6px}form input,form select,form button{font:inherit;padding:9px;border:1px solid #cbd5e1;border-radius:8px}form button{background:#14213d;color:white;cursor:pointer}
</style></head><body><header>BÉCHÉFAA • Administration <a href="/administration">Retour</a></header>
<main><h1>Google Ads</h1><p>Suivi publicitaire en lecture seule. Les données non disponibles ne sont pas assimilées à zéro.</p>
<section><form method="get" action="/administration/google-ads"><label>Période<select name="period" id="ads-period">{% for key,label in periods.items() %}<option value="{{ key }}"{% if key == period %} selected{% endif %}>{{ label }}</option>{% endfor %}</select></label><label>Du (personnalisée)<input type="date" name="start" value="{{ start }}"></label><label>Au (personnalisée)<input type="date" name="end" value="{{ end }}"></label><button type="submit">Actualiser</button></form><p>{{ api_status }}</p></section>
<section><h2>Résultats commerciaux du site internet</h2>
<p>Encaissements du canal SITE, indépendamment des cookies. Les ventes globales du site ne sont pas toutes attribuables à Google Ads.</p>
{% if sales is not none %}
<div class="grid">
{% for label,value,unit in [('Commandes avec encaissement',sales.count,''),('Encaissements TTC',sales.paid,' €'),('Remboursements',sales.refunds,' €'),('Net encaissé TTC',sales.net,' €'),('Encaissement moyen par commande',sales.average,' €'),('Dépenses Google Ads',cost,' €'),('Net encaissé / dépenses',ratio,' ×')] %}
<article><small>{{ label }}</small><strong{% if label == 'Net encaissé TTC' %} style="color:#15803d"{% endif %}>{{ ('%.2f'|format(value)|replace('.',',') ~ unit) if value is not none and unit else (value if value is not none else '—') }}</strong></article>
{% endfor %}</div>
<p>Ratio global, non attribué à la publicité ; il ne constitue ni une marge ni un bénéfice. Les paiements et remboursements sont comptés à leur date de transaction.</p>
<h3>Évolution quotidienne : ventes nettes et dépenses</h3>
<p><span style="color:#15803d">● Ventes nettes du site</span> · <span style="color:#2563eb">● Dépenses Google Ads</span></p>
{% if costs is none %}<p>Détail quotidien des dépenses indisponible.</p>{% endif %}
<div style="overflow-x:auto"><svg viewBox="0 0 650 170" style="width:100%;min-width:500px" role="img" aria-label="Évolution des ventes nettes et dépenses publicitaires">
<line x1="30" y1="75" x2="630" y2="75" stroke="#94a3b8"/>
<polyline points="{{ sales_points }}" fill="none" stroke="#15803d" stroke-width="2"/>
{% if costs is not none %}<polyline points="{{ cost_points }}" fill="none" stroke="#2563eb" stroke-width="2"/>{% endif %}
{% for day in sales.days %}<circle cx="{{ 30+600*loop.index0/[sales.days|length-1,1]|max }}" cy="{{ 75-65*day.net/sales_max }}" r="3" fill="#15803d"><title>{{ day.date }} : {{ '%.2f'|format(day.net) }} €</title></circle>
{% if costs is not none %}<circle cx="{{ 30+600*loop.index0/[sales.days|length-1,1]|max }}" cy="{{ 75-65*costs.get(day.date,0)/sales_max }}" r="3" fill="#2563eb"><title>{{ day.date }} : {{ '%.2f'|format(costs.get(day.date,0)) }} €</title></circle>{% endif %}{% endfor %}
<text x="30" y="158" font-size="12">{{ sales.days[0].date }}</text><text x="630" y="158" text-anchor="end" font-size="12">{{ sales.days[-1].date }}</text></svg></div>
{% else %}<p>Encaissements du site indisponibles pour cette période.</p>{% endif %}
</section>
<section><h2>Suivi budgétaire du mois en cours</h2>
{% if budget %}<div class="grid">
{% for label,key in [('Budget quotidien réel','daily'),('Dépenses du mois','spent'),('Budget mensuel indicatif','reference'),('Reste indicatif','remaining'),('Moyenne quotidienne du mois','average'),('Dépenses aujourd’hui','today')] %}<article><small>{{ label }}</small><strong>{{ '%.2f'|format(budget[key])|replace('.',',') }} €</strong></article>{% endfor %}</div>
{% if budget.today > budget.daily %}<p style="color:#a16207;font-weight:bold">Aujourd’hui : dépenses supérieures au budget quotidien moyen.</p>{% endif %}
<p>Estimation mensuelle sur la base du budget actuel × 30,4 ; ce n’est pas le plafond de facturation garanti en cas de modification du budget ou de démarrage en cours de mois. La moyenne inclut tous les jours écoulés du mois.</p>
<h3>Dépenses jour par jour</h3><div style="overflow-x:auto"><svg viewBox="0 0 650 150" style="width:100%;min-width:500px" role="img" aria-label="Courbe des dépenses quotidiennes">
<line x1="30" y1="110" x2="630" y2="110" stroke="#94a3b8"/>
<line x1="30" y1="{{ 110-90*budget.daily/chart_max }}" x2="630" y2="{{ 110-90*budget.daily/chart_max }}" stroke="#b45309" stroke-dasharray="4 4"/>
<polyline points="{{ points }}" fill="none" stroke="#2563eb" stroke-width="2"/>
{% for day in budget.days %}<circle cx="{{ 30+600*loop.index0/[budget.days|length-1,1]|max }}" cy="{{ 110-90*day.cost/chart_max }}" r="3" fill="#2563eb"><title>{{ day.date }} : {{ '%.2f'|format(day.cost) }} €</title></circle>{% endfor %}
<text x="30" y="130" font-size="12">{{ budget.days[0].date }}</text><text x="630" y="130" text-anchor="end" font-size="12">{{ budget.days[-1].date }}</text></svg></div>
{% else %}<p>Budget réel indisponible : aucune estimation affichée.</p>{% endif %}</section>
<div class="grid">
{% for label in metrics %}<article><small>{{ label }}</small><strong>{{ values.get(label, "—") if values else "—" }}</strong><small>{{ periods.get(period, "Période invalide") if values else "API non connectée ou données indisponibles" }}</small></article>{% endfor %}</div>
<section><h2>Diagnostic technique</h2><p>Conteneur prévu : <code>GTM-5CLSV6BG</code></p>
<p>Destination prévue : <code>AW-18595709642</code></p><p>Événement : <code>bechefaa_purchase</code></p>
<p>Configuration de référence uniquement : la réception effective des achats et le consentement restent à vérifier.</p>
<p>API Google Ads : {{ api_status }}</p><p><a href="https://ads.google.com/" target="_blank" rel="noopener noreferrer">Ouvrir Google Ads</a></p></section>
<section><h2>Liens publicitaires</h2><ul>{% for label,path in links %}<li><a href="https://www.bechefaa.fr{{ path }}" target="_blank" rel="noopener noreferrer">{{ label }}</a></li>{% endfor %}</ul></section>
</main></body></html>"""

def register_google_ads_admin(app, db=None):
    @app.get("/administration/google-ads")
    def google_ads_admin():
        if session.get("caisse_auth") is not True:
            return redirect("/", code=303)
        period = request.args.get("period", "TODAY")
        start = request.args.get("start", "")
        end = request.args.get("end", "")
        status, data = report(period, start, end)
        sales = None
        try:
            if db is not None:
                sales = site_sales(db, period, start, end)
        except Exception:
            app.logger.exception("Site sales reporting unavailable")
        cost = data.get("Dépenses") if data else None
        costs = data.get("_daily_costs") if data else None
        ratio = sales["net"]/cost if sales is not None and cost else None
        days = sales["days"] if sales is not None else []
        sales_max = max([1] + [abs(d["net"]) for d in days] + [costs.get(d["date"],0) for d in days] if costs is not None else [1] + [abs(d["net"]) for d in days])
        def curve(values):
            return " ".join(f"{30+600*i/max(1,len(days)-1):.2f},{75-65*v/sales_max:.2f}" for i,v in enumerate(values))
        sales_points = curve([d["net"] for d in days])
        cost_points = curve([costs.get(d["date"],0) for d in days]) if costs is not None else ""
        budget = data.get("_budget") if data else None
        chart_max = max([1, budget["daily"]] + [d["cost"] for d in budget["days"]]) if budget else 1
        points = " ".join(f"{30+600*i/max(1,len(budget['days'])-1):.2f},{110-90*d['cost']/chart_max:.2f}" for i,d in enumerate(budget["days"])) if budget else ""
        values = None if data is None else {label: ("—" if value is None else ((f"{value:.0f}" if label in ("Impressions", "Clics") else f"{value:.2f}") + (" ×" if label == "ROAS" else "" if label in ("Conversions attribuées", "Impressions", "Clics") else " €")).replace(".", ",")) for label, value in data.items() if not label.startswith("_")}
        response = Response(render_template_string(PAGE, links=LINKS, values=values,
            periods=PERIODS, period=period, start=start, end=end, sales=sales, cost=cost, costs=costs, ratio=ratio, sales_max=sales_max, sales_points=sales_points, cost_points=cost_points, budget=budget, chart_max=chart_max, points=points,
            metrics=("Impressions", "Clics", "Coût moyen par clic", "Dépenses", "Conversions attribuées", "Valeur des conversions", "Coût par acquisition", "Panier moyen attribué", "ROAS"),
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
