"""Phase 5 — correction isolée de visibilité des statistiques.

Objectifs strictement limités à /statistiques :
- rendre visibles les 4 canaux de vente Resto / Site internet / Uber Eats / Deliveroo ;
- corriger les cartes blanches des classements produits en thème sombre.
Aucun Z, aucun paiement, aucune écriture commande.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask import jsonify, request

PARIS = ZoneInfo("Europe/Paris")
UTC = ZoneInfo("UTC")
CHANNELS = ("RESTO", "SITE", "UBER_EATS", "DELIVEROO")
LABELS = {
    "RESTO": "Resto",
    "SITE": "Site internet",
    "UBER_EATS": "Uber Eats",
    "DELIVEROO": "Deliveroo",
}


def _bounds():
    today = datetime.now(PARIS).date()
    period = request.args.get("period", "today")
    if period == "week":
        start = today - timedelta(days=today.weekday())
        end = today + timedelta(days=1)
    elif period == "month":
        start = today.replace(day=1)
        end = today + timedelta(days=1)
    elif period == "custom":
        start = datetime.strptime(request.args.get("start", ""), "%Y-%m-%d").date()
        end = datetime.strptime(request.args.get("end", ""), "%Y-%m-%d").date() + timedelta(days=1)
    else:
        start = today
        end = today + timedelta(days=1)

    a = datetime.combine(start, time.min, PARIS)
    b = datetime.combine(end, time.min, PARIS)
    return int(a.astimezone(UTC).timestamp() * 1000), int(b.astimezone(UTC).timestamp() * 1000)


def register_statistics_visibility_fix_isolated_phase5(app, db):
    @app.get("/api/statistics/sales-channels-phase5")
    def statistics_sales_channels_visibility_phase5():
        try:
            start_ms, end_ms = _bounds()
            totals = {key: {"count": 0, "total": 0.0} for key in CHANNELS}

            with db() as conn:
                # Vérifie d'abord les colonnes disponibles pour ne jamais mettre
                # la transaction PostgreSQL en état aborted avec une requête test.
                column_rows = conn.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name='caisse_orders'
                      AND column_name IN ('sales_channel','cancellation_hidden')
                    """
                ).fetchall()
                columns = {str(row["column_name"]) for row in column_rows}
                has_sales_channel = "sales_channel" in columns
                has_cancellation_hidden = "cancellation_hidden" in columns

                channel_expr = (
                    "COALESCE(NULLIF(UPPER(sales_channel),''),'RESTO')"
                    if has_sales_channel else "'RESTO'"
                )
                cancel_filter = (
                    "AND COALESCE(cancellation_hidden,FALSE)=FALSE"
                    if has_cancellation_hidden else ""
                )

                rows = conn.execute(
                    f"""
                    SELECT {channel_expr} channel,
                           COUNT(*) count,
                           COALESCE(SUM(total),0) total
                    FROM caisse_orders
                    WHERE created_at >= %s AND created_at < %s
                      {cancel_filter}
                    GROUP BY 1
                    """,
                    (start_ms, end_ms),
                ).fetchall()

            for row in rows:
                key = str(row["channel"] or "RESTO").upper()
                if key not in totals:
                    key = "RESTO"
                totals[key]["count"] += int(row["count"] or 0)
                totals[key]["total"] += float(row["total"] or 0)

            return jsonify({
                "ok": True,
                "channels": [
                    {
                        "channel": key,
                        "label": LABELS[key],
                        "count": totals[key]["count"],
                        "total": totals[key]["total"],
                    }
                    for key in CHANNELS
                ],
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.after_request
    def statistics_visibility_fix_phase5(response):
        if request.path != "/statistiques" or response.status_code != 200:
            return response
        if not response.content_type or "text/html" not in response.content_type:
            return response

        html = response.get_data(as_text=True)
        if "phase5-statistics-visibility-fix" in html:
            return response

        patch = r'''
<style id="phase5-statistics-visibility-fix">
.phase44-rank-card{
  background:linear-gradient(160deg,#102238,#0b1726)!important;
  border:1px solid #20364f!important;
  box-shadow:0 14px 34px #0004!important;
  color:#fff!important;
}
.phase44-rank-card h2{color:#fff!important}
.phase44-rank-row{border-top:1px solid #20364f!important}
.phase44-rank-name,.phase44-rank-ca{color:#fff!important}
.phase44-rank-qty,.phase44-rank-empty{color:#b7c4d3!important}
#sources .row span{color:#dbe6f3!important}
#sources .row b{color:#fff!important}
</style>
<script id="phase5-statistics-visibility-fix-script">
(function(){
  const euro=n=>Number(n||0).toLocaleString('fr-FR',{style:'currency',currency:'EUR'});
  function qs(){
    const p=new URLSearchParams();
    const period=document.getElementById('period');
    const start=document.getElementById('start');
    const end=document.getElementById('end');
    p.set('period',period&&period.value?period.value:'today');
    if(start&&start.value)p.set('start',start.value);
    if(end&&end.value)p.set('end',end.value);
    return p.toString();
  }
  async function loadChannels(){
    const sources=document.getElementById('sources');
    if(!sources)return;
    const title=sources.closest('.box')&&sources.closest('.box').querySelector('h2');
    if(title)title.textContent='Canaux de vente';
    try{
      const r=await fetch('/api/statistics/sales-channels-phase5?'+qs(),{cache:'no-store'});
      const d=await r.json();
      if(!r.ok||!d.ok)throw new Error('Erreur');
      sources.innerHTML=d.channels.map(x=>`<div class="row"><span>${x.label} (${x.count})</span><b>${euro(x.total)}</b></div>`).join('');
    }catch(e){
      sources.innerHTML='<div class="muted">Canaux indisponibles</div>';
    }
  }
  function ready(){
    loadChannels();
    ['period','start','end'].forEach(id=>{const el=document.getElementById(id);if(el)el.addEventListener('change',loadChannels)});
    const btn=document.querySelector('.filters button');if(btn)btn.addEventListener('click',()=>setTimeout(loadChannels,50));
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',ready);else ready();
})();
</script>
'''
        response.set_data(html.replace("</body>", patch + "</body>", 1))
        response.headers["Content-Length"] = len(response.get_data())
        return response
