"""Phase 4.4 — courbes statistiques isolées.

Ce module est enregistré dans wsgi_caisse.py et injecte uniquement l'affichage
de la courbe sur /statistiques. Il utilise l'endpoint chronologique dédié,
sans modifier le noyau statistics_phase44.py ni les autres modules validés.
"""


def register_statistics_curves_isolated_phase44(app):
    """Affiche la courbe d'évolution des ventes sur /statistiques."""

    @app.after_request
    def inject_statistics_curves_phase44(response):
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
#phase44-curves{max-width:1180px;margin:22px auto;padding:0 18px;font-family:Arial,sans-serif}
.phase44-curve-card{background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:18px;box-shadow:0 6px 18px rgba(0,0,0,.05)}
.phase44-curve-card h2{margin:0 0 14px;font-size:20px;color:#111827}.phase44-curve-wrap{position:relative;min-height:300px}.phase44-curve-svg{width:100%;height:300px;display:block}.phase44-curve-grid{stroke:#e5e7eb;stroke-width:1}.phase44-curve-axis{stroke:#9ca3af;stroke-width:1.2}.phase44-curve-line{fill:none;stroke:#143D53;stroke-width:3;stroke-linecap:round;stroke-linejoin:round}.phase44-curve-point{fill:#143D53}.phase44-curve-label{font-size:11px;fill:#6b7280}.phase44-curve-value{font-size:11px;fill:#111827;font-weight:700}.phase44-curve-empty{color:#6b7280;padding:16px 0}
</style>
<section id="phase44-curves">
  <div class="phase44-curve-card">
    <h2>Évolution des ventes</h2>
    <div id="phase44-curve-sales" class="phase44-curve-wrap"><div class="phase44-curve-empty">Chargement…</div></div>
  </div>
</section>
<script>
(function(){
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
  function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function labelDate(v){
    const s=String(v||'');
    const m=s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    return m ? m[3]+'/'+m[2] : s;
  }
  function render(rows){
    const host=document.getElementById('phase44-curve-sales'); if(!host)return;
    if(!rows||!rows.length){host.innerHTML='<div class="phase44-curve-empty">Aucune donnée sur cette période.</div>';return;}
    const width=1000,height=300,padL=55,padR=20,padT=20,padB=42;
    const vals=rows.map(x=>Number(x.value||0)); const max=Math.max(...vals,1);
    const xStep=rows.length>1?(width-padL-padR)/(rows.length-1):0;
    const y=v=>padT+(height-padT-padB)*(1-v/max);
    const pts=rows.map((x,i)=>(padL+i*xStep)+','+y(Number(x.value||0))).join(' ');
    let grid=''; for(let i=0;i<=4;i++){const gy=padT+(height-padT-padB)*i/4;const gv=(max*(1-i/4));grid+='<line class="phase44-curve-grid" x1="'+padL+'" y1="'+gy+'" x2="'+(width-padR)+'" y2="'+gy+'"></line><text class="phase44-curve-label" x="6" y="'+(gy+4)+'">'+Math.round(gv)+'</text>';}
    const dots=rows.map((x,i)=>{const px=padL+i*xStep,py=y(Number(x.value||0));return '<circle class="phase44-curve-point" cx="'+px+'" cy="'+py+'" r="4"></circle><text class="phase44-curve-value" text-anchor="middle" x="'+px+'" y="'+(py-9)+'">'+Number(x.value||0)+'</text><text class="phase44-curve-label" text-anchor="middle" x="'+px+'" y="'+(height-16)+'">'+esc(x.label)+'</text>';}).join('');
    host.innerHTML='<svg class="phase44-curve-svg" viewBox="0 0 '+width+' '+height+'" preserveAspectRatio="none"><line class="phase44-curve-axis" x1="'+padL+'" y1="'+padT+'" x2="'+padL+'" y2="'+(height-padB)+'"></line><line class="phase44-curve-axis" x1="'+padL+'" y1="'+(height-padB)+'" x2="'+(width-padR)+'" y2="'+(height-padB)+'"></line>'+grid+'<polyline class="phase44-curve-line" points="'+pts+'"></polyline>'+dots+'</svg>';
  }
  async function load(){
    try{
      const r=await fetch('/api/statistics/evolution-phase44?'+params().toString(),{cache:'no-store'});
      const d=await r.json(); if(!r.ok||!d.ok)throw new Error(d.error||'Erreur');
      const rows=Array.isArray(d.points)
        ? d.points.map(x=>({label:labelDate(x.date),value:Number(x.orders||0)}))
        : [];
      render(rows);
    }catch(e){const host=document.getElementById('phase44-curve-sales');if(host)host.innerHTML='<div class="phase44-curve-empty">Données indisponibles.</div>';}
  }
  document.addEventListener('change',e=>{if(e.target.matches('[name="period"],#period,[name="start"],#start,[name="end"],#end'))load();});
  load();
})();
</script>
'''
        response.set_data(html.replace(marker, patch + marker))
        response.headers['Content-Length'] = len(response.get_data())
        return response
