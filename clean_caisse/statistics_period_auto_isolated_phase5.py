"""Phase 5 — filtres statistiques automatiques isolés.

INACTIF : ce module n'est ni importé ni enregistré dans wsgi_caisse.py.
Il ne modifie ni les calculs statistiques, ni les endpoints, ni la caisse Z.
Objectif : Aujourd'hui / Cette semaine / Ce mois se rechargent automatiquement ;
le bouton Afficher reste réservé à la période personnalisée.
"""


def register_statistics_period_auto_isolated_phase5(app):
    @app.after_request
    def statistics_period_auto_phase5(response):
        if response.status_code != 200:
            return response
        if not response.content_type or "text/html" not in response.content_type:
            return response

        from flask import request
        if request.path != "/statistiques":
            return response

        html = response.get_data(as_text=True)
        marker = "</body>"
        if marker not in html or 'id="period"' not in html:
            return response

        patch = r'''
<script id="phase5-statistics-period-auto">
(function(){
  const period=document.getElementById('period');
  const start=document.getElementById('start');
  const end=document.getElementById('end');
  if(!period) return;

  const filters=period.closest('.filters');
  const displayButton=filters ? filters.querySelector('button') : null;

  function refreshFilterState(){
    const custom=period.value==='custom';
    if(start) start.disabled=!custom;
    if(end) end.disabled=!custom;
    if(displayButton) displayButton.style.display=custom ? '' : 'none';
  }

  period.onchange=function(){
    refreshFilterState();
    if(period.value!=='custom' && typeof window.load==='function'){
      window.load();
    } else if(period.value!=='custom') {
      try { load(); } catch(e) {}
    }
  };

  refreshFilterState();
})();
</script>
'''
        response.set_data(html.replace(marker, patch + marker, 1))
        response.headers["Content-Length"] = len(response.get_data())
        return response
