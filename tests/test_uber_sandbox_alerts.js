'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('clean_caisse/uber_sandbox_test_panel.py','utf8');
const code=source.match(/<script id="uber-sandbox-pos-script">([\s\S]*?)<\/script>/)[1];
class Element{
 constructor(tag='div'){this.tag=tag;this.children=[];this.handlers={};this.dataset={};this.hidden=false;this.textContent='';}
 appendChild(el){el.parentNode=this;this.children.push(el);return el;}
 replaceChildren(...items){this.children=items;}
 addEventListener(name,fn){this.handlers[name]=fn;}
 set innerHTML(value){throw Error('HTML insertion is forbidden in sandbox panel');}
}
function all(el){return [el,...el.children.flatMap(all)];}
async function run(mode,board=false,initialRecent=false,initialStage='À préparer',shared=false){
 const root=new Element('details');root.dataset.mode=mode;root.dataset.board=board?'true':'false';
 const columns={todo:new Element(),doing:new Element(),done:new Element()};
 const selectors={};for(const name of ['count','status','action-status','orders','refresh','audio','arrival','close'])selectors['[data-uber-test-'+name+']']=new Element();
 selectors['[data-uber-test-arrival]'].hidden=true;
 root.querySelector=key=>selectors[key];let poll,beeps=0,rows=[],stage=initialStage,dispatched=false;const calls=[];
 class Audio{
  constructor(){this.state='suspended';this.currentTime=0;this.destination={};}
  async resume(){this.state='running';}
  createOscillator(){beeps++;return{frequency:{},connect(){},start(){},stop(){}};}
  createGain(){return{gain:{setValueAtTime(){},linearRampToValueAtTime(){}},connect(){}};}
 }
 const fixture={id:'01460685-2d3d-4d79-af00-4eaba3384a34',display_id:'84A34',current_state:'ACCEPTED',
  items:[{quantity:1,title:'Classic <script>bad()</script>',options:[{title:'Sans tomate',quantity:1,options:[]}]}],charges:{total:{amount:2100,currency_code:'EUR'}}};
 if(initialRecent)rows=[fixture];
 const body=new Element('body');
 const document={body,hidden:false,getElementById:id=>id==='uber-sandbox-pos'?root:columns[id.replace('uber-test-','')]||null,createElement:tag=>new Element(tag),addEventListener(){}};
 const fetch=async(url,options)=>{
  calls.push({url,options});
  if(options.method==='POST'){
   assert.equal(options.headers['X-Uber-Test-CSRF'],'csrf-test');
   if(url.endsWith('/stage'))stage=JSON.parse(options.body).stage;
   if(url.endsWith('/dispatch'))dispatched=true;
   return{ok:true,json:async()=>({ok:true,message:'Action test effectuée'})};
  }
  return{ok:true,json:async()=>({ok:true,csrf:'csrf-test',orders:rows.map(order=>({order,stage,kitchen_stage:dispatched?stage:null,imported_at:new Date().toISOString(),sent_at:new Date().toISOString()}))})};
 };
 const untouchedCart={items:['restaurant burger'],table:'7'};
 const savedNotices=new Map();
 const sessionStorage={getItem:key=>savedNotices.get(key)||null,setItem:(key,value)=>savedNotices.set(key,value)};
 const context={document,fetch,sessionStorage,window:{AudioContext:Audio,addEventListener(){}},location:{search:''},URLSearchParams,
  setInterval:fn=>{poll=fn;return 1;},clearInterval(){},console,untouchedCart};
 if(shared)context.window.bechefaaUberTestSound={notify:()=>{beeps+=3;},activate:async()=>{beeps+=3;return true;}};
 vm.runInNewContext(code,context);
 const flush=()=>new Promise(resolve=>setImmediate(resolve));await flush();
 assert.equal(selectors['[data-uber-test-count]'].textContent,initialRecent?'1':'0');
 assert.equal(selectors['[data-uber-test-arrival]'].hidden,true,'Uber arrival must not show a visual banner');
 if(initialRecent&&initialStage==='Terminée'){assert.equal(selectors['[data-uber-test-arrival]'].hidden,true,'finished order must not create a new arrival banner');assert.equal(beeps,0);return;}
 if(initialRecent){assert.equal(selectors['[data-uber-test-arrival]'].hidden,true);assert.equal(beeps,shared?3:0,'shared audio handles arrivals without a separate TEST activation');}
 const initialBeeps=beeps;await selectors['[data-uber-test-audio]'].handlers.click();assert.equal(beeps,initialBeeps+3);
 root.open=true;selectors['[data-uber-test-close]'].handlers.click();assert.equal(root.open,false);
 const expectedRef=initialRecent?'85B35':'84A34';
 rows=[initialRecent?{...fixture,id:'01460685-2d3d-4d79-af00-4eaba3385b35',display_id:'85B35'}:fixture];await poll();await flush();
 assert.equal(beeps,initialBeeps+6,'new polled order must sound after audio activation');
 assert.equal(selectors['[data-uber-test-arrival]'].hidden,true);
 assert.equal(selectors['[data-uber-test-arrival]'].textContent,'');
 if(mode==='pos'||board)assert.notEqual(root.open,true,'arrival must not open a panel over cashier work');
 assert.equal(selectors['[data-uber-test-count]'].textContent,'1');
 root.open=true;selectors['[data-uber-test-close]'].handlers.click();assert.equal(root.open,false,'explicit fold button must close the TEST panel');
 const labels=()=>board?Object.values(columns).flatMap(all):all(selectors['[data-uber-test-orders]']);
 if(board)assert.equal(columns.todo.children.length,1);
 assert.ok(labels().some(el=>el.textContent.includes('Classic <script>bad()</script>')),'product labels are inserted as literal text');
 selectors['[data-uber-test-arrival]'].handlers.click();assert.equal(selectors['[data-uber-test-arrival]'].hidden,true);
 await poll();await flush();assert.equal(root.open,false,'polling must not reopen folded TEST controls');assert.equal(beeps,initialBeeps+6,'duplicate poll must not sound again');
 assert.equal(selectors['[data-uber-test-arrival]'].hidden,true,'dismissed banner must not reopen on a duplicate poll');
 if(mode==='kitchen'){
  await labels().find(el=>el.textContent==='Commencer la préparation TEST').handlers.click();await flush();
  assert.equal(stage,'En préparation');if(board){assert.equal(columns.todo.children.length,0);assert.equal(columns.doing.children.length,1);}
  await labels().find(el=>el.textContent==='Terminer la préparation TEST').handlers.click();await flush();
  assert.equal(stage,'Terminée');if(board){assert.equal(columns.doing.children.length,0);assert.equal(columns.done.children.length,1);}assert.equal(beeps,initialBeeps+6,'stage changes must not repeat arrival sound');
 }else{
  await labels().find(el=>el.textContent==='Envoyer dans la cuisine de test').handlers.click();await flush();
  assert.ok(calls.some(c=>c.url==='/api/uber/sandbox/kitchen/dispatch'&&c.options.method==='POST'));
  stage='Terminée';await poll();await flush();assert.ok(labels().some(el=>el.textContent==='Préparation TEST : Terminée'));
  assert.ok(labels().some(el=>el.tag==='button'&&el.disabled&&el.textContent==='Déjà envoyée en cuisine — Terminée'));
 }
 await poll();await flush();
 assert.equal(selectors['[data-uber-test-action-status]'].textContent,'Action test effectuée','automatic refresh must preserve the last action result');
 assert.deepEqual(untouchedCart,{items:['restaurant burger'],table:'7'});
 assert.ok(calls.every(c=>c.url.startsWith('/api/uber/sandbox/')),'only isolated sandbox endpoints may be called');
 assert.ok(calls.every(c=>!c.url.includes('send-kitchen')&&!c.url.includes('print')),'never trigger POS print interception');
}
(async()=>{await run('pos',false,true,'À préparer',true);await run('kitchen',true,true,'À préparer',true);await run('pos');await run('kitchen');await run('kitchen',true);await run('kitchen',true,true);await run('kitchen',true,true,'Terminée');console.log('Sandbox POS and kitchen alerts: arrival, deduplication, transitions and cart isolation passed.');})().catch(error=>{console.error(error);process.exitCode=1;});

