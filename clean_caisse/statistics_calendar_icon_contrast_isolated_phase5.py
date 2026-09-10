"""Phase 5 — contraste de l'icône calendrier des statistiques.

INACTIF : module volontairement non importé/non enregistré dans wsgi_caisse.py.
Aucune donnée, aucun calcul, aucun endpoint métier, aucun Z n'est modifié.
"""


def register_statistics_calendar_icon_contrast_isolated_phase5(app):
    @app.after_request
    def statistics_calendar_icon_contrast_phase5(response):
        if response.status_code != 200:
            return response
        if not response.content_type or "text/html" not in response.content_type:
            return response

        from flask import request
        if request.path != "/statistiques":
            return response

        html = response.get_data(as_text=True)
        marker = "</head>"
        if marker not in html:
            return response

        patch = r'''<style id="phase5-calendar-icon-contrast">
/* Icône calendrier native : noire sur les champs clairs pour rester visible. */
#start::-webkit-calendar-picker-indicator,
#end::-webkit-calendar-picker-indicator{
  filter:none!important;
  opacity:1!important;
}
/* Bouton calendrier ajouté par Phase 5 : fond clair + pictogramme bien contrasté. */
.phase5-date-btn{
  background:#ffffff!important;
  border:1px solid #cbd5e1!important;
  border-radius:7px!important;
  color:#111827!important;
  opacity:1!important;
}
.phase5-date-btn:disabled{opacity:.45!important}
</style>'''
        response.set_data(html.replace(marker, patch + marker, 1))
        response.headers["Content-Length"] = len(response.get_data())
        return response
