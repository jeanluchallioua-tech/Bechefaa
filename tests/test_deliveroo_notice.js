const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const script=fs.readFileSync('clean_caisse/static/deliveroo-notice-preprod.js','utf8');
const now=1800000000000;
const order={id:'deliveroo-ticket49',sales_channel:'DELIVEROO',status:'À préparer',created_at:now-1000,platform_reference:'9560'};
async function harness(storage={},orders=[order]){
 const classes=new Set();let beeps=0,missing=false,fail=false;
 const banner={classList:{toggle:(s,on)=>on?classes.add(s):classes.delete(s)},style:{},textContent:''};
 const context={Date:{now:()=>now},Set,Object,Array,String,Number,JSON,console:{warn:()=>{}},
  sessionStorage:{getItem:k=>storage[k],setItem:(k,v)=>storage[k]=v},
  document:{getElementById:()=>missing?null:banner,addEventListener:()=>{}},
  window:{bechefaaNotifyDeliveroo:()=>beeps++,addEventListener:()=>{}},
  setInterval:()=>{},fetch:async()=>({ok:!fail,json:async()=>({ok:!fail,orders})})};
 vm.createContext(context);vm.runInContext(script,context);await new Promise(setImmediate);
 return {context,storage,banner,classes,beeps:()=>beeps,setOrders:v=>orders=v,setMissing:v=>missing=v,setFail:v=>fail=v,
         poll:()=>context.checkDeliveroo()};
}
(async()=>{
 let h=await harness();assert(h.classes.has('visible'));assert.equal(h.beeps(),1);
 await h.poll();assert.equal(h.beeps(),1); // no repeated beep
 h=await harness(h.storage);assert(h.classes.has('visible'));assert.equal(h.beeps(),0); // navigation restores
 h.banner.onclick();assert(!h.classes.has('visible'));
 h=await harness(h.storage);assert(!h.classes.has('visible'));assert.equal(h.beeps(),0); // acknowledged stays cleared
 h=await harness({},[{...order,created_at:now-180000}]);assert(h.classes.has('visible')); // 90-second cutoff removed
 h=await harness({},[{...order,created_at:now-7200000}]);assert(!h.classes.has('visible')); // no old ticket replay
 h=await harness({},[]);h.setOrders([order]);h.setMissing(true);await h.poll();assert.equal(h.beeps(),0);
 h.setMissing(false);await h.poll();assert(h.classes.has('visible'));assert.equal(h.beeps(),1); // retry render
 h.setFail(true);await h.poll();assert(h.classes.has('visible')); // network failure preserves alert
 h.setFail(false);h.setOrders([{...order,status:'Annulée'}]);await h.poll();assert(!h.classes.has('visible'));
 h=await harness({},[{...order,sales_channel:'SITE'}]);assert(!h.classes.has('visible'));assert.equal(h.beeps(),0);
 console.log('10 Deliveroo notice behavior checks passed (mocked DOM, no network or orders).');
})().catch(e=>{console.error(e);process.exitCode=1});
