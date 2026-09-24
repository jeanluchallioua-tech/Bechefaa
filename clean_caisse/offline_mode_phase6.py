"""Mode hors connexion Phase 6 pour la caisse BÉCHÉFAA.

- Service Worker racine
- cache du POS et du catalogue
- file IndexedDB des commandes hors ligne
- synchronisation automatique au retour du réseau
"""
from flask import Response

SW_JS = r"""
const CACHE='bechefaa-pos-offline-v2';
const DB='bechefaa-offline-v1';
const STORE='orders';

function dbOpen(){
  return new Promise((resolve,reject)=>{
    const r=indexedDB.open(DB,1);
    r.onupgradeneeded=()=>{const db=r.result;if(!db.objectStoreNames.contains(STORE))db.createObjectStore(STORE,{keyPath:'offline_id'})};
    r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);
  });
}
async function putOrder(row){const db=await dbOpen();return new Promise((res,rej)=>{const tx=db.transaction(STORE,'readwrite');tx.objectStore(STORE).put(row);tx.oncomplete=()=>res();tx.onerror=()=>rej(tx.error)})}
async function getOrder(id){const db=await dbOpen();return new Promise((res,rej)=>{const r=db.transaction(STORE).objectStore(STORE).get(id);r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error)})}
async function allOrders(){const db=await dbOpen();return new Promise((res,rej)=>{const r=db.transaction(STORE).objectStore(STORE).getAll();r.onsuccess=()=>res(r.result||[]);r.onerror=()=>rej(r.error)})}
async function delOrder(id){const db=await dbOpen();return new Promise((res,rej)=>{const tx=db.transaction(STORE,'readwrite');tx.objectStore(STORE).delete(id);tx.oncomplete=()=>res();tx.onerror=()=>rej(tx.error)})}
function json(data,status=200){return new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'}})}
function totalOf(body){return (body.items||[]).reduce((s,x)=>s+Number(x.unit_price||0)*Number(x.qty||1),0)}
function ticketType(body){return String(body.ticket_type||'').toLowerCase()==='livraison'?'Livraison':'Comptoir'}
function offlineId(){return 'offline-'+Date.now()+'-'+Math.random().toString(36).slice(2,10)}

self.addEventListener('install',event=>{
  event.waitUntil((async()=>{
    const c=await caches.open(CACHE);
    await Promise.allSettled([c.add('/pos'),c.add('/api/catalog/summary')]);
    await self.skipWaiting();
  })());
});
self.addEventListener('activate',event=>event.waitUntil((async()=>{
  const keys=await caches.keys();
  await Promise.all(keys.filter(k=>k.startsWith('bechefaa-pos-offline-')&&k!==CACHE).map(k=>caches.delete(k)));
  await self.clients.claim();
})()));

async function cachedGet(req){
  const c=await caches.open(CACHE);
  try{
    const net=await fetch(req);
    if(net.ok)c.put(req,net.clone());
    return net;
  }catch(e){
    const hit=await c.match(req);
    if(hit)return hit;
    throw e;
  }
}

async function syncOrders(){
  const rows=(await allOrders()).sort((a,b)=>(a.created_at||0)-(b.created_at||0));
  let synced=0;
  const printOrderIds=[];
  for(const row of rows){
    try{
      const r=await fetch('/api/orders',{
        method:'POST',
        headers:{'Content-Type':'application/json','X-BECHEFAA-OFFLINE-ID':row.offline_id},
        body:JSON.stringify(row.body)
      });
      const d=await r.json();
      if(!r.ok||!d.ok)continue;
      if(row.send_kitchen){
        try{
          const kr=await fetch('/api/orders/'+encodeURIComponent(d.id)+'/send-kitchen',{method:'POST'});
          if(!kr.ok)continue;
          printOrderIds.push(d.id);
        }catch(e){continue}
      }
      await delOrder(row.offline_id);synced++;
    }catch(e){break}
  }
  const remain=(await allOrders()).length;
  const cs=await self.clients.matchAll({includeUncontrolled:true,type:'window'});
  cs.forEach(c=>c.postMessage({type:'offline-sync-result',synced,pending:remain,print_order_ids:printOrderIds}));
  return {synced,pending:remain,print_order_ids:printOrderIds};
}

self.addEventListener('message',event=>{
  if(event.data&&event.data.type==='offline-sync') event.waitUntil(syncOrders());
  if(event.data&&event.data.type==='offline-count') event.waitUntil((async()=>{
    const pending=(await allOrders()).length;
    if(event.source)event.source.postMessage({type:'offline-count-result',pending});
  })());
});

self.addEventListener('fetch',event=>{
  const url=new URL(event.request.url);
  if(url.origin!==location.origin)return;

  if(event.request.method==='GET' && (
      url.pathname==='/pos' ||
      url.pathname==='/api/catalog/summary' ||
      url.pathname.startsWith('/api/catalog/product/')
  )){
    event.respondWith(cachedGet(event.request));
    return;
  }

  if(event.request.method==='POST' && url.pathname==='/api/orders'){
    event.respondWith((async()=>{
      try{return await fetch(event.request.clone())}
      catch(e){
        const body=await event.request.clone().json();
        const id=offlineId();
        const row={offline_id:id,body,created_at:Date.now(),send_kitchen:false};
        await putOrder(row);
        const n=String((await allOrders()).length);
        const cs=await self.clients.matchAll({includeUncontrolled:true,type:'window'});
        cs.forEach(c=>c.postMessage({type:'offline-count-result',pending:Number(n)}));
        return json({
          ok:true,id,num:'HL-'+n,total:totalOf(body),
          status:'Hors connexion - en attente de synchronisation',
          ticket_type:ticketType(body),offline:true
        },201);
      }
    })());
    return;
  }

  const kitchenMatch=url.pathname.match(/^\/api\/orders\/(offline-[^/]+)\/send-kitchen$/);
  if(event.request.method==='POST' && kitchenMatch){
    event.respondWith((async()=>{
      const id=decodeURIComponent(kitchenMatch[1]);
      const row=await getOrder(id);
      if(!row)return json({ok:false,error:'Commande locale introuvable'},404);
      row.send_kitchen=true;await putOrder(row);
      return json({
        ok:false,
        error:'Commande conservée hors connexion. Elle sera envoyée en cuisine automatiquement au retour d’Internet.',
        offline:true
      },503);
    })());
  }
});
"""

