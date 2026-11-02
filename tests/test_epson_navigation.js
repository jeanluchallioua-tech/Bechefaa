const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('clean_caisse/epson_epos_network_phase6.py','utf8');
const start=source.indexOf("const box=document.getElementById('epson-status');");
const script='(function(){\n'+source.slice(start,source.indexOf("</script>'''",start));
function harness(path='/pos'){
 const calls=[],navigations=[],timers=[],listeners={},box={className:'',textContent:''};
 const location={origin:'https://caisse.bechefaa.fr',pathname:path,search:'',replace:u=>navigations.push(u)};
 Object.defineProperty(location,'href',{get:()=>location.origin+path,set:u=>navigations.push(u)});
 const response=(data,ok=true)=>({ok,clone(){return response(data,ok)},json:async()=>data});
 const fetch=async(url,init)=>{
   calls.push([url,init]);
   if(url==='/api/epson/config-phase6')return response({ok:true,host:'192.168.10.112'});
   if(String(url).includes('/send-kitchen'))return response({ok:true,id:'order-265'});
   throw Error('Unexpected request: '+url);
 };
 const document={hidden:false,getElementById:()=>box,addEventListener:(k,v)=>listeners[k]=v};
 const window={location,fetch,addEventListener(){},dispatchEvent(){},matchMedia:()=>({matches:false}),navigator:{}};
 const context={window,document,navigator:{userAgent:'Mozilla/5.0 Android SamsungBrowser'},
   sessionStorage:{setItem(){},getItem(){return null}},URLSearchParams,Event:class{},
   setTimeout:(fn,ms)=>{timers.push(ms);return 1},clearTimeout(){},encodeURIComponent,console};
 vm.runInNewContext(script,context);
 return {window,calls,navigations,timers};
}
(async()=>{
 const h=harness();await Promise.resolve();await Promise.resolve();
 await h.window.bechefaaPrintClient('saved id');
 assert.equal(h.navigations.at(-1),'/epson/print-client/saved%20id?return_to=%2Fpos');
 await h.window.bechefaaPrintKitchen('saved id');
 assert.equal(h.navigations.at(-1),'/epson/print-kitchen/saved%20id?return_to=%2Fpos');
 await h.window.bechefaaPrintOrderPack('saved id');
 assert.equal(h.navigations.at(-1),'/epson/print-order-pack/saved%20id?return_to=%2Fpos');
 assert.equal(h.calls.length,1,'Android printing must not wait for an XML fetch');
 assert.equal(h.timers.length,0,'Do not put app launch behind a JavaScript timer');
 const history=harness('/historique-modification');
 await history.window.bechefaaPrintClient('order-265');
 assert.equal(history.navigations[0],'/epson/print-client/order-265?return_to=%2Fhistorique-modification');
 await history.window.bechefaaPrintExpenseNote('order-265',2);
 assert.equal(history.navigations.at(-1),'/epson/print-expense-note/order-265?return_to=%2Fhistorique-modification&persons=2');
 const kitchen=harness();
 await kitchen.window.fetch('/api/orders/order-265/send-kitchen',{method:'POST'});
 assert.equal(kitchen.navigations.length,1);
 assert.equal(kitchen.navigations[0],'/epson/print-order-pack/order-265?return_to=%2Fpos');
 assert.equal(kitchen.calls.filter(([url])=>url.includes('/send-kitchen')).length,1);
 assert.equal(kitchen.calls.filter(([url])=>url==='/api/orders').length,0);
 assert.equal(kitchen.timers.length,0);
 console.log('Epson navigation: POS pair, history, individual tickets and expense note passed');
})().catch(e=>{console.error(e);process.exitCode=1});
