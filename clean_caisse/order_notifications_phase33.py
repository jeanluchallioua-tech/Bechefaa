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
@keyframes phase33pulse{50%{transform:scale(1.015);box-shadow:0 0 0 4px rgba(217,119,6,.25)}}
</style>
<script>
(function(){
 let initialized=false, known=new Set();
 function sourceInfo(source){
   const s=String(source||'').trim().toUpperCase();
   if(s.includes('UBER')) return {label:'UBER EATS',cls:'phase33-uber'};
   if(s.includes('DELIVEROO')) return {label:'DELIVEROO',cls:'phase33-deliveroo'};
   if(s.includes('WIX')||s.includes('SITE')||s.includes('WEB')) return {label:'SITE INTERNET',cls:'phase33-site'};
   return {label:'CAISSE',cls:'phase33-caisse'};
 }
 function beep(){
   try{
     const C=window.AudioContext||window.webkitAudioContext;if(!C)return;
     const ctx=new C(),osc=ctx.createOscillator(),gain=ctx.createGain();
     osc.type='sine';osc.frequency.value=880;gain.gain.setValueAtTime(.12,ctx.currentTime);gain.gain.exponentialRampToValueAtTime(.001,ctx.currentTime+.35);
     osc.connect(gain);gain.connect(ctx.destination);osc.start();osc.stop(ctx.currentTime+.35);setTimeout(()=>ctx.close(),500);
   }catch(e){}
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
