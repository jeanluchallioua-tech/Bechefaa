'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('clean_caisse/uber_sandbox_test_panel.py','utf8');
const code=source.match(/<script id="uber-sandbox-pos-script">([\s\S]*?)<\/script>/)[1];
class Element{
 constructor(tag='div'){this.tag=tag;this.children=[];this.handlers={};this.dataset={};this.hidden=false;this.textContent='';}
 appendChild(el){this.children.push(el);return el;}
 replaceChildren(){this.children=[];}
 addEventListener(name,fn){this.handlers[name]=fn;}
 set innerHTML(value){throw Error('HTML insertion is forbidden in sandbox panel');}
}
function all(el){return [el,...el.children.flatMap(all)];}
async function run(mode){
 const root=new Element('details');root.dataset.mode=mode;
 const selectors={};for(const name of ['count','status','orders','refresh','audio','arrival'])selectors['[data-uber-test-'+name+']']=new Element();
 root.querySelector=key=>selectors[key];let poll,beeps=0,rows=[],stage='À préparer';const calls=[];
 class Audio{
  constructor(){this.state='suspended';this.currentTime=0;this.destination={};}
  async resume(){this.state='running';}
  createOscillator(){beeps++;return{frequency:{},connect(){},start(){},stop(){}};}
  createGain(){return{gain:{setValueAtTime(){},linearRampToValueAtTime(){}},connect(){}};}
 }
 const fixture={id:'01460685-2d3d-4d79-af00-4eaba3384a34',display_id:'84A34',current_state:'ACCEPTED',
  items:[{quantity:1,title:'Classic <script>bad()</script>',options:[{title:'Sans tomate',quantity:1,options:[]}]}],charges:{total:{amount:2100,currency_code:'EUR'}}};
 const document={hidden:false,getElementById:id=>id==='uber-sandbox-pos'?root:null,createElement:tag=>new Element(tag),addEventListener(){}};
 const fetch=async(url,options)=>{
  calls.push({url,options});
  if(options.method==='POST'){
   assert.equal(options.headers['X-Uber-Test-CSRF'],'csrf-test');
   if(url.endsWith('/stage'))stage=JSON.parse(options.body).stage;
   return{ok:true,json:async()=>({ok:true,message:'Action test effectuée'})};
  }
  return{ok:true,json:async()=>({ok:true,csrf:'csrf-test',orders:rows.map(order=>({order,stage,imported_at:'2026-11-23T17:00:00Z',sent_at:'2026-11-23T17:00:00Z'}))})};
 };
 const untouchedCart={items:['restaurant burger'],table:'7'};
 const context={document,fetch,window:{AudioContext:Audio,addEventListener(){}},location:{search:''},URLSearchParams,
  setInterval:fn=>{poll=fn;return 1;},clearInterval(){},console,untouchedCart};
 vm.runInNewContext(code,context);
 const flush=()=>new Promise(resolve=>setImmediate(resolve));await flush();
 assert.equal(selectors['[data-uber-test-count]'].textContent,'0');
 await selectors['[data-uber-test-audio]'].handlers.click();assert.equal(beeps,3);
 rows=[fixture];await poll();await flush();
 assert.equal(beeps,6,'new polled order must sound after audio activation');
 assert.equal(selectors['[data-uber-test-arrival]'].hidden,false);
 assert.match(selectors['[data-uber-test-arrival]'].textContent,/84A34/);
 assert.equal(root.open,true);
 assert.equal(selectors['[data-uber-test-count]'].textContent,'1');
 const labels=()=>all(selectors['[data-uber-test-orders]']);
 assert.ok(labels().some(el=>el.textContent.includes('Classic <script>bad()</script>')),'product labels are inserted as literal text');
 await poll();await flush();assert.equal(beeps,6,'duplicate poll must not sound again');
 if(mode==='kitchen'){
  await labels().find(el=>el.textContent==='Commencer la préparation TEST').handlers.click();await flush();
  assert.equal(stage,'En préparation');
  await labels().find(el=>el.textContent==='Terminer la préparation TEST').handlers.click();await flush();
  assert.equal(stage,'Terminée');assert.equal(beeps,6,'stage changes must not repeat arrival sound');
 }else{
  await labels().find(el=>el.textContent==='Envoyer dans la cuisine de test').handlers.click();await flush();
  assert.ok(calls.some(c=>c.url==='/api/uber/sandbox/kitchen/dispatch'&&c.options.method==='POST'));
 }
 assert.deepEqual(untouchedCart,{items:['restaurant burger'],table:'7'});
 assert.ok(calls.every(c=>c.url.startsWith('/api/uber/sandbox/')),'only isolated sandbox endpoints may be called');
 assert.ok(calls.every(c=>!c.url.includes('send-kitchen')&&!c.url.includes('print')),'never trigger POS print interception');
}
(async()=>{await run('pos');await run('kitchen');console.log('Sandbox POS and kitchen alerts: arrival, deduplication, transitions and cart isolation passed.');})().catch(error=>{console.error(error);process.exitCode=1;});
