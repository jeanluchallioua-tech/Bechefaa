"""Phase 3.3 — notifications visuelles et sonores des nouvelles commandes.

Correctif isolé : aucune écriture PostgreSQL, aucun changement de commande/ticket/TVA.
Le choix sonore est mémorisé côté navigateur et la surveillance fonctionne sur Cuisine et Caisse.
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
.phase33-source{position:absolute;right:12px;bottom:12px;z-index:2;display:inline-block;padding:5px 9px;border-radius:7px;font-size:12px;font-weight:900;color:#fff;letter-spacing:.2px;pointer-events:none}
.phase33-caisse{background:#2563eb}.phase33-site{background:#16a34a}.phase33-uber{background:#111827}.phase33-deliveroo{background:#0d9488}
.card{position:relative}
.phase33-new{outline:3px solid rgba(217,119,6,.35);outline-offset:2px}
.phase33-audio{border:0;border-radius:8px;padding:9px 12px;font-weight:800;cursor:pointer;background:#dc2626;color:#fff}
.phase33-audio.on{background:#16a34a}
.phase33-audio-float{position:fixed;right:14px;bottom:14px;z-index:9999;box-shadow:0 3px 14px rgba(0,0,0,.2)}
</style>
<script>
(function(){
 const STORAGE_KEY='bechefaa_phase33_sound';
 const isKitchen=location.pathname==='/cuisine-preparation';
 let initialized=false,known=new Set(),audioCtx=null;
 let audioEnabled=localStorage.getItem(STORAGE_KEY)==='1';

 function sourceInfo(source){
   const s=String(source||'').trim().toUpperCase();
   if(s.includes('UBER')) return {label:'UBER EATS',cls:'phase33-uber'};
   if(s.includes('DELIVEROO')) return {label:'DELIVEROO',cls:'phase33-deliveroo'};
   if(s.includes('WIX')||s.includes('SITE')||s.includes('WEB')) return {label:'SITE INTERNET',cls:'phase33-site'};
   return {label:'CAISSE',cls:'phase33-caisse'};
 }
 function ensureAudio(){
   try{
     const C=window.AudioContext||window.webkitAudioContext;if(!C)return false;
     if(!audioCtx)audioCtx=new C();
     const p=audioCtx.state==='suspended'?audioCtx.resume():null;
     audioEnabled=true;localStorage.setItem(STORAGE_KEY,'1');
     return true;
   }catch(e){return false}
 }
 function beep(){
   try{
     if(!audioEnabled)return;
     if(!audioCtx){
       const C=window.AudioContext||window.webkitAudioContext;if(!C)return;
       audioCtx=new C();
     }
     if(audioCtx.state!=='running')return;
     const osc=audioCtx.createOscillator(),gain=audioCtx.createGain();
     osc.type='sine';osc.frequency.value=880;
     gain.gain.setValueAtTime(.16,audioCtx.currentTime);
     gain.gain.exponentialRampToValueAtTime(.001,audioCtx.currentTime+.45);
     osc.connect(gain);gain.connect(audioCtx.destination);osc.start();osc.stop(audioCtx.currentTime+.45);
   }catch(e){}
 }
 function updateButton(){
   const btn=document.getElementById('phase33-audio');if(!btn)return;
   btn.classList.toggle('on',audioEnabled);
   btn.textContent=audioEnabled?'🔊 Son activé':'🔇 Activer le son';
 }
 function installAudioButton(){
   if(document.getElementById('phase33-audio'))return;
   const btn=document.createElement('button');btn.id='phase33-audio';btn.className='phase33-audio';
   const top=document.querySelector('.top');
   if(top)top.appendChild(btn);else{btn.classList.add('phase33-audio-float');document.body.appendChild(btn)}
   btn.onclick=function(){
     if(audioEnabled){audioEnabled=false;localStorage.setItem(STORAGE_KEY,'0');if(audioCtx)audioCtx.close().catch(()=>{});audioCtx=null;updateButton();return}
     if(ensureAudio()){updateButton();setTimeout(beep,80)}else alert('Le son ne peut pas être activé sur ce navigateur.');
   };
   updateButton();
 }
 function resumeOnUserAction(){
   if(!audioEnabled)return;
   ensureAudio();
   updateButton();
 }
 document.addEventListener('pointerdown',resumeOnUserAction,{passive:true});
 document.addEventListener('keydown',resumeOnUserAction,{passive:true});

 function decorateAndNotify(orders){
   const active=(orders||[]).filter(o=>o.status==='À préparer'||o.status==='En préparation');
   const current=new Set(active.map(o=>String(o.id)));
   if(isKitchen){
     document.querySelectorAll('.card').forEach(card=>{
       const num=(card.querySelector('.num')||{}).textContent||'';
       const order=active.find(o=>num.startsWith('#'+o.num+' ')||num.startsWith('#'+o.num+' ·'));
       if(!order)return;
       const info=sourceInfo(order.source);
       if(!card.querySelector('.phase33-source')){const b=document.createElement('div');b.className='phase33-source '+info.cls;b.textContent=info.label;card.appendChild(b)}
       if(initialized&&!known.has(String(order.id))&&order.status==='À préparer'){
         card.classList.add('phase33-new');setTimeout(()=>card.classList.remove('phase33-new'),1800);
       }
     });
   }
   if(initialized&&active.some(o=>o.status==='À préparer'&&!known.has(String(o.id))))beep();
   known=current;initialized=true;
 }
 async function poll(){
   try{
     const r=await fetch('/api/kitchen/board',{cache:'no-store'}),d=await r.json();
     if(r.ok&&d&&d.ok&&Array.isArray(d.orders))setTimeout(()=>decorateAndNotify(d.orders),isKitchen?40:0);
   }catch(e){}
 }

 installAudioButton();
 if(audioEnabled){
   try{const C=window.AudioContext||window.webkitAudioContext;if(C)audioCtx=new C()}catch(e){}
 }
 poll();setInterval(poll,5000);
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
