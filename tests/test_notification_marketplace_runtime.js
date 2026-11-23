'use strict';
const assert=require('node:assert/strict'),fs=require('fs'),vm=require('vm');
const policy=fs.readFileSync('clean_caisse/notification_sound_policy_phase6.py','utf8').match(/SOUND_POLICY_JS = r'''([\s\S]*?)'''/)[1];
const raw=fs.readFileSync('clean_caisse/order_notifications_phase33.py','utf8').match(/addon = r'''([\s\S]*?)'''/)[1].match(/<script>([\s\S]*?)<\/script>/)[1];
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function approx(actual,expected){assert.ok(Math.abs(actual-expected)<1e-8,`${actual} != ${expected}`);}
class Element{
 constructor(tag){this.tag=tag;this.children=[];this.style={};this.textContent='';this.id='';this.attributes={};this.handlers={};this.classList={add(){},remove(){}};}
 appendChild(el){el.parent=this;this.children.push(el);return el;}
 setAttribute(k,v){this.attributes[k]=v;}
 addEventListener(k,v){this.handlers[k]=v;}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(child=>child!==this);}
}
function find(node,id){if(node.id===id)return node;for(const child of node.children){const result=find(child,id);if(result)return result;}return null;}
async function runtime(page,prefs){
 const body=new Element('body'),cart=new Element('div');cart.id='cart';cart.textContent='Burger en cours';body.appendChild(cart);
 const calls=[],peaks=[],prints=[],timers=[];let oscillators=0;
 class Audio{
  constructor(){this.state='running';this.currentTime=0;this.destination={};}
  async resume(){this.state='running';}
  createOscillator(){oscillators++;return {type:'',frequency:{setValueAtTime(){}},connect(){},start(){},stop(){}};}
  createGain(){return{gain:{setValueAtTime(){},exponentialRampToValueAtTime(value){peaks.push(value);}},connect(){}};}
 }
 const storage=()=>{const data=new Map();return{getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,String(v)),removeItem:k=>data.delete(k)}};
 const context={console,Date,AbortController,Promise,localStorage:storage(),sessionStorage:storage(),navigator:{userAgent:'Android',userActivation:{hasBeenActive:true}},
 document:{body,hidden:false,getElementById:id=>find(body,id),createElement:tag=>new Element(tag),addEventListener(){}},
 window:{AudioContext:Audio,addEventListener(){},bechefaaPrintOrderPack:id=>{prints.push(id);return Promise.resolve();}},
 setTimeout:(fn,delay)=>{const timer={fn,delay};timers.push(timer);return timer;},clearTimeout(){},setInterval(){},
 fetch:async(url,options)=>{calls.push({url,options});return{ok:true,json:async()=>url==='/api/notification-settings'?{ok:true,...prefs}:{ok:true,orders:[]}};}};
 const code=raw.replace('__SOUND_POLICY__',policy).replace('__PAGE__',page).replace('__PRINT_ENABLED__',page==='pos'?'true':'false').replace('__TEST_MODE__','false')
  .replace('\n})();','\nwindow.testAccess={inspect,loadSoundSettings,unlock};\n})();');
 vm.runInNewContext(code,context);await flush();await context.window.testAccess.unlock(false);
 return{context,body,cart,calls,peaks,prints,timers,get oscillators(){return oscillators;},access:context.window.testAccess};
}
function order(id,channel){return{id,sales_channel:channel,status:'À préparer',customer_name:'Test',ticket_type:'Livraison',created_at:Date.now(),updated_at:Date.now()};}
(async()=>{
 const pctx={};vm.runInNewContext(policy,pctx);
 const prefs={pos_enabled:true,pos_volume:80,kitchen_enabled:true,kitchen_volume:60,deliveroo_enabled:true,deliveroo_volume:25,ubereats_enabled:true,ubereats_volume:50};
 approx(pctx.notificationSoundPolicy(prefs,'pos','DELIVEROO').volume,.2);
 approx(pctx.notificationSoundPolicy(prefs,'kitchen','Livraison Uber Eats').volume,.3);
 approx(pctx.notificationSoundPolicy(prefs,'pos','SITE').volume,.8);
 approx(pctx.notificationSoundPolicy({pos_volume:75},'pos','UBER_EATS').volume,.75);
 assert.equal(pctx.notificationSoundPolicy({...prefs,deliveroo_enabled:false},'kitchen','Deliveroo').enabled,false);
 assert.equal(pctx.notificationSoundPolicy({...prefs,kitchen_enabled:false},'kitchen','Uber Eats').enabled,false);
 approx(pctx.notificationSoundPolicy({...prefs,ubereats_volume:0},'pos','UberEats').volume,0);
 const pos=await runtime('pos',prefs);
 pos.context.window.bechefaaNotifyDeliveroo();assert.equal(pos.oscillators,3);approx(Math.max(...pos.peaks),.2);
 pos.peaks.length=0;pos.context.window.bechefaaNotifyUberEats();assert.equal(pos.oscillators,6);approx(Math.max(...pos.peaks),.4);
 prefs.deliveroo_enabled=false;await pos.access.loadSoundSettings();pos.context.window.bechefaaNotifyDeliveroo();assert.equal(pos.oscillators,6,'disabled Deliveroo must remain silent');
 pos.peaks.length=0;pos.access.inspect([order('uber-1','UBER_EATS')]);assert.equal(pos.oscillators,9);approx(Math.max(...pos.peaks),.4);
 assert.match(find(pos.body,'phase6-site-order-notice').textContent,/UBER EATS/);
 assert.equal(pos.timers.filter(timer=>timer.delay===1200).length,0,'Uber settings must not enable Uber automatic printing');
 pos.peaks.length=0;pos.access.inspect([order('uber-1','UBER_EATS'),order('site-1','SITE')]);approx(Math.max(...pos.peaks),.8);
 for(const timer of pos.timers.filter(timer=>timer.delay===1200))timer.fn();
 assert.deepEqual(pos.prints,['site-1'],'existing SITE print path must still run');
 assert.equal(pos.cart.textContent,'Burger en cours');
 const kitchen=await runtime('kitchen',{...prefs,deliveroo_enabled:true});
 kitchen.access.inspect([order('roo-1','DELIVEROO')]);assert.equal(kitchen.oscillators,3);approx(Math.max(...kitchen.peaks),.15);
 kitchen.peaks.length=0;kitchen.access.inspect([order('roo-1','DELIVEROO'),order('uber-2','UBER EATS')]);assert.equal(kitchen.oscillators,6);approx(Math.max(...kitchen.peaks),.3);
 kitchen.access.inspect([order('roo-1','DELIVEROO'),order('uber-2','UBER EATS')]);assert.equal(kitchen.oscillators,6,'same order must not sound twice');
 const muted=await runtime('kitchen',{...prefs,ubereats_enabled:false});muted.access.inspect([order('muted-uber','UBEREATS')]);assert.equal(muted.oscillators,0);
 assert.deepEqual(kitchen.prints,[]);
 console.log('Marketplace notification policies, live hooks, channel muting, kitchen alerts, cart preservation and SITE-only printing passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
