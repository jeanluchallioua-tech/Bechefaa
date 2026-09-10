"""Phase 5 — correction isolée d'ordre d'injection du camembert canaux.

INACTIF : module non importé/non enregistré dans wsgi_caisse.py.
Cause traitée : les after_request Flask s'exécutent en ordre inverse. Le module
précédent cherchait #phase44-donut-most avant que le module de base ne l'ait
injecté dans la réponse HTML, donc il ne pouvait jamais ajouter son script.

Ce module injecte uniquement le JavaScript/CSS dans /statistiques sans exiger
que le conteneur existe déjà côté serveur. Au chargement navigateur, le DOM
complet contient alors le camembert de base et celui-ci est remplacé.
Aucune écriture métier, aucun paiement, aucun Z.
"""


def register_statistics_channel_donut_late_isolated_phase5(app):
    @app.after_request
    def inject_statistics_channel_donut_late_phase5(response):
        if response.status_code != 200:
            return response
        if not response.content_type or "text/html" not in response.content_type:
            return response

        from flask import request
        if request.path != "/statistiques":
            return response

        html = response.get_data(as_text=True)
        if "phase5-channel-donut-late" in html or "</body>" not in html:
            return response

        patch = r'''
<style id="phase5-channel-donut-late">
#phase44-donut-most .phase44-donut{box-shadow:0 0 24px rgba(0,240,255,.35),0 0 42px rgba(255,0,168,.20)!important}
#phase44-donut-most .phase44-donut-dot{box-shadow:0 0 10px currentColor,0 0 0 1px rgba(255,255,255,.35)!important}
</style>
<script id="phase5-channel-donut-late-script">
(function(){
  const colors=['#00F0FF','#FF00A8','#FFD400','#39FF14'];
  const labels={RESTO:'Resto',SITE:'Site internet',UBER_EATS:'Uber Eats',DELIVEROO:'Deliveroo'};
  const euro=new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR'});

  function params(){
    const p=new URLSearchParams();
    const period=document.querySelector('[name="period"],#period');
    const start=document.querySelector('[name="start"],#start');
    const end=document.querySelector('[name="end"],#end');
    p.set('period',period&&period.value?period.value:'today');
    if(start&&start.value)p.set('start',start.value);
    if(end&&end.value)p.set('end',end.value);
    return p.toString();
  }

  function draw(rows){
    const host=document.getElementById('phase44-donut-most');
    if(!host)return false;
    const card=host.closest('.phase44-donut-card');
    const title=card&&card.querySelector('h2');
    if(title)title.textContent='Répartition des canaux de vente';

    const ordered=['RESTO','SITE','UBER_EATS','DELIVEROO'].map((key,i)=>{
      const found=(rows||[]).find(x=>String(x.channel||'').toUpperCase()===key);
      return {key,label:labels[key],count:Number(found&&found.count||0),total:Number(found&&found.total||0),color:colors[i]};
    });

    const grand=ordered.reduce((s,x)=>s+x.total,0);
    if(grand<=0){
      host.innerHTML='<div class="phase44-donut-empty">Aucune donnée sur cette période.</div>';
      return true;
    }

    let cursor=0;
    const stops=[];
    ordered.forEach(x=>{
      const next=cursor+(x.total/grand*100);
      if(x.total>0)stops.push(x.color+' '+cursor.toFixed(2)+'% '+next.toFixed(2)+'%');
      cursor=next;
    });
    const legend=ordered.map(x=>'<div class="phase44-donut-line"><span class="phase44-donut-dot" style="background:'+x.color+';color:'+x.color+'"></span><span class="phase44-donut-name">'+x.label+' ('+x.count+')</span><span class="phase44-donut-value">'+euro.format(x.total)+'</span></div>').join('');
    host.innerHTML='<div class="phase44-donut" style="background:conic-gradient('+stops.join(',')+')"></div><div class="phase44-donut-legend">'+legend+'</div>';
    return true;
  }

  async function load(){
    const host=document.getElementById('phase44-donut-most');
    if(!host)return;
    try{
      const r=await fetch('/api/statistics/sales-channels-phase5?'+params(),{cache:'no-store'});
      const d=await r.json();
      if(!r.ok||!d.ok)throw new Error('channels unavailable');
      draw(d.channels||[]);
    }catch(e){
      host.innerHTML='<div class="phase44-donut-empty">Canaux indisponibles.</div>';
    }
  }

  function ready(){
    setTimeout(load,250);
    document.addEventListener('change',e=>{
      if(e.target.matches('[name="period"],#period,[name="start"],#start,[name="end"],#end'))setTimeout(load,120);
    });
    const btn=document.querySelector('.filters button');
    if(btn)btn.addEventListener('click',()=>setTimeout(load,150));
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',ready);else ready();
})();
</script>
'''
        response.set_data(html.replace("</body>", patch + "</body>", 1))
        response.headers["Content-Length"] = len(response.get_data())
        return response
