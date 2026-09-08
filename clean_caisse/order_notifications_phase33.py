"""Phase 3.3 — notifications sonores des nouvelles commandes.

Correctif isolé : aucune écriture PostgreSQL, aucun changement de commande/ticket/TVA.
Le son est activable sur Cuisine ou Caisse et son choix est mémorisé dans le navigateur.
Aucune modification du DOM des cartes cuisine : pas de saut de mise en page.
"""
from flask import request


def register_order_notifications_phase33(app):
    @app.after_request
    def inject_order_notifications_phase33(response):
        if request.path not in ("/cuisine-preparation", "/pos") or response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        addon = r'''
<style>
.phase33-audio{position:fixed;right:14px;bottom:14px;z-index:9999;border:0;border-radius:8px;padding:9px 12px;font-weight:800;cursor:pointer;background:#dc2626;color:#fff;box-shadow:0 3px 14px rgba(0,0,0,.2)}
.phase33-audio.on{background:#16a34a}
</style>
<script>
(function(){
 const KEY='bechefaa_phase33_sound';
 let initialized=false,known=new Set(),audioCtx=null;
 let wanted=localStorage.getItem(KEY)==='1';

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
   wanted=true;localStorage.setItem(KEY,'1');updateButton();
   if(test)beep();
   return true;
 }
 function beep(){
   try{
     const ctx=getCtx();if(!wanted||!ctx||ctx.state!=='running')return;
     const osc=ctx.createOscillator(),gain=ctx.createGain();
     osc.type='sine';osc.frequency.value=880;
     gain.gain.setValueAtTime(.16,ctx.currentTime);gain.gain.exponentialRampToValueAtTime(.001,ctx.currentTime+.45);
     osc.connect(gain);gain.connect(ctx.destination);osc.start();osc.stop(ctx.currentTime+.45);
   }catch(e){}
 }
 function updateButton(){
   const b=document.getElementById('phase33-audio');if(!b)return;
   b.classList.toggle('on',wanted);b.textContent=wanted?'🔊 Son activé':'🔇 Activer le son';
 }
 function installButton(){
   if(document.getElementById('phase33-audio'))return;
   const b=document.createElement('button');b.id='phase33-audio';b.className='phase33-audio';document.body.appendChild(b);
   b.onclick=async function(e){
     e.preventDefault();e.stopPropagation();
     if(wanted){wanted=false;localStorage.setItem(KEY,'0');updateButton();return}
     if(!(await unlock(true)))alert('Le navigateur bloque encore le son. Cliquez à nouveau sur Activer le son.');
   };
   updateButton();
 }
 async function resumeRemembered(){if(wanted)await unlock(false)}
 document.addEventListener('pointerdown',resumeRemembered,{passive:true});
 document.addEventListener('keydown',resumeRemembered);

 function inspect(orders){
   const active=(orders||[]).filter(o=>o.status==='À préparer'||o.status==='En préparation');
   const current=new Set(active.map(o=>String(o.id)));
   if(initialized&&active.some(o=>o.status==='À préparer'&&!known.has(String(o.id))))beep();
   known=current;initialized=true;
 }
 async function poll(){
   try{const r=await fetch('/api/kitchen/board',{cache:'no-store'}),d=await r.json();if(r.ok&&d&&d.ok&&Array.isArray(d.orders))inspect(d.orders)}catch(e){}
 }
 installButton();
 poll();setInterval(poll,5000);
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
