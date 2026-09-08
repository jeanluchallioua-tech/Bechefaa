"""Phase 3.3 — notifications visuelles et sonores des nouvelles commandes cuisine.

Correctif isolé : aucune écriture PostgreSQL, aucun changement de commande/ticket/TVA.
La couleur dépend de la source déjà stockée sur la commande.
"""
from flask import request


def register_order_notifications_phase33(app):
    @app.after_request
    def inject_order_notifications_phase33(response):
        if request.path != "/cuisine-preparation" or response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        addon = r'''
<style>
.phase33-source{display:inline-block;margin-top:6px;padding:5px 9px;border-radius:7px;font-size:12px;font-weight:900;color:#fff;letter-spacing:.2px}
.phase33-caisse{background:#2563eb}.phase33-site{background:#16a34a}.phase33-uber{background:#111827}.phase33-deliveroo{background:#0d9488}
.phase33-new{animation:phase33pulse .65s ease-in-out 3}
.phase33-audio{border:0;border-radius:8px;padding:9px 12px;font-weight:800;cursor:pointer;background:#dc2626;color:#fff}
.phase33-audio.on{background:#16a34a}
@keyframes phase33pulse{50%{transform:scale(1.015);box-shadow:0 0 0 4px rgba(217,119,6,.25)}}
</style>
<script>
(function(){
 let initialized=false, known=new Set(),audioCtx=null,audioEnabled=false;
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
     if(audioCtx.state==='suspended')audioCtx.resume();
     audioEnabled=true;
     return true;
   }catch(e){return false}
 }
 function beep(){
   try{
     if(!audioEnabled||!audioCtx)return;
     const osc=audioCtx.createOscillator(),gain=audioCtx.createGain();
     osc.type='sine';osc.frequency.value=880;
     gain.gain.setValueAtTime(.16,audioCtx.currentTime);
     gain.gain.exponentialRampToValueAtTime(.001,audioCtx.currentTime+.45);
     osc.connect(gain);gain.connect(audioCtx.destination);osc.start();osc.stop(audioCtx.currentTime+.45);
   }catch(e){}
 }
 function installAudioButton(){
   const top=document.querySelector('.top');if(!top||document.getElementById('phase33-audio'))return;
   const btn=document.createElement('button');btn.id='phase33-audio';btn.className='phase33-audio';btn.textContent='🔇 Activer le son';
   btn.onclick=function(){
     if(ensureAudio()){
       btn.classList.add('on');btn.textContent='🔊 Son activé';
       beep();
     }else{alert('Le son ne peut pas être activé sur ce navigateur.')}
   };
   top.appendChild(btn);
 }
 function decorateAndNotify(orders){
   const active=(orders||[]).filter(o=>o.status==='À préparer'||o.status==='En préparation');
   const current=new Set(active.map(o=>String(o.id)));
   document.querySelectorAll('.card').forEach(card=>{
     const num=(card.querySelector('.num')||{}).textContent||'';
     const order=active.find(o=>num.startsWith('#'+o.num+' ' )||num.startsWith('#'+o.num+' ·'));
     if(!order)return;
     const info=sourceInfo(order.source),head=card.querySelector('.cardhead>div');
     if(head&&!head.querySelector('.phase33-source')){const b=document.createElement('div');b.className='phase33-source '+info.cls;b.textContent=info.label;head.appendChild(b)}
     if(initialized&&!known.has(String(order.id))&&order.status==='À préparer')card.classList.add('phase33-new');
   });
   if(initialized&&active.some(o=>o.status==='À préparer'&&!known.has(String(o.id))))beep();
   known=current;initialized=true;
 }
 installAudioButton();
 const originalFetch=window.fetch;
 window.fetch=async function(){
   const response=await originalFetch.apply(this,arguments);
   try{
     const url=String(arguments[0]||'');
     if(url.includes('/api/kitchen/board')||url.includes('/api/kitchen/orders')){
       const clone=response.clone(),data=await clone.json();
       if(data&&data.ok&&Array.isArray(data.orders))setTimeout(()=>decorateAndNotify(data.orders),30);
     }
   }catch(e){}
   return response;
 };
})();
</script>
'''
        html = html.replace("</body>", addon + "</body>")
        response.set_data(html)
        response.content_length = len(response.get_data())
        return response
