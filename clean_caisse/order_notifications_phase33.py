"""Phase 3.3 / Phase 6 — notifications des nouvelles commandes.

Correctif isolé : aucune écriture PostgreSQL, aucun changement de commande/ticket/TVA.
- Cuisine et Caisse utilisent des marqueurs de dernière commande distincts.
- Sur /pos, toute nouvelle commande déclenche le même événement sonore,
  quelle que soit sa provenance / son canal de vente.
- Le son de la Caisse doit être réellement déverrouillé par le navigateur :
  le bouton reste visible tant que l'AudioContext de /pos n'est pas actif.
- Alerte sonore renforcée : plusieurs impulsions courtes, volume nettement supérieur.
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
#phase6-site-order-notice{display:none;align-items:center;white-space:nowrap;font-size:15px;font-weight:900;color:#ffd21f;text-transform:uppercase;letter-spacing:.4px;text-shadow:0 0 7px rgba(255,210,31,.75);pointer-events:none;margin-left:4px}
#phase6-site-order-notice.show{display:inline-flex;animation:phase6SiteTextPulse .8s ease-in-out 4}
@keyframes phase6SiteTextPulse{0%,100%{color:#ffd21f;transform:scale(1)}50%{color:#ff5a36;transform:scale(1.04)}}
</style>
<script>
(function(){
 const PAGE='__PAGE__';
 const SOUND_KEY='bechefaa_phase33_sound';
 const LAST_KEY=PAGE==='pos'?'bechefaa_phase6_last_order_pos_all_v3':'bechefaa_phase6_last_order_kitchen';
 let audioCtx=null;
 let wanted=localStorage.getItem(SOUND_KEY)==='1';

 function getCtx(){
   try{
     const C=window.AudioContext||window.webkitAudioContext;if(!C)return null;
     if(!audioCtx||audioCtx.state==='closed')audioCtx=new C();
     return audioCtx;
   }catch(e){return null}
 }
 function isAudioReady(){
   const ctx=audioCtx;
   return !!(wanted&&ctx&&ctx.state==='running');
 }
 async function unlock(test){
   const ctx=getCtx();if(!ctx)return false;
   try{if(ctx.state==='suspended')await ctx.resume()}catch(e){}
   if(ctx.state!=='running'){updateButton();return false}
   wanted=true;localStorage.setItem(SOUND_KEY,'1');updateButton();
   if(test)beep();
   return true;
 }
 function tone(ctx,start,freq,duration,volume){
   const osc=ctx.createOscillator(),gain=ctx.createGain();
   osc.type='square';
   osc.frequency.setValueAtTime(freq,start);
   gain.gain.setValueAtTime(.001,start);
   gain.gain.exponentialRampToValueAtTime(volume,start+.015);
   gain.gain.setValueAtTime(volume,start+Math.max(.02,duration-.055));
   gain.gain.exponentialRampToValueAtTime(.001,start+duration);
   osc.connect(gain);gain.connect(ctx.destination);
   osc.start(start);osc.stop(start+duration+.02);
 }
 function beep(){
   try{
     const ctx=getCtx();if(!wanted||!ctx||ctx.state!=='running')return;
     const t=ctx.currentTime+.015;
     tone(ctx,t,920,.22,.72);
     tone(ctx,t+.28,1080,.22,.78);
     tone(ctx,t+.56,920,.30,.82);
   }catch(e){}
 }
 function updateButton(){
   const b=document.getElementById('phase33-audio');if(!b)return;
   if(PAGE==='pos'){
     b.classList.toggle('hidden',isAudioReady());
     b.textContent='🔊 Activer le son caisse';
     return;
   }
   b.classList.toggle('hidden',wanted);
   b.textContent='🔇 Activer le son';
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
 async function unlockOnInteraction(){
   if(PAGE!=='pos')return;
   const ctx=getCtx();
   if(ctx&&ctx.state==='running'){
     wanted=true;localStorage.setItem(SOUND_KEY,'1');updateButton();return;
   }
   await unlock(false);
 }
 document.addEventListener('pointerdown',unlockOnInteraction,{passive:true});
 document.addEventListener('keydown',unlockOnInteraction);
 document.addEventListener('touchstart',unlockOnInteraction,{passive:true});
 document.addEventListener('visibilitychange',()=>{if(PAGE==='pos'&&!document.hidden)updateButton()});

 function ensureSiteNotice(){
   if(PAGE!=='pos')return null;
   let el=document.getElementById('phase6-site-order-notice');
   if(el)return el;
   const top=document.querySelector('.top');
   const spacer=top&&top.querySelector('.navspacer');
   if(!top||!spacer)return null;
   el=document.createElement('span');
   el.id='phase6-site-order-notice';
   top.insertBefore(el,spacer);
   return el;
 }
 function showSiteNotice(order){
   if(PAGE!=='pos')return;
   const el=ensureSiteNotice();if(!el)return;
   const name=String(order.customer_name||'Client').trim();
   const mode=String(order.ticket_type||'').toLowerCase().includes('livraison')?'Livraison':'À emporter';
   const channel=String(order.sales_channel||order.source||'CAISSE').trim().toUpperCase()||'CAISSE';
   el.textContent='⚡ NOUVELLE COMMANDE — '+channel+' — '+name+' • '+mode;
   el.classList.remove('show');
   void el.offsetWidth;
   el.classList.add('show');
   clearTimeout(el._hideTimer);
   el._hideTimer=setTimeout(()=>el.classList.remove('show'),12000);
 }

 function inspect(orders){
   const all=(orders||[]).filter(o=>Number.isFinite(Number(o.num)));
   if(!all.length)return;

   if(PAGE==='pos'){
     const maxSeen=Math.max.apply(null,all.map(o=>Number(o.num)));
     const storedRaw=localStorage.getItem(LAST_KEY);
     if(storedRaw===null){localStorage.setItem(LAST_KEY,String(maxSeen));return}
     const last=Number(storedRaw);
     const newer=all.filter(o=>Number(o.num)>last).sort((a,b)=>Number(a.num)-Number(b.num));
     if(maxSeen>last)localStorage.setItem(LAST_KEY,String(maxSeen));
     if(!newer.length)return;
     const newest=newer[newer.length-1];
     showSiteNotice(newest);
     beep();
     return;
   }

   const maxSeen=Math.max.apply(null,all.map(o=>Number(o.num)));
   const storedRaw=localStorage.getItem(LAST_KEY);
   if(storedRaw===null){localStorage.setItem(LAST_KEY,String(maxSeen));return}
   const last=Number(storedRaw);
   const newer=all.filter(o=>Number(o.num)>last).sort((a,b)=>Number(a.num)-Number(b.num));
   if(maxSeen>last)localStorage.setItem(LAST_KEY,String(maxSeen));
   if(!newer.length)return;
   const kitchenNewer=newer.filter(o=>o.status==='À préparer');
   if(kitchenNewer.length)beep();
 }
 async function poll(){
   try{
     const r=await fetch('/api/kitchen/board',{cache:'no-store'}),d=await r.json();
     if(r.ok&&d&&d.ok&&Array.isArray(d.orders))inspect(d.orders);
   }catch(e){}
 }
 installButton();
 ensureSiteNotice();
 poll();setInterval(poll,4000);
})();
</script>
'''.replace('__PAGE__', page)
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
