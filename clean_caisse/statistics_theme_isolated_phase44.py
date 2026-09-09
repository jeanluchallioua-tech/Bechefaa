"""Phase 4.4 — charte graphique statistiques BÉCHÉFAA isolée.

IMPORTANT : ce module n'est volontairement ni importé ni enregistré dans
wsgi_caisse.py. Il prépare uniquement la future refonte visuelle de
/statistiques. Aucune requête métier, aucune écriture, aucun Z.
"""


def register_statistics_theme_isolated_phase44(app):
    """Prépare la charte BÉCHÉFAA ; inactive tant qu'elle n'est pas enregistrée."""

    @app.after_request
    def inject_statistics_theme_phase44(response):
        if response.status_code != 200:
            return response
        if not response.content_type or 'text/html' not in response.content_type:
            return response

        from flask import request
        if request.path != '/statistiques':
            return response

        html = response.get_data(as_text=True)
        marker = '</body>'
        if marker not in html:
            return response

        patch = r'''
<style id="phase44-bechefaa-theme">
:root{
  --bc-bg:#07111f;
  --bc-panel:#0d1b2b;
  --bc-panel-2:#12243a;
  --bc-border:#20364f;
  --bc-text:#f8fafc;
  --bc-muted:#94a3b8;
  --bc-red:#ff3b30;
  --bc-orange:#ff8a00;
  --bc-yellow:#ffd60a;
  --bc-green:#22c55e;
  --bc-cyan:#00d4ff;
  --bc-blue:#3b82f6;
  --bc-purple:#a855f7;
  --bc-pink:#ff2d95;
}
body{background:radial-gradient(circle at 80% 0%,#102944 0,#07111f 34%,#050b14 100%)!important;color:var(--bc-text)!important;min-height:100vh}
.w{max-width:1180px!important;margin:0 auto!important;padding:30px 22px 38px!important}
h1{font-size:30px!important;letter-spacing:-.5px!important;margin:0 0 8px!important;color:#fff!important}
h2{color:#fff!important;font-size:18px!important}.muted{color:var(--bc-muted)!important}
.filters{background:#0b1726!important;border:1px solid var(--bc-border)!important;border-radius:18px!important;padding:14px!important;box-shadow:0 14px 40px #0005!important}
select,input,button{background:#102238!important;color:#fff!important;border:1px solid #29425f!important;border-radius:11px!important}
button{background:linear-gradient(135deg,#ff3b30,#ff6a00)!important;border:0!important;box-shadow:0 8px 22px #ff3b3038!important}
.cards{gap:14px!important}
.card,.box,.phase44-donut-card,.phase44-curve-card{background:linear-gradient(160deg,#102238,#0b1726)!important;border:1px solid var(--bc-border)!important;box-shadow:0 14px 34px #0004!important;color:#fff!important}
.card{position:relative!important;overflow:hidden!important;min-height:112px!important}
.card:before{content:'';position:absolute;left:0;top:0;bottom:0;width:5px;border-radius:15px 0 0 15px}
.card:nth-child(1):before{background:var(--bc-cyan)}.card:nth-child(2):before{background:var(--bc-orange)}.card:nth-child(3):before{background:var(--bc-purple)}.card:nth-child(4):before{background:var(--bc-red)}.card:nth-child(5):before{background:var(--bc-green)}
.card:nth-child(1){background:linear-gradient(145deg,#0d2940,#0b1726)!important}.card:nth-child(2){background:linear-gradient(145deg,#39230d,#0b1726)!important}.card:nth-child(3){background:linear-gradient(145deg,#2c1640,#0b1726)!important}.card:nth-child(4){background:linear-gradient(145deg,#3b1719,#0b1726)!important}.card:nth-child(5){background:linear-gradient(145deg,#12331f,#0b1726)!important}
.lab{color:#b7c4d3!important;letter-spacing:.45px!important}.v{color:#fff!important;font-size:28px!important}
.row{border-bottom:1px solid #20364f!important}.row span{color:#dbe6f3!important}.row b{color:#fff!important}
.warn{background:#241d0c!important;border:1px solid #5d4a12!important;color:#ffd76a!important}
#phase44-donuts,#phase44-curves{max-width:1180px!important}.phase44-donut-card h2,.phase44-curve-card h2{color:#fff!important}
.phase44-donut:after{background:#0d1b2b!important;box-shadow:inset 0 0 0 1px #20364f!important}.phase44-donut-name{color:#dbe6f3!important}.phase44-donut-value{color:#fff!important}.phase44-donut-empty,.phase44-curve-empty{color:#94a3b8!important}
.phase44-curve-grid{stroke:#20364f!important}.phase44-curve-axis{stroke:#52677e!important}.phase44-curve-line{stroke:#00d4ff!important;filter:drop-shadow(0 0 5px #00d4ff66)}.phase44-curve-point{fill:#ff3b30!important;stroke:#fff!important;stroke-width:1.5}.phase44-curve-label{fill:#94a3b8!important}.phase44-curve-value{fill:#fff!important}
@media(max-width:800px){.w{padding:20px 12px!important}.cards{grid-template-columns:1fr 1fr!important}}
</style>
'''
        response.set_data(html.replace(marker, patch + marker))
        response.headers['Content-Length'] = len(response.get_data())
        return response
