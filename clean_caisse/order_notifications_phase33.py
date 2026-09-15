"""Phase 3.3 / Phase 6 — notifications des nouvelles commandes.

Correctif isolé : aucune écriture PostgreSQL, aucun changement de commande/ticket/TVA.
- Cuisine et Caisse utilisent des marqueurs de dernière commande distincts.
- Sur /pos, seules les commandes provenant du SITE déclenchent l'alerte Caisse.
- Les commandes saisies directement en Caisse restent silencieuses sur /pos,
  mais déclenchent normalement la notification Cuisine après envoi.
- Le son Caisse et Cuisine est activé par défaut et se déverrouille à la première
  interaction utilisateur ; le bouton Cuisine reste disponible en secours navigateur.
- La Cuisine ne mémorise que les commandes réellement au statut À préparer afin
  d'éviter de perdre le son si le polling voit l'ordre entre création et envoi cuisine.
- Le volume et l'activation Caisse/Cuisine sont pilotés depuis Administration.
"""
from flask import request
from .notification_settings_phase6 import register_notification_settings_phase6


def register_order_notifications_phase33(app):
    register_notification_settings_phase6(app)

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
 const LAST_KEY=PAGE==='pos'?'bechefaa_phase6_last_site_order_pos_v4':'bechefaa_phase6_last_ready_order_kitchen_v2';
 let audioCtx=null;
 let wanted=true;
 let soundSettings={enabled:true,volume:.82};
 localStorage.setItem(SOUND_KEY,'1');

 async function loadSoundSettings(){
   try{
     const r=await fetch('/api/notification-settings',{cache:'no-store'}),d=await r.json();
     if(!r.ok||!d||!d.ok)return;
     if(PAGE==='pos')soundSettings={enabled:!!d.pos_enabled,volume:Math.max(0,Math.min(1,Number(d.pos_volume||0)/100))};
     else soundSettings={enabled:!!d.kitchen_enabled,volume:Math.max(0,Math.min(1,Number(d.kitchen_volume||0)/100))};
     updateButton();
   }catch(e){}
 }
 function getCtx(){
   try{
     const C=window.AudioContext||window.webkitAudioContext;if(!C)return null;
     if(!audioCtx||audioCtx.state==='closed')audioCtx=new C();
     return audioCtx;
   }catch(e){return null}
 }
 function isAudioReady(){return !!(audioCtx&&audioCtx.state==='running')}
 async function unlock(test){
   if(!soundSettings.enabled)return false;
   const ctx=getCtx();if(!ctx)return false;
   try{if(ctx.state==='suspended')await ctx.resume()}catch(e){}
   if(ctx.state!=='running'){updateButton();return false}
   wanted=true;localStorage.setItem(SOUND_KEY,'1');updateButton();
   if(test)beep();
   return true;
 }
 function tone(ctx,start,freq,duration,volume){
   const osc=ctx.createOscillator(),gain=ctx.createGain();
   osc.type='square';osc.frequency.setValueAtTime(freq,start);
   gain.gain.setValueAtTime(.001,start);
   gain.gain.exponentialRampToValueAtTime(Math.max(.001,volume),start+.015);
   gain.gain.setValueAtTime(Math.max(.001,volume),start+Math.max(.02,duration-.055));
   gain.gain.exponentialRampToValueAtTime(.001,start+duration);
   osc.connect(gain);gain.connect(ctx.destination);osc.start(start);osc.stop(start+duration+.02);
 }
 function beep(){
   try{
     const ctx=getCtx();if(!soundSettings.enabled||soundSettings.volume<=0||!wanted||!ctx||ctx.state!=='running')return;
     const t=ctx.currentTime+.015,v=soundSettings.volume;
     tone(ctx,t,920,.22,v*.88);tone(ctx,t+.28,1080,.22,v*.95);tone(ctx,t+.56,920,.30,v);
   }catch(e){}
 }
 function updateButton(){
   const b=document.getElementById('phase33-audio');if(!b)return;
   if(PAGE==='pos'||!soundSettings.enabled){b.classList.add('hidden');return}
   b.classList.toggle('hidden',isAudioReady());
   b.textContent='🔇 Activer le son';
 }
 function installButton(){
   if(PAGE==='pos')return;
   if(document.getElementById('phase33-audio'))return;
   const b=document.createElement('button');b.id='phase33-audio';b.className='phase33-audio';document.body.appendChild(b);
   b.onclick=async function(e){e.preventDefault();e.stopPropagation();if(!(await unlock(true))&&soundSettings.enabled)alert('Le navigateur bloque encore le son. Cliquez à nouveau sur Activer le son.');};
   updateButton();
 }
 async function unlockOnInteraction(){
   if(!soundSettings.enabled)return;
   const ctx=getCtx();
   if(ctx&&ctx.state==='running'){wanted=true;localStorage.setItem(SOUND_KEY,'1');updateButton();return}
   await unlock(false);
 }
 document.addEventListener('pointerdown',unlockOnInteraction,{passive:true});
 document.addEventListener('keydown',unlockOnInteraction);
 document.addEventListener('touchstart',unlockOnInteraction,{passive:true});

 function ensureSiteNotice(){
   if(PAGE!=='pos')return null;
   let el=document.getElementById('phase6-site-order-notice');if(el)return el;
   const top=document.querySelector('.top');const spacer=top&&top.querySelector('.navspacer');if(!top||!spacer)return null;
   el=document.createElement('span');el.id='phase6-site-order-notice';top.insertBefore(el,spacer);return el;
 }
 function showSiteNotice(order){
   if(PAGE!=='pos')return;
   const el=ensureSiteNotice();if(!el)return;
   const name=String(order.customer_name||'Client').trim();
   const mode=String(order.ticket_type||'').toLowerCase().includes('livraison')?'Livraison':'À emporter';
   el.textContent='⚡ NOUVELLE COMMANDE SITE — '+name+' • '+mode;
   el.classList.remove('show');void el.offsetWidth;el.classList.add('show');
   clearTimeout(el._hideTimer);el._hideTimer=setTimeout(()=>el.classList.remove('show'),12000);
 }

 function inspect(orders){
   const all=(orders||[]).filter(o=>Number.isFinite(Number(o.num)));
   if(!all.length)return;

   if(PAGE==='pos'){
     const site=all.filter(o=>String(o.sales_channel||'').toUpperCase()==='SITE');
     if(!site.length)return;
     const maxSeen=Math.max.apply(null,site.map(o=>Number(o.num)));
     const storedRaw=localStorage.getItem(LAST_KEY);
     if(storedRaw===null){localStorage.setItem(LAST_KEY,String(maxSeen));return}
     const last=Number(storedRaw);
     const newer=site.filter(o=>Number(o.num)>last).sort((a,b)=>Number(a.num)-Number(b.num));
     if(maxSeen>last)localStorage.setItem(LAST_KEY,String(maxSeen));
     if(!newer.length)return;
     const newest=newer[newer.length-1];showSiteNotice(newest);beep();return;
   }

   const ready=all.filter(o=>String(o.status||'').trim()==='À préparer');
   if(!ready.length)return;
   const maxReady=Math.max.apply(null,ready.map(o=>Number(o.num)));
   const storedRaw=localStorage.getItem(LAST_KEY);
   if(storedRaw===null){localStorage.setItem(LAST_KEY,String(maxReady));return}
   const last=Number(storedRaw);
   const newerReady=ready.filter(o=>Number(o.num)>last).sort((a,b)=>Number(a.num)-Number(b.num));
   if(maxReady>last)localStorage.setItem(LAST_KEY,String(maxReady));
   if(newerReady.length)beep();
 }
 async function poll(){
   try{const r=await fetch('/api/kitchen/board',{cache:'no-store'}),d=await r.json();if(r.ok&&d&&d.ok&&Array.isArray(d.orders))inspect(d.orders);}catch(e){}
 }
 installButton();ensureSiteNotice();loadSoundSettings();poll();setInterval(poll,4000);setInterval(loadSoundSettings,10000);
})();
</script>
'''.replace('__PAGE__', page)
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
