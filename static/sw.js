
const CACHE_NAME="bechefaa-clean-0535-auto";
const CORE=["/","/caisse","/salle","/cuisine","/style.css?v=0538notifformat","/app.js?v=0538notifformat","/cloud.js?v=0538notifformat","/manifest.webmanifest"];

self.addEventListener("install",e=>{
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE_NAME).then(c=>c.addAll(CORE).catch(()=>{})));
});
self.addEventListener("activate",e=>{
  e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE_NAME).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});
self.addEventListener("fetch",e=>{
  if(e.request.method!=="GET")return;
  const u=new URL(e.request.url);
  if(u.pathname.startsWith("/api/")){e.respondWith(fetch(e.request));return}
  if(u.pathname.endsWith(".js")||u.pathname.endsWith(".css")||u.pathname.endsWith(".html")||["/","/caisse","/salle","/cuisine"].includes(u.pathname)){
    e.respondWith(fetch(e.request).then(r=>{const x=r.clone();caches.open(CACHE_NAME).then(c=>c.put(e.request,x));return r}).catch(()=>caches.match(e.request)));
    return;
  }
  e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request)));
});
