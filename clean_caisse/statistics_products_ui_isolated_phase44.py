"""Phase 4.4 — UI isolée + vendus / - vendus.

IMPORTANT : ce module n'est volontairement ni importé ni enregistré dans
wsgi_caisse.py. Il prépare uniquement l'affichage futur sur /statistiques.
Aucune modification du noyau statistics_phase44.py.
"""


def register_statistics_products_ui_isolated_phase44(app):
    """Prépare le patch HTML futur ; fonction inactive tant qu'elle n'est pas enregistrée."""

    @app.after_request
    def inject_product_rankings_phase44(response):
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
<style>
#phase44-product-rankings{max-width:1180px;margin:22px auto;padding:0 18px;display:grid;grid-template-columns:1fr 1fr;gap:18px;font-family:Arial,sans-serif}
.phase44-rank-card{background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:18px;box-shadow:0 6px 18px rgba(0,0,0,.05)}
.phase44-rank-card h2{margin:0 0 14px;font-size:20px;color:#111827}
.phase44-rank-row{display:grid;grid-template-columns:1fr auto auto;gap:12px;padding:10px 0;border-top:1px solid #eef0f2;align-items:center}
.phase44-rank-row:first-child{border-top:0}.phase44-rank-name{font-weight:700}.phase44-rank-qty{white-space:nowrap;color:#374151}.phase44-rank-ca{white-space:nowrap;font-weight:700}
.phase44-rank-empty{color:#6b7280;padding:8px 0}
@media(max-width:760px){#phase44-product-rankings{grid-template-columns:1fr}.phase44-rank-row{grid-template-columns:1fr auto}.phase44-rank-ca{grid-column:2}}
</style>
<section id="phase44-product-rankings">
  <div class="phase44-rank-card"><h2>Produits les + vendus</h2><div id="phase44-most-sold"><div class="phase44-rank-empty">Chargement…</div></div></div>
  <div class="phase44-rank-card"><h2>Produits les – vendus</h2><div id="phase44-least-sold"><div class="phase44-rank-empty">Chargement…</div></div></div>
</section>
<script>
(function(){
  const euro = new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR'});
  function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function draw(id, rows){
    const el=document.getElementById(id); if(!el)return;
    if(!rows||!rows.length){el.innerHTML='<div class="phase44-rank-empty">Aucune vente sur cette période.</div>';return;}
    el.innerHTML=rows.map(x=>'<div class="phase44-rank-row"><div class="phase44-rank-name">'+esc(x.name)+'</div><div class="phase44-rank-qty">'+Number(x.qty||0)+' vendu(s)</div><div class="phase44-rank-ca">'+euro.format(Number(x.revenue||0))+'</div></div>').join('');
  }
  function params(){
    const p=new URLSearchParams();
    const period=document.querySelector('[name="period"],#period');
    const start=document.querySelector('[name="start"],#start');
    const end=document.querySelector('[name="end"],#end');
    if(period&&period.value)p.set('period',period.value);
    if(start&&start.value)p.set('start',start.value);
    if(end&&end.value)p.set('end',end.value);
    return p;
  }
  async function load(){
    try{
      const r=await fetch('/api/statistics/products-phase44?'+params().toString(),{cache:'no-store'});
      const d=await r.json(); if(!r.ok||!d.ok)throw new Error(d.error||'Erreur');
      draw('phase44-most-sold',d.most_sold); draw('phase44-least-sold',d.least_sold);
    }catch(e){
      ['phase44-most-sold','phase44-least-sold'].forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML='<div class="phase44-rank-empty">Données indisponibles.</div>';});
    }
  }
  document.addEventListener('change',e=>{if(e.target.matches('[name="period"],#period,[name="start"],#start,[name="end"],#end'))load();});
  load();
})();
</script>
'''
        response.set_data(html.replace(marker, patch + marker))
        response.headers['Content-Length'] = len(response.get_data())
        return response
