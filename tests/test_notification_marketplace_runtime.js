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
async function runtime(page,prefs,blocked=false){
 const body=new Element('body'),cart=new Element('div');cart.id='cart';cart.textContent='Burger en cours';body.appendChild(cart);
 const calls=[],peaks=[],prints=[],timers=[];let oscillators=0;const toneStarts=[];
 class Audio{
  constructor(){this.state=blocked?'suspended':'running';this.currentTime=0;this.destination={};}
  async resume(){this.state='running';}
  createOscillator(){oscillators++;return {type:'',frequency:{setValueAtTime(){}},connect(){},start(at){toneStarts.push(at);},stop(){}};}
  createGain(){return{gain:{setValueAtTime(){},exponentialRampToValueAtTime(value){peaks.push(value);}},connect(){}};}
 }
 const storage=()=>{const data=new Map();return{getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,String(v)),removeItem:k=>data.delete(k)}};
 const context={console,Date,URLSearchParams,location:{search:''},AbortController,Promise,localStorage:storage(),sessionStorage:storage(),navigator:{userAgent:'Android',userActivation:{hasBeenActive:true}},
 document:{body,hidden:false,querySelectorAll:()=>[],dispatchEvent(){},getElementById:id=>find(body,id),createElement:tag=>new Element(tag),addEventListener(){}},
 window:{AudioContext:Audio,addEventListener(){},bechefaaPrintOrderPack:id=>{prints.push(id);return Promise.resolve();},bechefaaPrintUberTestPack:id=>{prints.push('TEST:'+id);return Promise.resolve();}},
 setTimeout:(fn,delay)=>{const timer={fn,delay};timers.push(timer);return timer;},clearTimeout(){},setInterval(){},
 fetch:async(url,options)=>{calls.push({url,options});return{ok:true,json:async()=>url==='/api/notification-settings'?{ok:true,...prefs}:{ok:true,orders:[]}};}};
 const code=raw.replace('__SOUND_POLICY__',policy).replace('__PAGE__',page).replace('__PRINT_ENABLED__',page==='pos'?'true':'false').replace('__TEST_MODE__','false')
  .replace('\n})();','\nwindow.testAccess={inspect,loadSoundSettings,unlock,resumeAlerts};\n})();');
 vm.runInNewContext(code,context);await flush();if(!blocked)await context.window.testAccess.unlock(false);
 return{context,body,cart,calls,peaks,prints,timers,get oscillators(){return oscillators;},toneStarts,access:context.window.testAccess};
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
 assert.equal(find(pos.body,'phase6-site-order-notice').textContent,'','Uber must not display an arrival banner');
 for(const timer of pos.timers.filter(timer=>timer.delay===1200))timer.fn();await flush();
 assert.deepEqual(pos.prints,['uber-1'],'an incoming Uber order must automatically print its ticket pack');
 pos.access.resumeAlerts({type:'bechefaa:print-return'});await flush();
 pos.peaks.length=0;pos.access.inspect([order('uber-1','UBER_EATS'),order('site-1','SITE')]);approx(Math.max(...pos.peaks),.8);
 for(const timer of pos.timers.filter(timer=>timer.delay===1200))timer.fn();await flush();
 assert.deepEqual(pos.prints,['uber-1','site-1'],'SITE printing remains enabled without duplicate Uber printing');
 assert.equal(pos.cart.textContent,'Burger en cours');
 const kitchen=await runtime('kitchen',{...prefs,deliveroo_enabled:true});
 kitchen.access.inspect([order('roo-1','DELIVEROO')]);assert.equal(kitchen.oscillators,3);approx(Math.max(...kitchen.peaks),.15);
 kitchen.peaks.length=0;kitchen.access.inspect([order('roo-1','DELIVEROO'),order('uber-2','UBER EATS')]);assert.equal(kitchen.oscillators,6);approx(Math.max(...kitchen.peaks),.3);
 kitchen.access.inspect([order('roo-1','DELIVEROO'),order('uber-2','UBER EATS')]);assert.equal(kitchen.oscillators,6,'same order must not sound twice');
 const muted=await runtime('kitchen',{...prefs,ubereats_enabled:false});muted.access.inspect([order('muted-uber','UBEREATS')]);assert.equal(muted.oscillators,0);
 assert.deepEqual(kitchen.prints,[]);
 const sharedKitchen=await runtime('kitchen',{...prefs,deliveroo_enabled:true});
 sharedKitchen.context.window.bechefaaUberTestSound.notify();assert.equal(sharedKitchen.oscillators,3,'TEST kitchen uses normal unlocked audio without a separate TEST click');approx(Math.max(...sharedKitchen.peaks),.3);
 assert.equal(await sharedKitchen.context.window.bechefaaUberTestSound.activate(),true);assert.equal(sharedKitchen.oscillators,6);
 muted.context.window.bechefaaUberTestSound.notify();assert.equal(muted.oscillators,0,'TEST arrivals must respect Uber mute');assert.equal(await muted.context.window.bechefaaUberTestSound.activate(),false);
 const locked=await runtime('kitchen',prefs,true);locked.context.window.bechefaaUberTestSound.notify();
 assert.equal(locked.oscillators,0);assert.ok(find(locked.body,'bechefaa-audio-wait'),'blocked kitchen arrival must offer activation instead of silently disappearing');
 assert.equal(await locked.context.window.bechefaaUberTestSound.activate(),true);assert.equal(locked.oscillators,3,'pending kitchen alert plays once on activation');assert.equal(find(locked.body,'bechefaa-audio-wait'),null);
 const mixed=await runtime('pos',{...prefs,deliveroo_enabled:true});
 Object.assign(mixed.context,{ORDER:[{name:'Burger comptoir',qty:2,unit_price:17.5,options:[{name:'Sans tomate'}]}],TICKET_TYPE:'Salle',MANUAL_DISCOUNT:10,renderOrder(){}});
 const draftScript=fs.readFileSync('clean_caisse/static/pos-active-cart.js','utf8');
 vm.runInNewContext(draftScript,mixed.context);
 for(let pass=0;pass<2;pass++)for(const timer of mixed.timers.filter(timer=>timer.delay===0))timer.fn();
 let snapshots=0;const prepare=mixed.context.window.bechefaaPrepareIncomingPrint;
 assert.equal(typeof prepare,'function');mixed.context.window.bechefaaPrepareIncomingPrint=async()=>{snapshots++;await prepare();};
 const batch=[order('mixed-site','SITE'),order('mixed-roo','DELIVEROO'),order('mixed-uber','UBEREATS')];
 for(let n=0;n<3;n++){
   mixed.access.resumeAlerts({type:'bechefaa:print-return'});await flush();mixed.access.inspect(batch);
   for(const timer of mixed.timers.filter(timer=>timer.delay===1200))timer.fn();await flush();
 }
 assert.deepEqual(mixed.prints,['mixed-site','mixed-roo','mixed-uber'],'all simultaneous arrivals must print once, regardless of channel');
 assert.equal(snapshots,3,'save active draft before every Epson launch');
 assert.equal(mixed.context.ORDER.length,1);assert.equal(mixed.context.ORDER[0].qty,2);
 const owner=mixed.context.sessionStorage.getItem('bechefaa_active_cart_owner_v2');
 const persisted=JSON.parse(mixed.context.localStorage.getItem('bechefaa_active_cart_v2_'+owner));
 assert.equal(persisted.items[0].name,'Burger comptoir');assert.equal(persisted.items[0].options[0].name,'Sans tomate');
 assert.match(find(mixed.body,'phase6-site-order-notice').textContent,/SITE/);
 assert.doesNotMatch(find(mixed.body,'phase6-site-order-notice').textContent,/UBER|DELIVEROO/);
 const testId='4b54b4f9-7bc7-4f78-b25c-1d9ea41006b6';
 assert.equal(mixed.context.window.bechefaaQueueUberTestPrint(testId),true);
 for(const timer of mixed.timers.filter(timer=>timer.delay===1200))timer.fn();await flush();
 assert.equal(mixed.prints.length,3,'TEST must wait for the running normal Epson pack');
 mixed.access.resumeAlerts({type:'visibilitychange'});await flush();
 for(const timer of mixed.timers.filter(timer=>timer.delay===1200))timer.fn();await flush();
 assert.equal(mixed.prints.length,3,'merely focusing another tab must not release the Epson queue');
 mixed.access.resumeAlerts({type:'bechefaa:print-return'});await flush();
 for(const timer of mixed.timers.filter(timer=>timer.delay===1200))timer.fn();await flush();
 assert.equal(mixed.prints[3],'TEST:'+testId);assert.equal(snapshots,4);assert.equal(mixed.context.ORDER.length,1);
 mixed.context.window.bechefaaQueueUberTestPrint(testId);
 mixed.access.resumeAlerts({type:'bechefaa:print-return'});await flush();
 for(const timer of mixed.timers.filter(timer=>timer.delay===1200))timer.fn();await flush();assert.equal(mixed.prints.length,4,'same TEST snapshot must not print twice');
 mixed.context.navigator.userAgent='Windows';assert.equal(mixed.context.window.bechefaaQueueUberTestPrint(testId,true),false,'PC must never launch physical TEST printing');
 const failedPrint=await runtime('pos',prefs);let attempts=0;
 failedPrint.context.window.bechefaaPrintUberTestPack=()=>{attempts++;throw Error('TEST XML missing');};
 failedPrint.context.window.bechefaaQueueUberTestPrint(testId);
 for(const timer of failedPrint.timers.filter(timer=>timer.delay===1200))timer.fn();await flush();assert.equal(attempts,1);
 assert.equal(failedPrint.context.window.bechefaaQueueUberTestPrint(testId),false,'failed TEST print must pause instead of retrying on every poll');
 failedPrint.access.resumeAlerts({type:'bechefaa:print-return'});await flush();for(const timer of failedPrint.timers.filter(timer=>timer.delay===1200))timer.fn();await flush();assert.equal(attempts,1);
 assert.equal(failedPrint.context.window.bechefaaQueueUberTestPrint(testId,true),true);for(const timer of failedPrint.timers.filter(timer=>timer.delay===1200))timer.fn();await flush();assert.equal(attempts,2,'explicit retry remains available');
 const times=pos.toneStarts;for(let n=3;n<times.length;n+=3)assert.ok(times[n]>=times[n-3]+.9-1e-8,'successive alert packs must not overlap');
 console.log('Marketplace notification policies, live hooks, channel muting, kitchen alerts, cart preservation and all-channel automatic printing passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});

