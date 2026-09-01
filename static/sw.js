const CACHE_NAME="bechefaa-central-pos-0541";
const CORE=["/","/caisse","/salle","/cuisine","/style.css?v=0538","/app.js?v=0541","/cloud.js?v=0538notifformat","/manifest.webmanifest"];

const PROFILE_NEEDLE="function profile(p){\n let ek=exactKey(p);";
const PROFILE_REPLACEMENT=`/* === V0.5.41 CENTRAL CATALOGUE -> POS === */
const CENTRAL_PROFILE_BY_ID=Object.create(null), CENTRAL_PROFILE_BY_NAME=Object.create(null);
async function loadCentralCatalogOptions(){
 try{
  const r=await fetch("/api/catalog-admin?t="+Date.now(),{cache:"no-store"});
  if(!r.ok)throw new Error("HTTP "+r.status);
  const j=await r.json(), products=j?.data?.products;
  if(!Array.isArray(products))return;
  products.forEach((p)=>{
   const keys=[];
   const enabled=p?.active!==false && (p?.channels?.caisse!==false);
   if(enabled){
    (Array.isArray(p.options)?p.options:[]).forEach((g,i)=>{
     const safeId=String(p.id??p.name??"product").replace(/[^a-zA-Z0-9_-]/g,"_");
     const key=\`central_\${safeId}_\${i}\`;
     const choices=(Array.isArray(g?.choices)?g.choices:[]).map(c=>{
      if(Array.isArray(c))return [String(c[0]??"Option"),Number(c[1]||0)];
      return [String(c?.name??c?.label??"Option"),Number(c?.price??c?.extra??0)];
     });
     GROUPS[key]={title:String(g?.title||g?.key||"Options"),required:!!g?.required,max:Math.max(0,Number(g?.max??1)),choices};
     keys.push(key);
    });
   }
   CENTRAL_PROFILE_BY_ID[String(p.id??"")]=keys;
   CENTRAL_PROFILE_BY_NAME[norm(p.name)]=keys;
  });
  if(typeof rp==="function")rp();
 }catch(e){console.error("BÉCHÉFAA Catalogue central -> POS:",e)}
}
setTimeout(loadCentralCatalogOptions,0);
function profile(p){
 const centralId=String(p?.id??"");
 if(Object.prototype.hasOwnProperty.call(CENTRAL_PROFILE_BY_ID,centralId))return CENTRAL_PROFILE_BY_ID[centralId];
 const centralName=norm(p?.name);
 if(Object.prototype.hasOwnProperty.call(CENTRAL_PROFILE_BY_NAME,centralName))return CENTRAL_PROFILE_BY_NAME[centralName];
 let ek=exactKey(p);`;

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

  if(u.pathname.endsWith("/app.js") || u.pathname==="/app.js"){
    e.respondWith((async()=>{
      try{
        const r=await fetch(e.request,{cache:"no-store"});
        let txt=await r.text();
        if(!txt.includes("V0.5.41 CENTRAL CATALOGUE -> POS") && txt.includes(PROFILE_NEEDLE)){
          txt=txt.replace(PROFILE_NEEDLE,PROFILE_REPLACEMENT);
        }
        const h=new Headers(r.headers);
        h.set("content-type","application/javascript; charset=utf-8");
        h.set("cache-control","no-store, max-age=0");
        return new Response(txt,{status:r.status,statusText:r.statusText,headers:h});
      }catch(err){
        return caches.match(e.request) || Response.error();
      }
    })());
    return;
  }

  if(u.pathname.endsWith(".js")||u.pathname.endsWith(".css")||u.pathname.endsWith(".html")||["/","/caisse","/salle","/cuisine"].includes(u.pathname)){
    e.respondWith(fetch(e.request).then(r=>{const x=r.clone();caches.open(CACHE_NAME).then(c=>c.put(e.request,x));return r}).catch(()=>caches.match(e.request)));
    return;
  }
  e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request)));
});
