"""Phase 5 — amélioration visuelle isolée des graphiques circulaires statistiques.

INACTIF : ce module n'est ni importé ni enregistré dans wsgi_caisse.py.
Il ne touche pas aux requêtes, périodes, classements produits ni au noyau statistiques.
"""


def register_statistics_donuts_vivid_isolated_phase5(app):
    @app.after_request
    def statistics_donuts_vivid_phase5(response):
        if response.status_code != 200:
            return response
        if not response.content_type or "text/html" not in response.content_type:
            return response

        from flask import request
        if request.path != "/statistiques":
            return response

        html = response.get_data(as_text=True)
        if "phase44-donuts" not in html:
            return response

        # Palette plus franche et mieux différenciée pour la lecture immédiate
        # des parts, sans modifier les données ni le calcul des graphiques.
        old_palette = "const colors=['#143D53','#2E6F95','#4E9F3D','#F2A541','#C8553D','#7D5BA6','#2A9D8F','#E76F51'];"
        new_palette = "const colors=['#00C2FF','#FFB000','#22C55E','#FF4D6D','#8B5CF6','#F97316','#06B6D4','#EAB308'];"
        html = html.replace(old_palette, new_palette)

        # Renforcement purement visuel : anneau plus large, contraste des cartes,
        # pastilles et valeurs plus faciles à distinguer sur le thème sombre.
        marker = "</head>"
        patch = r'''
<style id="phase5-donuts-vivid">
#phase44-donuts{gap:22px}
.phase44-donut-card{border:1px solid rgba(255,255,255,.14)!important;box-shadow:0 10px 28px rgba(0,0,0,.22)!important}
.phase44-donut-card h2{font-weight:800!important;letter-spacing:-.2px}
.phase44-donut{box-shadow:0 0 0 1px rgba(255,255,255,.08),0 12px 30px rgba(0,0,0,.24)}
.phase44-donut:after{inset:54px!important;box-shadow:inset 0 0 0 1px rgba(255,255,255,.08)}
.phase44-donut-line{font-size:14px!important;gap:10px!important}
.phase44-donut-dot{width:14px!important;height:14px!important;border-radius:4px!important;box-shadow:0 0 0 1px rgba(255,255,255,.16)}
.phase44-donut-value{font-size:14px!important;font-weight:800!important}
@media(max-width:520px){.phase44-donut:after{inset:49px!important}}
</style>
'''
        if marker in html:
            html = html.replace(marker, patch + marker, 1)

        response.set_data(html)
        response.headers["Content-Length"] = len(response.get_data())
        return response
