"""Phase 5 — remplacement isolé du camembert produits par les canaux de vente.

INACTIF : module non importé/non enregistré dans wsgi_caisse.py.
Objectif limité à /statistiques :
- remplacer le camembert « Répartition des produits les + vendus » par
  « Répartition des canaux de vente » ;
- utiliser les données déjà exposées par /api/statistics/today-phase44 ;
- appliquer une palette nettement plus flashy.
Aucune écriture métier, aucun paiement, aucun Z.
"""


def register_statistics_channel_donut_flashy_isolated_phase5(app):
    @app.after_request
    def inject_channel_donut_flashy_phase5(response):
        if response.status_code != 200:
            return response
        if not response.content_type or "text/html" not in response.content_type:
            return response

        from flask import request
        if request.path != "/statistiques":
            return response

        html = response.get_data(as_text=True)
        if "phase44-donut-most" not in html or "phase5-channel-donut-flashy" in html:
            return response

        patch = r'''
<style id="phase5-channel-donut-flashy">
#phase44-donut-most .phase44-donut{
  box-shadow:0 0 22px rgba(0,229,255,.28),0 0 38px rgba(255,0,153,.16)!important;
}
#phase44-donut-most .phase44-donut-dot{
  box-shadow:0 0 9px currentColor,0 0 0 1px rgba(255,255,255,.30)!important;
}
</style>
<script id="phase5-channel-donut-flashy-script">
(function(){
  const colors=['#00F0FF','#FF00A8','#FFD400','#39FF14'];
  const labels={
    RESTO:'Resto',
    SITE:'Site internet',
    UBER_EATS:'Uber Eats',
    DELIVEROO:'Deliveroo'
  };
  const euro=new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR'});

  function params(){
    const p=new URLSearchParams();
    const period=document.getElementById('period');
    const start=document.getElementById('start');
    const end=document.getElementById('end');
    p.set('period',period&&period.value?period.value:'today');
    if(start&&start.value)p.set('start',start.value);
    if(end&&end.value)p.set('end',end.value);
    return p.toString();
  }

  function draw(rows){
    const host=document.getElementById('phase44-donut-most');
    if(!host)return;
    const card=host.closest('.phase44-donut-card');
    const title=card&&card.querySelector('h2');
    if(title)title.textContent='Répartition des canaux de vente';

    const ordered=['RESTO','SITE','UBER_EATS','DELIVEROO'].map((key,i)=>{
      const found=(rows||[]).find(x=>String(x.channel||'').toUpperCase()===key || String(x.source||'').toLowerCase()===labels[key].toLowerCase());
      return {
        key,
        label:labels[key],
        count:Number(found&&found.count||0),
        total:Number(found&&found.total||0),
        color:colors[i]
      };
    });

    const grand=ordered.reduce((s,x)=>s+x.total,0);
    if(grand<=0){
      host.innerHTML='<div class="phase44-donut-empty">Aucune donnée sur cette période.</div>';
      return;
    }

    let cursor=0;
    const stops=[];
    ordered.forEach(x=>{
      const next=cursor+(x.total/grand*100);
      if(x.total>0)stops.push(x.color+' '+cursor.toFixed(2)+'% '+next.toFixed(2)+'%');
      cursor=next;
    });
    if(!stops.length)stops.push('#20364f 0% 100%');

    const legend=ordered.map(x=>
      '<div class="phase44-donut-line">'+
      '<span class="phase44-donut-dot" style="background:'+x.color+';color:'+x.color+'"></span>'+
      '<span class="phase44-donut-name">'+x.label+' ('+x.count+')</span>'+
      '<span class="phase44-donut-value">'+euro.format(x.total)+'</span>'+
      '</div>'
    ).join('');

    host.innerHTML='<div class="phase44-donut" style="background:conic-gradient('+stops.join(',')+')"></div><div class="phase44-donut-legend">'+legend+'</div>';
  }

  async function load(){
    try{
      const r=await fetch('/api/statistics/today-phase44?'+params(),{cache:'no-store'});
      const d=await r.json();
      if(!r.ok||!d.ok)throw new Error();
      draw(d.sources||[]);
    }catch(e){
      const host=document.getElementById('phase44-donut-most');
      if(host)host.innerHTML='<div class="phase44-donut-empty">Données indisponibles.</div>';
    }
  }

  function bind(){
    ['period','start','end'].forEach(id=>{
      const el=document.getElementById(id);
      if(el)el.addEventListener('change',()=>setTimeout(load,80));
    });
    const btn=document.querySelector('.filters button');
    if(btn)btn.addEventListener('click',()=>setTimeout(load,120));
    setTimeout(load,180);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind();
})();
</script>
'''
        html = html.replace("</body>", patch + "</body>", 1)
        response.set_data(html)
        response.headers["Content-Length"] = len(response.get_data())
        return response
