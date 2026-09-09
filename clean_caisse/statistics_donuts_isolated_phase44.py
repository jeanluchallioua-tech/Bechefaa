"""Phase 4.4 — camemberts statistiques isolés.

IMPORTANT : ce module n'est volontairement ni importé ni enregistré dans
wsgi_caisse.py. Il prépare uniquement les futurs graphiques de répartition
sur /statistiques, sans toucher au noyau statistics_phase44.py ni aux blocs
produits déjà validés.
"""


def register_statistics_donuts_isolated_phase44(app):
    """Prépare les camemberts futurs ; fonction inactive tant qu'elle n'est pas enregistrée."""

    @app.after_request
    def inject_statistics_donuts_phase44(response):
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
#phase44-donuts{max-width:1180px;margin:22px auto;padding:0 18px;display:grid;grid-template-columns:1fr 1fr;gap:18px;font-family:Arial,sans-serif}
.phase44-donut-card{background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:18px;box-shadow:0 6px 18px rgba(0,0,0,.05)}
.phase44-donut-card h2{margin:0 0 14px;font-size:20px;color:#111827}.phase44-donut-wrap{display:flex;gap:20px;align-items:center;min-height:240px}.phase44-donut{width:210px;height:210px;border-radius:50%;position:relative;flex:0 0 auto}.phase44-donut:after{content:'';position:absolute;inset:48px;background:#fff;border-radius:50%}.phase44-donut-legend{display:grid;gap:8px;min-width:0}.phase44-donut-line{display:grid;grid-template-columns:12px minmax(0,1fr) auto;gap:8px;align-items:center;font-size:14px}.phase44-donut-dot{width:12px;height:12px;border-radius:3px}.phase44-donut-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.phase44-donut-value{font-weight:700;white-space:nowrap}.phase44-donut-empty{color:#6b7280}
@media(max-width:900px){#phase44-donuts{grid-template-columns:1fr}}@media(max-width:520px){.phase44-donut-wrap{flex-direction:column}.phase44-donut{width:190px;height:190px}.phase44-donut:after{inset:44px}.phase44-donut-legend{width:100%}}
</style>
<section id="phase44-donuts">
 <div class="phase44-donut-card"><h2>Répartition des produits les + vendus</h2><div id="phase44-donut-most" class="phase44-donut-wrap"><div class="phase44-donut-empty">Chargement…</div></div></div>
 <div class="phase44-donut-card"><h2>Répartition du chiffre d'affaires produits</h2><div id="phase44-donut-revenue" class="phase44-donut-wrap"><div class="phase44-donut-empty">Chargement…</div></div></div>
</section>
<script>
(function(){
 const colors=['#143D53','#2E6F95','#4E9F3D','#F2A541','#C8553D','#7D5BA6','#2A9D8F','#E76F51'];
 const euro=new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR'});
 function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
 function params(){const p=new URLSearchParams();const period=document.querySelector('[name="period"],#period');const start=document.querySelector('[name="start"],#start');const end=document.querySelector('[name="end"],#end');if(period&&period.value)p.set('period',period.value);if(start&&start.value)p.set('start',start.value);if(end&&end.value)p.set('end',end.value);p.set('limit','8');return p;}
 function render(id,rows,key,formatter){const host=document.getElementById(id);if(!host)return;const clean=(rows||[]).filter(x=>Number(x[key]||0)>0);const total=clean.reduce((s,x)=>s+Number(x[key]||0),0);if(!total){host.innerHTML='<div class="phase44-donut-empty">Aucune donnée sur cette période.</div>';return;}let cursor=0;const stops=[];clean.forEach((x,i)=>{const next=cursor+(Number(x[key]||0)/total*100);stops.push(colors[i%colors.length]+' '+cursor.toFixed(2)+'% '+next.toFixed(2)+'%');cursor=next;});const legend=clean.map((x,i)=>'<div class="phase44-donut-line"><span class="phase44-donut-dot" style="background:'+colors[i%colors.length]+'"></span><span class="phase44-donut-name">'+esc(x.name)+'</span><span class="phase44-donut-value">'+formatter(Number(x[key]||0))+'</span></div>').join('');host.innerHTML='<div class="phase44-donut" style="background:conic-gradient('+stops.join(',')+')"></div><div class="phase44-donut-legend">'+legend+'</div>';}
 async function load(){try{const r=await fetch('/api/statistics/products-phase44?'+params().toString(),{cache:'no-store'});const d=await r.json();if(!r.ok||!d.ok)throw new Error();render('phase44-donut-most',d.most_sold,'qty',v=>v+' vendu(s)');render('phase44-donut-revenue',d.most_sold,'revenue',v=>euro.format(v));}catch(e){['phase44-donut-most','phase44-donut-revenue'].forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML='<div class="phase44-donut-empty">Données indisponibles.</div>';});}}
 document.addEventListener('change',e=>{if(e.target.matches('[name="period"],#period,[name="start"],#start,[name="end"],#end'))load();});load();
})();
</script>
'''
        response.set_data(html.replace(marker, patch + marker))
        response.headers['Content-Length'] = len(response.get_data())
        return response
