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
#phase6-site-order-notice{display:none;position:fixed;top:10px;left:50%;transform:translateX(-50%);z-index:2147483000;align-items:center;white-space:normal;max-width:calc(100vw - 24px);text-align:center;font-size:16px;font-weight:900;color:#111;background:#ffd21f;border:2px solid #fff3a6;border-radius:10px;padding:11px 16px;text-transform:uppercase;letter-spacing:.4px;box-shadow:0 10px 30px rgba(0,0,0,.45);pointer-events:auto;cursor:pointer}
#phase6-site-order-notice.show{display:inline-flex;animation:phase6SiteTextPulse .8s ease-in-out 4}
@keyframes phase6SiteTextPulse{0%,100%{filter:none}50%{filter:brightness(1.18);box-shadow:0 0 0 5px rgba(255,90,54,.28),0 12px 34px rgba(0,0,0,.5)}}
</style>
<script>
(function(){
 const PAGE='__PAGE__';
 const SOUND_KEY='bechefaa_phase33_sound';
 function safeSet(key,value){try{localStorage.setItem(key,value)}catch(_){}}
 const PENDING_NOTICE='bechefaa_pending_notice_'+PAGE;
 const LAST_KEY='bechefaa_ready_notices_v5_'+PAGE;
 const PRINT_ENABLED=__PRINT_ENABLED__;
 let seen={};try{seen=JSON.parse(localStorage.getItem(LAST_KEY)||'{}')}catch(e){}
 if(!seen||typeof seen!=='object'||Array.isArray(seen))seen={};
 let initialized=Object.keys(seen).length>0;
 let pendingBeep=false;
 let audioCtx=null;
 let wanted=true;
 let unlocking=false;
 let soundSettings={enabled:true,volume:.82};
 safeSet(SOUND_KEY,'1');

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
       if(p&&typeof p.then==='function')await Promise.race([p,new Promise(resolve=>setTimeout(resolve,1200))]);
     }
   }catch(e){}
   unlocking=false;
   if(ctx.state!=='running'){updateButton();return false}
   wanted=true;safeSet(SOUND_KEY,'1');updateButton();
   if(test||pendingBeep)beep();
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
 // Reuse the configured POS beep for Deliveroo; never add a separate sound.
 if(PAGE==='pos')window.bechefaaNotifyDeliveroo=()=>{beep();};
 function beep(){
   try{
     const ctx=getCtx();if(!soundSettings.enabled||soundSettings.volume<=0||!wanted)return;
     if(!ctx||ctx.state!=='running'){pendingBeep=true;updateButton();return;}
     pendingBeep=false;updateButton();
     const t=ctx.currentTime+.015,v=soundSettings.volume;
     tone(ctx,t,920,.22,v*.88);tone(ctx,t+.28,1080,.22,v*.95);tone(ctx,t+.56,920,.30,v);
   }catch(e){}
 }
 function updateButton(){
   let button=document.getElementById('bechefaa-audio-wait');
   if(!pendingBeep||isAudioReady()||!soundSettings.enabled||soundSettings.volume<=0){if(button)button.remove();return;}
   if(!button){button=document.createElement('button');button.id='bechefaa-audio-wait';button.type='button';button.style.cssText='position:fixed;bottom:14px;left:14px;z-index:2147483001;max-width:calc(100vw - 28px);padding:12px;background:#ffd21f;color:#111;border:2px solid white;border-radius:10px;font-weight:900';button.textContent='Alerte reçue — toucher pour activer le son';button.onclick=()=>unlock(true);document.body.appendChild(button);}
 }
 function installButton(){
   if(!__TEST_MODE__)return;
   const panel=document.createElement('section');
   panel.style.cssText='position:fixed;bottom:18px;left:18px;z-index:50001;background:white;color:#111;padding:16px;border:3px solid #d99a18;border-radius:12px;max-width:340px;box-shadow:0 4px 20px #0004';
   panel.innerHTML='<b>Test des alertes '+(PAGE==='pos'?'caisse':'cuisine')+'</b><p>Aucune commande enregistrée, aucun paiement, aucune impression.</p><button type="button">Simuler une arrivée</button> <button type="button">Fermer</button><p role="status"></p>';
   const buttons=panel.querySelectorAll('button'),status=panel.querySelector('[role="status"]');
   buttons[0].onclick=async function(){
     buttons[0].disabled=true;
     try{
       await unlock(false);await loadSoundSettings();
       const order={id:'notification-test-'+Date.now(),num:0,status:'À préparer',sales_channel:'SITE',customer_name:'TEST DES ALERTES',ticket_type:'À emporter',updated_at:Date.now()};
       const detected=inspect([order],{simulation:true});
       status.textContent=(detected?'Arrivée détectée. ':'Arrivée non détectée. ')+(soundSettings.enabled&&soundSettings.volume>0?(isAudioReady()?'Son déclenché : vérifiez que vous entendez le bip.':'Son bloqué par le navigateur. Touchez puis réessayez.'):'Son désactivé ou volume à zéro dans les réglages.');
     }catch(e){status.textContent='Test impossible : '+e.message}
     finally{buttons[0].disabled=false}
   };
   buttons[1].onclick=()=>panel.remove();document.body.appendChild(panel);
 }
 function unlockOnInteraction(){
   if(!soundSettings.enabled||isAudioReady()||unlocking)return;
   const ctx=getCtx();
   if(!ctx)return;
   try{
     const p=ctx.resume();
     if(p&&typeof p.then==='function'){
       p.then(()=>{wanted=true;safeSet(SOUND_KEY,'1');updateButton();if(pendingBeep)beep();}).catch(()=>updateButton());
     }else{
       wanted=true;safeSet(SOUND_KEY,'1');updateButton();
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

 let siteNoticeTimer=null;
 function scheduleSiteNoticeDismiss(el){
   if(siteNoticeTimer)clearTimeout(siteNoticeTimer);
   siteNoticeTimer=setTimeout(()=>{
     el.classList.remove('show');
     try{sessionStorage.removeItem(PENDING_NOTICE)}catch(_){}
     siteNoticeTimer=null;
   },8000);
 }
 function ensureSiteNotice(){
   if(PAGE!=='pos')return null;
   let el=document.getElementById('phase6-site-order-notice');if(el)return el;
   el=document.createElement('span');el.id='phase6-site-order-notice';el.setAttribute('role','button');el.setAttribute('aria-live','assertive');el.tabIndex=0;function dismiss(){el.classList.remove('show');try{sessionStorage.removeItem(PENDING_NOTICE)}catch(_){}}el.addEventListener('click',dismiss);el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' ')dismiss();});document.body.appendChild(el);return el;
 }
 function showSiteNotice(order,simulation=false){
   if(PAGE!=='pos')return;
   const el=ensureSiteNotice();if(!el)return;
   const name=String(order.customer_name||'Client').trim();
   const mode=String(order.ticket_type||'').toLowerCase().includes('livraison')?'Livraison':'À emporter';
   el.textContent=(simulation?'TEST — ':'⚡ NOUVELLE COMMANDE SITE — ')+name+' • '+mode;
   el.classList.remove('show');void el.offsetWidth;el.classList.add('show');
   scheduleSiteNoticeDismiss(el);
   if(!simulation){try{sessionStorage.setItem(PENDING_NOTICE,JSON.stringify({order:{id:order.id,customer_name:order.customer_name,ticket_type:order.ticket_type},at:Date.now()}))}catch(_){}}
 }

 const SITE_PRINT_KEY='bechefaa_site_prints_v2';
 let printing=false,printTimer=null;
 function autoPrintSiteOrder(order){
   if(!PRINT_ENABLED||PAGE!=='pos'||!/Android/i.test(navigator.userAgent||'')||!order||!order.id||printing)return;
   let printed={};try{printed=JSON.parse(localStorage.getItem(SITE_PRINT_KEY)||'{}')}catch(e){}
   if(printed[order.id])return;
   if(typeof window.bechefaaPrintOrderPack!=='function'){
     const el=ensureSiteNotice();
     if(el){el.textContent='Impression automatique indisponible — imprimer les tickets manuellement';el.classList.add('show');}
     console.error('BÉCHÉFAA: fonction Epson bechefaaPrintOrderPack absente');
     return;
   }
   printing=true;
   // Reserve this launch before leaving the page for Epson; other orders remain pending.
   printed[order.id]=Date.now();safeSet(SITE_PRINT_KEY,JSON.stringify(printed));
   Promise.resolve().then(()=>window.bechefaaPrintOrderPack(order.id)).then(result=>{
     if(result===false)throw new Error('Epson a refusé le lancement');
   }).catch(e=>{
     // Ne pas relancer automatiquement : une tentative Epson peut avoir abouti
     // malgré une erreur de retour. La reprise est manuelle pour éviter les doublons.
     printing=false;
     console.error('BÉCHÉFAA: impression automatique non confirmée',e);
     const el=ensureSiteNotice();if(el){el.textContent='Impression non confirmée — vérifier les tickets puis imprimer manuellement si nécessaire';el.classList.add('show');}
   });
 }

 function inspect(orders,{simulation=false}={}){
   const known=simulation?{}:seen;
   const wasInitialized=simulation?false:initialized;
   const active=(orders||[]).filter(o=>o.id&&['À préparer','En préparation','Prête','Terminée'].includes(String(o.status||'').trim()));
   const eligible=PAGE==='pos'?active.filter(o=>String(o.sales_channel||'').toUpperCase()==='SITE'):active.filter(o=>String(o.status||'').trim()==='À préparer');
   const fresh=[];
   for(const order of eligible){
     if(known[order.id])continue;
     const ts=Number(order.updated_at||order.created_at||0);
     if(wasInitialized||(ts>0&&Date.now()-ts<10*60*1000))fresh.push(order);
     known[order.id]=Date.now();
   }
   // Track identities only after kitchen admission: order numbers need not arrive in order.
   if(!simulation){
     initialized=true;
     const entries=Object.entries(known).sort((a,b)=>b[1]-a[1]).slice(0,500);
     seen=Object.fromEntries(entries);safeSet(LAST_KEY,JSON.stringify(seen));
   }
   if(fresh.length){if(PAGE==='pos')showSiteNotice(fresh[fresh.length-1],simulation);beep();}
   if(PRINT_ENABLED&&!simulation){
     // Retry unlaunched recent orders on return from Epson, not merely the newest order.
     const toPrint=eligible.filter(o=>String(o.status||'').trim()==='À préparer').filter(o=>{
       const ts=Number(o.updated_at||o.created_at||0);return ts>0&&Date.now()-ts<10*60*1000;
     }).sort((a,b)=>Number(a.num)-Number(b.num));
     if(!printing&&!printTimer&&toPrint.length)printTimer=setTimeout(()=>{printTimer=null;for(const order of toPrint){autoPrintSiteOrder(order);if(printing)break;}},1200);
   }
   return fresh.length;
 }
 let pollBusy=false,connectionFailures=0,connectionFailureSince=0;
 function connectionRecovered(){
   connectionFailures=0;connectionFailureSince=0;
   const warning=document.getElementById('bechefaa-alert-connection');if(warning)warning.remove();
 }
 function connectionFailed(){
   connectionFailures++;
   if(connectionFailures===1)connectionFailureSince=Date.now();
   // A single failed request does not mean that alerts have stopped.
   if(connectionFailures<3||Date.now()-connectionFailureSince<8000)return;
   let warning=document.getElementById('bechefaa-alert-connection');
   if(!warning){warning=document.createElement('div');warning.id='bechefaa-alert-connection';warning.setAttribute('role','status');warning.style.cssText='position:fixed;bottom:60px;left:14px;z-index:2147483001;background:#991b1b;color:white;padding:10px;border-radius:8px;max-width:90vw';document.body.appendChild(warning);}
   warning.textContent='Connexion aux alertes interrompue — reconnexion automatique…';
 }
 async function poll(){
   if(pollBusy)return;pollBusy=true;
   const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
   let orders;
   try{
     const endpoint=PAGE==='kitchen'?'/api/kitchen/orders':'/api/kitchen/board';
     const r=await fetch(endpoint,{cache:'no-store',signal:controller.signal}),d=await r.json();
     if(!r.ok||!d||!d.ok||!Array.isArray(d.orders))throw Error('Alertes indisponibles');
     orders=d.orders;connectionRecovered();
   }catch(e){connectionFailed();}
   finally{clearTimeout(timer);pollBusy=false;}
   // Rendering errors must not be reported as a lost server connection.
   if(orders){try{inspect(orders);}catch(e){console.error('Affichage des alertes impossible',e);}}
 }
 function resumeAlerts(){if(document.hidden)return;printing=false;retryUnlockIfAllowed();loadSoundSettings();poll();}
 window.addEventListener('bechefaa:print-return',resumeAlerts);
 window.addEventListener('pageshow',resumeAlerts);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)resumeAlerts();});
 try{const pending=JSON.parse(sessionStorage.getItem(PENDING_NOTICE)||'null');if(pending&&pending.order&&Date.now()-pending.at<15*60*1000){showSiteNotice(pending.order);pendingBeep=true;updateButton();}}catch(_){}

 installButton();ensureSiteNotice();loadSoundSettings();poll();setInterval(poll,4000);setInterval(loadSoundSettings,10000);
})();
</script>
'''.replace('__PAGE__', page).replace('__PRINT_ENABLED__', 'true' if request.path == '/pos' else 'false').replace('__TEST_MODE__', 'true' if request.args.get('test_notifications') == '1' else 'false')
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
