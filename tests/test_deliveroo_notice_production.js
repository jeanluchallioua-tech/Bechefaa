const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
let script=fs.readFileSync('clean_caisse/static/deliveroo-notice-production.js','utf8');
// Expose just the poll operation inside the test VM, without changing shipped code.
script=script.replace(/\}\)\(\);\s*$/, 'globalThis.__poll=checkDeliveroo;})();');
const now=1800000000000;
const order={id:'deliveroo-test',sales_channel:'DELIVEROO',status:'À préparer',created_at:now-1000,updated_at:now-1000,platform_reference:'1234'};
async function harness(storage={},orders=[order]){
 const classes=new Set();let beeps=0,missing=false,fail=false;const urls=[];
 const banner={classList:{toggle:(s,on)=>on?classes.add(s):classes.delete(s)},style:{},textContent:''};
 const context={Date:{now:()=>now},Set,Object,Array,String,Number,JSON,console:{warn:()=>{}},
  sessionStorage:{getItem:k=>storage[k],setItem:(k,v)=>storage[k]=v},
  document:{getElementById:()=>missing?null:banner,addEventListener:()=>{}},
  window:{bechefaaNotifyDeliveroo:()=>beeps++,addEventListener:()=>{}},
  setInterval:()=>{},fetch:async url=>{urls.push(url);return {ok:!fail,json:async()=>({ok:!fail,orders})}}};
 vm.createContext(context);vm.runInContext(script,context);await new Promise(setImmediate);
 return {context,storage,banner,classes,urls,beeps:()=>beeps,setOrders:v=>orders=v,setMissing:v=>missing=v,setFail:v=>fail=v,poll:()=>context.__poll()};
}
(async()=>{
 let h=await harness();assert(h.classes.has('visible'));assert.equal(h.beeps(),1);
 assert(h.urls.every(url=>url==='/api/kitchen/orders')); // Never writes, charges or prints.
 await h.poll();assert.equal(h.beeps(),1);
 h=await harness(h.storage);assert(h.classes.has('visible'));assert.equal(h.beeps(),0);
 h.banner.onclick();assert(!h.classes.has('visible'));
 h=await harness(h.storage);assert(!h.classes.has('visible'));assert.equal(h.beeps(),0);
 h=await harness({},[{...order,created_at:now-7200000,updated_at:now-1000}]);assert(h.classes.has('visible')); // A scheduled order just released.
 h=await harness({},[{...order,created_at:now-7200000,updated_at:now-7200000}]);assert(!h.classes.has('visible'));
 h=await harness({},[]);h.setOrders([order]);h.setMissing(true);await h.poll();assert.equal(h.beeps(),0);
 h.setMissing(false);await h.poll();assert(h.classes.has('visible'));assert.equal(h.beeps(),1);
 h.setFail(true);await h.poll();assert(h.classes.has('visible'));
 h.setFail(false);h.setOrders([{...order,status:'Annulée'}]);await h.poll();assert(!h.classes.has('visible'));
 h=await harness({},[{...order,sales_channel:'SITE'}]);assert(!h.classes.has('visible'));assert.equal(h.beeps(),0);
 console.log('12 production Deliveroo notice contracts passed (mocked DOM, no network, payment or print).');
})().catch(e=>{console.error(e);process.exitCode=1});
