"""Phase 3.3 / Phase 6 — notifications des nouvelles commandes.

Correctif isolé : aucune écriture PostgreSQL, aucun changement de commande/ticket/TVA.
- Cuisine et Caisse utilisent des marqueurs de dernière commande distincts.
- Sur /pos, seules les commandes provenant du SITE déclenchent l'alerte Caisse.
- Les commandes saisies directement en Caisse restent silencieuses sur /pos,
  mais déclenchent normalement la notification Cuisine après envoi.
- Le son Caisse et Cuisine est activé par défaut et se déverrouille automatiquement
  à la première interaction normale avec l'écran, sans bouton supplémentaire.
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
        if request.path not in ("/cuisine-preparation", "/pos", "/historique-modification", "/administration") or response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        page = "kitchen" if request.path == "/cuisine-preparation" else "pos"
        addon = r'''
<style>
#phase6-site-order-notice{display:none;position:fixed;top:10px;left:50%;transform:translateX(-50%);z-index:50000;align-items:center;white-space:nowrap;font-size:16px;font-weight:900;color:#111;background:#ffd21f;border:2px solid #fff3a6;border-radius:10px;padding:11px 16px;text-transform:uppercase;letter-spacing:.4px;box-shadow:0 10px 30px rgba(0,0,0,.45);pointer-events:none}
#phase6-site-order-notice.show{display:inline-flex;animation:phase6SiteTextPulse .8s ease-in-out 4}
@keyframes phase6SiteTextPulse{0%,100%{filter:none}50%{filter:brightness(1.18);box-shadow:0 0 0 5px rgba(255,90,54,.28),0 12px 34px rgba(0,0,0,.5)}}
</style>
<script>
(function(){
 const PAGE='__PAGE__';
 const SOUND_KEY='bechefaa_phase33_sound';
 const LAST_KEY='bechefaa_ready_notices_v5_'+PAGE;
 const PRINT_ENABLED=__PRINT_ENABLED__;
 let seen={};try{seen=JSON.parse(localStorage.getItem(LAST_KEY)||'{}')}catch(e){}
 let initialized=Object.keys(seen).length>0;
 let pendingBeep=false;
 let audioCtx=null;
 let wanted=true;
 let unlocking=false;
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
   if(!soundSettings.enabled||unlocking)return isAudioReady();
   unlocking=true;
   const ctx=getCtx();
   if(!ctx){unlocking=false;return false}
   try{
     if(ctx.state!=='running'){
       const p=ctx.resume();
       if(p&&typeof p.then==='function')await p;
     }
   }catch(e){}
   unlocking=false;
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
     const ctx=getCtx();if(!soundSettings.enabled||soundSettings.volume<=0||!wanted)return;
     if(!ctx||ctx.state!=='running'){pendingBeep=true;return;}
     pendingBeep=false;
     const t=ctx.currentTime+.015,v=soundSettings.volume;
     tone(ctx,t,920,.22,v*.88);tone(ctx,t+.28,1080,.22,v*.95);tone(ctx,t+.56,920,.30,v);
   }catch(e){}
 }
 function updateButton(){
   // Aucun bouton à cliquer : le son est toujours demandé par défaut.
   // Chrome/Android autorise l'audio dès la première interaction normale
   // (toucher, clic ou clavier) avec la Caisse ou la Cuisine.
 }
 function installButton(){}
 function unlockOnInteraction(){
   if(!soundSettings.enabled||isAudioReady()||unlocking)return;
   const ctx=getCtx();
   if(!ctx)return;
   try{
     const p=ctx.resume();
     if(p&&typeof p.then==='function'){
       p.then(()=>{wanted=true;localStorage.setItem(SOUND_KEY,'1');updateButton();if(pendingBeep)beep();}).catch(()=>updateButton());
     }else{
       wanted=true;localStorage.setItem(SOUND_KEY,'1');updateButton();
     }
   }catch(e){updateButton()}
 }
 ['pointerdown','mousedown','touchstart','click','keydown'].forEach(function(evt){
   document.addEventListener(evt,unlockOnInteraction,{capture:true,passive:evt!=='keydown'});
 });
 function retryUnlockIfAllowed(){
   try{
     if(soundSettings.enabled&&!isAudioReady()&&navigator.userActivation&&navigator.userActivation.hasBeenActive){
       unlock(false);
     }
   }catch(e){}
 }
 window.addEventListener('pageshow',retryUnlockIfAllowed);
 window.addEventListener('focus',retryUnlockIfAllowed);
 document.addEventListener('visibilitychange',function(){if(!document.hidden)retryUnlockIfAllowed();});

 function ensureSiteNotice(){
   if(PAGE!=='pos')return null;
   let el=document.getElementById('phase6-site-order-notice');if(el)return el;
   el=document.createElement('span');el.id='phase6-site-order-notice';document.body.appendChild(el);return el;
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

 const SITE_PRINT_KEY='bechefaa_site_prints_v2';
 let printing=false;
 function autoPrintSiteOrder(order){
   if(!PRINT_ENABLED||PAGE!=='pos'||!/Android/i.test(navigator.userAgent||'')||!order||!order.id||printing)return;
   let printed={};try{printed=JSON.parse(localStorage.getItem(SITE_PRINT_KEY)||'{}')}catch(e){}
   if(printed[order.id])return;
   if(typeof window.bechefaaPrintOrderPack!=='function')return;
   printing=true;
   // Reserve this launch before leaving the page for Epson; other orders remain pending.
   printed[order.id]=Date.now();localStorage.setItem(SITE_PRINT_KEY,JSON.stringify(printed));
   Promise.resolve(window.bechefaaPrintOrderPack(order.id)).catch(e=>{
     delete printed[order.id];localStorage.setItem(SITE_PRINT_KEY,JSON.stringify(printed));printing=false;
     const el=ensureSiteNotice();if(el){el.textContent='Impression impossible — commande conservée';el.classList.add('show');}
   });
 }

 function inspect(orders){
   const active=(orders||[]).filter(o=>o.id&&['À préparer','En préparation','Prête','Terminée'].includes(String(o.status||'').trim()));
   const eligible=PAGE==='pos'?active.filter(o=>String(o.sales_channel||'').toUpperCase()==='SITE'):active.filter(o=>String(o.status||'').trim()==='À préparer');
   const fresh=[];
   for(const order of eligible){
     if(seen[order.id])continue;
     const ts=Number(order.updated_at||order.created_at||0);
     if(initialized||(ts>0&&Date.now()-ts<10*60*1000))fresh.push(order);
     seen[order.id]=Date.now();
   }
   // Track identities only after kitchen admission: order numbers need not arrive in order.
   initialized=true;
   const entries=Object.entries(seen).sort((a,b)=>b[1]-a[1]).slice(0,500);
   seen=Object.fromEntries(entries);localStorage.setItem(LAST_KEY,JSON.stringify(seen));
   if(fresh.length){if(PAGE==='pos')showSiteNotice(fresh[fresh.length-1]);beep();}
   if(PRINT_ENABLED){
     // Retry unlaunched recent orders on return from Epson, not merely the newest order.
     const toPrint=eligible.filter(o=>String(o.status||'').trim()==='À préparer').filter(o=>{
       const ts=Number(o.updated_at||o.created_at||0);return ts>0&&Date.now()-ts<10*60*1000;
     }).sort((a,b)=>Number(a.num)-Number(b.num));
     for(const order of toPrint){autoPrintSiteOrder(order);if(printing)break;}
   }
 }
 async function poll(){
   try{const r=await fetch('/api/kitchen/board',{cache:'no-store'}),d=await r.json();if(r.ok&&d&&d.ok&&Array.isArray(d.orders))inspect(d.orders);}catch(e){}
 }
 installButton();ensureSiteNotice();loadSoundSettings();poll();setInterval(poll,4000);setInterval(loadSoundSettings,10000);
})();
</script>
'''.replace('__PAGE__', page).replace('__PRINT_ENABLED__', 'true' if request.path == '/pos' else 'false')
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
