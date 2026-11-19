const vm=require('node:vm'),assert=require('node:assert/strict'),fs=require('node:fs');
const source=fs.readFileSync(0,'utf8'),origin='https://caisse.test';
const handlers={},stores=new Map(),timers=new Map();let timerId=0,net,claims=0,writes=0,deletes=0;
const urlOf=x=>new URL(typeof x==='string'?x:x.url,origin).href;
const cache={open:async name=>{
 if(!stores.has(name))stores.set(name,new Map());const map=stores.get(name);
 return {put:async(req,res)=>map.set(urlOf(req),res.clone()),match:async(req,opts={})=>{let key=urlOf(req);if(opts.ignoreSearch){key=[...map.keys()].find(k=>k.split('?')[0]===key.split('?')[0])}return map.get(key)?.clone()},keys:async()=>[...map.keys()].map(k=>new Request(k)),delete:async req=>map.delete(urlOf(req))};
},keys:async()=>[...stores.keys()],delete:async name=>{deletes++;return stores.delete(name)}};
const ctx={Response,Request,URL,AbortController,location:{origin},caches:cache,
fetch:(...args)=>net(...args),setTimeout:fn=>{timers.set(++timerId,fn);return timerId},clearTimeout:id=>timers.delete(id),
indexedDB:{open(){writes++;throw Error('Startup must never touch queued orders')}},
self:{addEventListener:(name,fn)=>handlers[name]=fn,clients:{claim:async()=>{claims++},matchAll:async()=>[]}}};
vm.createContext(ctx);vm.runInContext(source,ctx);
const shell=()=>new Response('<div id="order"></div><script>function renderOrder(){}</script>',{headers:{'Content-Type':'text/html','X-BECHEFAA-POS-Shell':'1'}});
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 const old=await cache.open('bechefaa-pos-offline-v4');await old.put('/pos',shell());
 net=async()=>{throw Error('offline')};
 let r=await ctx.navigationResponse(new Request(origin+'/'));assert((await r.text()).includes('function renderOrder'));
 await ctx.revokeShells();r=await ctx.navigationResponse(new Request(origin+'/pos'));assert.equal(r.status,503);assert((await r.text()).includes('Réessayer'));assert.equal(writes,0);
 await old.put('/pos',new Response('<form action="/auth/pin">PIN</form>'));assert.equal(await ctx.cachedShell(),null);
 await old.put('/pos',shell());
 net=async()=>new Response('PIN required',{headers:{'X-BECHEFAA-Auth':'required'}});
 r=await ctx.navigationResponse(new Request(origin+'/'));assert.equal(await r.text(),'PIN required');assert.equal(await ctx.cachedShell(),null);
 net=async()=>shell();await ctx.navigationResponse(new Request(origin+'/pos'));assert(await ctx.cachedShell());
 // Browser storage quota must not turn a healthy network response into a failure.
 const realOpen=cache.open;cache.open=async name=>({...await realOpen(name),put:async()=>{throw Error('quota')}});
 r=await ctx.navigationResponse(new Request(origin+'/pos'));assert.equal(r.status,200);cache.open=realOpen;
 // Storage unavailable: successful network and login screens must still load.
 cache.open=async()=>{throw Error('storage unavailable')};net=async()=>shell();
 assert.equal((await ctx.navigationResponse(new Request(origin+'/pos'))).status,200);
 net=async()=>new Response('PIN required',{headers:{'X-BECHEFAA-Auth':'required'}});
 assert.equal(await (await ctx.navigationResponse(new Request(origin+'/'))).text(),'PIN required');
 net=async()=>{throw Error('offline')};assert.equal((await ctx.navigationResponse(new Request(origin+'/'))).status,503);
 cache.open=realOpen;
 net=(req,opts)=>new Promise((resolve,reject)=>opts.signal.addEventListener('abort',()=>reject(Error('timeout'))));
 const pending=ctx.navigationResponse(new Request(origin+'/pos'));await tick();for(const fn of [...timers.values()])fn();r=await pending;assert.equal(r.status,200);assert.equal(timers.size,0);
 // Failed installation preserves the existing rescue copy and never activates early.
 const before=deletes;net=async()=>{throw Error('offline')};let install;
 handlers.install({waitUntil:p=>install=p});await install;assert.equal(deletes,before);
 // No current shell: activation must retain every prior cache.
 const current=[...stores.keys()].find(k=>k.includes('v5-startup'));stores.get(current).clear();let activation;
 handlers.activate({waitUntil:p=>activation=p});await activation;assert.equal(deletes,before);assert.equal(claims,1);
 assert.equal(writes,0);
 // POST behavior is still network-first and is not subject to navigation aborts.
 let postRequest;
 net=async(req,opts)=>{postRequest={req,opts};return new Response('{"ok":true}',{headers:{'Content-Type':'application/json'}})};
 let posted;const req=new Request(origin+'/api/orders',{method:'POST',headers:{'Content-Type':'application/json'},body:'{"items":[{"name":"Burger"}]}'});
 handlers.fetch({request:req,respondWith:p=>posted=p});await posted;assert.equal(postRequest.opts,undefined);assert.equal(writes,0);
 console.log('PASS startup timeout, rescue cache, auth, update preservation, quota failure and untouched order writes');
})().catch(e=>{console.error(e);process.exitCode=1});