UI = r"""
<style id="bechefaa-offline-style">
#bechefaa-offline-bar{position:fixed;left:0;right:0;bottom:0;z-index:99999;padding:9px 14px;text-align:center;font:800 13px Arial,sans-serif;box-shadow:0 -2px 10px #0003;display:none}
#bechefaa-offline-bar.off{display:block;background:#991b1b;color:white}
#bechefaa-offline-bar.sync{display:block;background:#b45309;color:white}
#bechefaa-offline-bar.ok{display:block;background:#166534;color:white}
</style>
<div id="bechefaa-offline-bar"></div>
<script id="bechefaa-offline-ui">
(function(){
 const bar=document.getElementById('bechefaa-offline-bar');
 let pending=0,hideTimer=null;
 function render(kind,msg){
   clearTimeout(hideTimer);bar.className=kind;bar.textContent=msg;
   if(kind==='ok')hideTimer=setTimeout(()=>{bar.className='';bar.textContent=''},4500);
 }
 function update(){
   if(!navigator.onLine) render('off','HORS CONNEXION • '+pending+' commande(s) en attente • paiements en ligne indisponibles');
   else if(pending>0) render('sync','Synchronisation en attente • '+pending+' commande(s) locale(s)');
 }
 function count(){if(navigator.serviceWorker.controller)navigator.serviceWorker.controller.postMessage({type:'offline-count'})}
 function sync(){if(navigator.serviceWorker.controller)navigator.serviceWorker.controller.postMessage({type:'offline-sync'})}
 if('serviceWorker' in navigator){
   navigator.serviceWorker.register('/caisse-sw.js',{scope:'/'}).then(async reg=>{
     await navigator.serviceWorker.ready;
     count();
     if(navigator.onLine)sync();
     try{
       const d=await fetch('/api/catalog/summary',{cache:'no-store'}).then(r=>r.json());
       const items=(d&&d.items)||[];
       for(const p of items){if(p&&p.id)fetch('/api/catalog/product/'+encodeURIComponent(p.id)+'/options').catch(()=>{})}
     }catch(e){}
   }).catch(()=>{});
 }
 navigator.serviceWorker&&navigator.serviceWorker.addEventListener('message',e=>{
   const d=e.data||{};
   if(d.type==='offline-count-result'){pending=Number(d.pending||0);update()}
   if(d.type==='offline-sync-result'){
     pending=Number(d.pending||0);
     if(pending===0&&Number(d.synced||0)>0)render('ok','Synchronisation terminée • '+d.synced+' commande(s) envoyée(s)');
     else if(pending>0&&!navigator.onLine)render('off','HORS CONNEXION • '+pending+' commande(s) en attente • paiements en ligne indisponibles');
     else update();
   }
 });
 window.addEventListener('offline',()=>{update()});
 window.addEventListener('online',()=>{update();sync()});
 setInterval(()=>{count();if(navigator.onLine&&pending>0)sync()},15000);
 update();
})();
</script>
"""


def register_offline_mode_phase6(app):
    @app.get("/offline-sw.js")
    def offline_sw_phase6():
        response = Response(SW_JS, status=200, content_type="application/javascript; charset=utf-8")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Service-Worker-Allowed"] = "/"
        return response

    @app.after_request
    def inject_offline_ui_phase6(response):
        if request_path_is_pos(response):
            html = response.get_data(as_text=True)
            if 'id="bechefaa-offline-ui"' not in html:
                html = html.replace("</body>", UI + "</body>")
                response.set_data(html)
                response.content_length = len(response.get_data())
        return response


def request_path_is_pos(response):
    from flask import request
    return request.path == "/pos" and response.status_code == 200 and response.mimetype == "text/html"
