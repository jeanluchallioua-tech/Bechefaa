"""Phase 3.3 / Phase 6 — notifications des nouvelles commandes.

Correctif isolé : aucune écriture PostgreSQL, aucun changement de commande/ticket/TVA.
- Cuisine et Caisse utilisent désormais des marqueurs de dernière commande distincts.
- Sur /pos, une nouvelle commande SITE déclenche le même événement pour le son
  et pour une notification visuelle.
- Le son reste soumis à l'autorisation du navigateur et peut être activé par le
  bouton existant.
"""
from flask import request


def register_order_notifications_phase33(app):
    @app.after_request
    def inject_order_notifications_phase33(response):
        if request.path not in ("/cuisine-preparation", "/pos") or response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        page = "pos" if request.path == "/pos" else "kitchen"
        addon = r'''
<style>
.phase33-audio{position:fixed;right:14px;top:14px;z-index:9999;border:0;border-radius:8px;padding:9px 12px;font-weight:800;cursor:pointer;background:#dc2626;color:#fff;box-shadow:0 3px 14px rgba(0,0,0,.2)}
.phase33-audio.hidden{display:none}
#phase6-site-order-notice{position:fixed;right:20px;bottom:20px;z-index:11000;max-width:410px;background:#111827;color:#fff;border-radius:12px;padding:16px 19px;box-shadow:0 10px 32px rgba(0,0,0,.3);display:none}
#phase6-site-order-notice.show{display:block}
#phase6-site-order-notice b{display:block;font-size:17px;margin-bottom:4px}
#phase6-site-order-notice span{font-size:14px;font-weight:600}
</style>
<script>
(function(){
 const PAGE='__PAGE__';
 const SOUND_KEY='bechefaa_phase33_sound';
 const LAST_KEY='bechefaa_phase6_last_order_'+PAGE;
 let audioCtx=null;
 let wanted=localStorage.getItem(SOUND_KEY)==='1';

 function getCtx(){
   try{
     const C=window.AudioContext||window.webkitAudioContext;if(!C)return null;
     if(!audioCtx||audioCtx.state==='closed')audioCtx=new C();
     return audioCtx;
   }catch(e){return null}
 }
 async function unlock(test){
   const ctx=getCtx();if(!ctx)return false;
   try{if(ctx.state==='suspended')await ctx.resume()}catch(e){}
   if(ctx.state!=='running')return false;
   wanted=true;localStorage.setItem(SOUND_KEY,'1');updateButton();
   if(test)beep();
   return true;
 }
 function beep(){
   try{
     const ctx=getCtx();if(!wanted||!ctx||ctx.state!=='running')return;
     const osc=ctx.createOscillator(),gain=ctx.createGain();
     osc.type='sine';osc.frequency.value=880;
     gain.gain.setValueAtTime(.22,ctx.currentTime);gain.gain.exponentialRampToValueAtTime(.001,ctx.currentTime+.65);
     osc.connect(gain);gain.connect(ctx.destination);osc.start();osc.stop(ctx.currentTime+.65);
   }catch(e){}
 }
 function updateButton(){
   const b=document.getElementById('phase33-audio');if(!b)return;
   b.classList.toggle('hidden',wanted);b.textContent='🔇 Activer le son';
 }
 function installButton(){
   if(document.getElementById('phase33-audio'))return;
   const b=document.createElement('button');b.id='phase33-audio';b.className='phase33-audio';document.body.appendChild(b);
   b.onclick=async function(e){
     e.preventDefault();e.stopPropagation();
     if(!(await unlock(true)))alert('Le navigateur bloque encore le son. Cliquez à nouveau sur Activer le son.');
   };
   updateButton();
 }
 async function resumeRemembered(){if(wanted)await unlock(false)}
 document.addEventListener('pointerdown',resumeRemembered,{passive:true});
 document.addEventListener('keydown',resumeRemembered);

 function showSiteNotice(order){
   if(PAGE!=='pos')return;
   let el=document.getElementById('phase6-site-order-notice');
   if(!el){el=document.createElement('div');el.id='phase6-site-order-notice';document.body.appendChild(el)}
   const name=String(order.customer_name||'Client').trim();
   const mode=String(order.ticket_type||'').toLowerCase().includes('livraison')?'Livraison':'À emporter';
   el.innerHTML='<b>Nouvelle commande SITE</b><span>'+name+' • '+mode+'</span>';
   el.classList.add('show');
   clearTimeout(el._hideTimer);
   el._hideTimer=setTimeout(()=>el.classList.remove('show'),8000);
 }

 function inspect(orders){
   const all=(orders||[]).filter(o=>Number.isFinite(Number(o.num)));
   if(!all.length)return;
   const maxSeen=Math.max.apply(null,all.map(o=>Number(o.num)));
   const storedRaw=localStorage.getItem(LAST_KEY);
   if(storedRaw===null){localStorage.setItem(LAST_KEY,String(maxSeen));return}
   const last=Number(storedRaw);
   const newer=all.filter(o=>Number(o.num)>last).sort((a,b)=>Number(a.num)-Number(b.num));
   if(maxSeen>last)localStorage.setItem(LAST_KEY,String(maxSeen));
   if(!newer.length)return;

   if(PAGE==='pos'){
     const siteNewer=newer.filter(o=>String(o.sales_channel||'').toUpperCase()==='SITE');
     if(siteNewer.length){
       const newest=siteNewer[siteNewer.length-1];
       showSiteNotice(newest);
       beep();
     }
   }else{
     const kitchenNewer=newer.filter(o=>o.status==='À préparer');
     if(kitchenNewer.length)beep();
   }
 }
 async function poll(){
   try{
     const r=await fetch('/api/kitchen/board',{cache:'no-store'}),d=await r.json();
     if(r.ok&&d&&d.ok&&Array.isArray(d.orders))inspect(d.orders);
   }catch(e){}
 }
 installButton();
 poll();setInterval(poll,4000);
})();
</script>
'''.replace('__PAGE__', page)
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
