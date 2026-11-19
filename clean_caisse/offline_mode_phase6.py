"""Mode hors connexion Phase 6 pour la caisse BÉCHÉFAA.

- Service Worker racine
- cache du POS et du catalogue
- file IndexedDB des commandes hors ligne
- synchronisation automatique au retour du réseau
"""
from flask import Response

SW_JS = r"""
const CACHE='bechefaa-pos-offline-v5-startup';
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
function subtotalOf(body){return (body.items||[]).reduce((s,x)=>s+Number(x.unit_price||0)*Number(x.qty||1),0)}
function discountOf(body){return body.manual_discount_percent!=null?Math.round(subtotalOf(body)*Number(body.manual_discount_percent))/100:Number(body.manual_discount_amount||0)}
function totalOf(body){return Math.round((subtotalOf(body)-discountOf(body))*100)/100}
function ticketType(body){
  const mode=String(body.service_mode||body.ticket_type||'').toLowerCase();
  if(mode==='salle'||mode==='sur place'||mode==='sur_place')return 'Salle';
  if(mode==='livraison'||mode==='delivery')return 'Livraison';
  if(mode==='emporter'||mode==='takeaway'||mode==='comptoir')return 'Emporter';
  return 'Emporter';
}
function offlineId(){return 'offline-'+Date.now()+'-'+Math.random().toString(36).slice(2,10)}

// GET timeouts never apply to order writes: an uncertain POST must not be retried.
const STARTUP_TIMEOUT_MS=8000;
async function networkGet(req){
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),STARTUP_TIMEOUT_MS);
  try{return await fetch(req,{cache:'no-store',signal:controller.signal})}
  finally{clearTimeout(timer)}
}
function isShell(response){
  return response && response.ok && response.headers.get('X-BECHEFAA-POS-Shell')==='1';
}
async function saveShell(response){
  if(!isShell(response))return;
  try{await (await caches.open(CACHE)).put('/pos',response.clone())}catch(_){}
}
async function revokeShells(){
  for(const name of await caches.keys()){
    if(!name.startsWith('bechefaa-pos-offline-'))continue;
    const cache=await caches.open(name);
    for(const key of await cache.keys()){
      if(['/', '/pos'].includes(new URL(key.url).pathname))await cache.delete(key);
    }
  }
}
async function cachedShell(){
  const names=await caches.keys();
  for(const name of [CACHE,...names.filter(n=>n!==CACHE&&n.startsWith('bechefaa-pos-offline-')).reverse()]){
    const cache=await caches.open(name),hit=await cache.match('/pos');
    if(!hit || !hit.ok)continue;
    if(isShell(hit))return hit;
    // Previous versions did not mark responses. Accept the actual empty POS shell,
    // never a PIN form accidentally cached after an authentication redirect.
    const text=await hit.clone().text();
    if(text.includes('function renderOrder(')&&text.includes('id="order"'))return hit;
  }
  return null;
}
function recoveryPage(){
  return new Response('<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BÉCHÉFAA • Connexion</title><body style="font:18px Arial;background:#111827;color:white;margin:0;padding:32px"><h1>BÉCHÉFAA Caisse</h1><p>La caisse ne peut pas encore se charger. Vérifiez la connexion puis réessayez.</p><p>Les commandes déjà enregistrées localement sont conservées.</p><a href="/" style="display:inline-block;padding:16px;background:#d7b35a;color:#111;border-radius:10px">Réessayer l’ouverture</a></body></html>',{status:503,headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'}});
}
async function navigationResponse(req){
  try{
    const net=await networkGet(req);
    if(net.headers.get('X-BECHEFAA-Auth')==='required'||net.status===401||net.status===403){
      try{await revokeShells()}catch(_){}return net;
    }
    if(net.ok){await saveShell(net);return net}
    if(net.status<500)return net;
  }catch(_){}
  try{return (await cachedShell())||recoveryPage()}catch(_){return recoveryPage()}
}
self.addEventListener('install',event=>{
  event.waitUntil((async()=>{
    // Installation remains possible before PIN entry. Do not cache login HTML.
    await Promise.allSettled([
      networkGet('/pos').then(saveShell),
      cachedGet(new Request(new URL('/api/catalog/summary',location.origin))),
      cachedGet(new Request(new URL('/static/pos-pending-edit.js',location.origin)))
    ]);
    // No skipWaiting: never replace the worker underneath a running service.
  })());
});
self.addEventListener('activate',event=>event.waitUntil((async()=>{
  // Keep one previous version as a rescue copy; keep all old versions when the
  // new version has not acquired an authenticated POS shell yet.
  const current=await caches.open(CACHE),shell=await current.match('/pos');
  if(isShell(shell)){
    const old=(await caches.keys()).filter(k=>k.startsWith('bechefaa-pos-offline-')&&k!==CACHE);
    await Promise.all(old.slice(0,-1).map(k=>caches.delete(k)));
  }
  await self.clients.claim();
})()));

async function cachedGet(req){
  let c=null;try{c=await caches.open(CACHE)}catch(_){}
  try{
    const net=await networkGet(req);
    if(net.status===401||net.status===403||net.headers.get('X-BECHEFAA-Auth')==='required')return net;
    const isScript=new URL(req.url,location.origin).pathname.endsWith('.js');
    const correctType=!isScript||/javascript/.test(net.headers.get('Content-Type')||'');
    if(net.ok&&!net.redirected&&correctType){try{if(c)await c.put(req,net.clone())}catch(_){}return net}
    if(net.status<500)return net;
  }catch(_){}
  const names=await caches.keys();
  for(const name of [CACHE,...names.filter(n=>n!==CACHE&&n.startsWith('bechefaa-pos-offline-')).reverse()]){
    const hit=await (await caches.open(name)).match(req,{ignoreSearch:new URL(req.url,location.origin).pathname.endsWith('.js')});
    if(hit)return hit;
  }
  return json({ok:false,error:'Connexion indisponible et ressource absente du cache.'},503);
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

  if(event.request.method==='GET' && ['/', '/pos'].includes(url.pathname)){
    event.respondWith(navigationResponse(event.request));return;
  }
  if(event.request.method==='GET' && url.pathname==='/auth/logout'){
    event.respondWith((async()=>{const net=await fetch(event.request);if(net.ok){try{await revokeShells()}catch(_){}}return net})());return;
  }

  if(event.request.method==='GET' && (
      url.pathname==='/api/catalog/summary' ||
      url.pathname==='/static/pos-pending-edit.js' ||
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
          ok:true,id,num:'HL-'+n,total:totalOf(body),discount_amount:discountOf(body),manual_discount_percent:body.manual_discount_percent??null,subtotal_before_discount:subtotalOf(body),
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
   navigator.serviceWorker.register('/caisse-sw.js',{scope:'/',updateViaCache:'none'}).then(async reg=>{
     function waitingNotice(){
       if(!reg.waiting||document.getElementById('bechefaa-update-note'))return;
       const note=document.createElement('div');note.id='bechefaa-update-note';
       note.style.cssText='position:fixed;right:12px;bottom:52px;max-width:360px;padding:10px 14px;border:1px solid #d7b35a;border-radius:10px;background:#111827;color:white;font:14px Arial;z-index:99990';
       note.textContent='Mise à jour prête. Après le service, fermez les écrans de caisse puis rouvrez l’application pour l’activer.';
       document.body.appendChild(note);
     }
     waitingNotice();
     reg.addEventListener('updatefound',()=>{const worker=reg.installing;if(worker)worker.addEventListener('statechange',waitingNotice)});

     await navigator.serviceWorker.ready;
     count();
     if(navigator.onLine)sync();
     try{
       const d=await fetch('/api/catalog/summary',{cache:'no-store'}).then(r=>r.json());
       const items=(d&&d.items)||[];
       // Warm offline options once per catalogue revision, with bounded concurrency.
       // Previously every return launched all product requests at once.
       const warmKey='bechefaa-options-warmed-v1',revision=String(d.updatedAt||'');
       let warmed=null;try{warmed=JSON.parse(localStorage.getItem(warmKey)||'null')}catch(_){}
       if(warmed&&revision&&warmed.revision===revision&&Date.now()-warmed.at<10*60*1000)return;
       let cursor=0,complete=true;
       async function worker(){
         while(cursor<items.length){
           const p=items[cursor++];if(!p||!p.id)continue;
           try{const r=await fetch('/api/catalog/product/'+encodeURIComponent(p.id)+'/options');if(!r.ok)complete=false;}catch(_){complete=false;}
         }
       }
       await Promise.all([worker(),worker()]);
       if(complete&&revision){try{localStorage.setItem(warmKey,JSON.stringify({revision,at:Date.now()}))}catch(_){}}
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
            if 'function renderOrder(' in html:
                response.headers['X-BECHEFAA-POS-Shell'] = '1'
            if 'id="bechefaa-offline-ui"' not in html:
                html = html.replace("</body>", UI + "</body>")
                response.set_data(html)
                response.content_length = len(response.get_data())
        return response


def request_path_is_pos(response):
    from flask import request
    return request.path == "/pos" and response.status_code == 200 and response.mimetype == "text/html"



