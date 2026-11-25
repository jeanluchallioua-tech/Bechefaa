'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const script=fs.readFileSync('clean_caisse/static/pos-active-cart.js','utf8');
const storage=()=>{const data=new Map();return{getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,String(v)),removeItem:k=>data.delete(k),data};};
function screen(local=storage(),session=storage(),search='',configure=null){
 const fields=[{id:'cust-first',value:''},{id:'cust-phone',value:''},{id:'cust-floor',value:''}];
 const nodes=new Map(fields.map(el=>[el.id,el]));const events={},timers=[],service={mode:null,table:null};
 const context={console,Date,Math,JSON,Promise,URLSearchParams,location:{search},crypto:{randomUUID:()=>Math.random().toString(36).slice(2)},localStorage:local,sessionStorage:session,
 ORDER:[],TICKET_TYPE:'Salle',MANUAL_DISCOUNT:10,current:'Burgers',currentProduct:{id:'p2',name:'Autre burger'},currentGroups:[{name:'Cuisson'}],selections:{'0:1':true},DATA:{},LAST_SAVED_ORDER:null,SAVE_IN_FLIGHT:null,
 renderOrder(){},render(){},CustomEvent:class{constructor(type,values){this.type=type;this.detail=values.detail;}},
 document:{readyState:'complete',querySelectorAll:()=>fields,getElementById:id=>nodes.get(id)||null,createElement:()=>({setAttribute(){}}),body:{appendChild(el){nodes.set(el.id,el);el.parentNode=this;}},
 addEventListener:(name,fn)=>{(events[name]||=[]).push(fn)},dispatchEvent:event=>(events[event.type]||[]).forEach(fn=>fn(event))},
 setTimeout:fn=>timers.push(fn),window:{addEventListener:(name,fn)=>{(events[name]||=[]).push(fn)},bechefaaServiceDraft:{read:()=>({...service}),restore:value=>Object.assign(service,value)},bechefaaPendingEdit:{draftContext:()=>null,whenSaved:()=>Promise.resolve()}}};
 if(configure)configure(context);
 vm.runInNewContext(script,context);while(timers.length)timers.shift()();
 return{context,local,session,fields,service,events,fire:name=>(events[name]||[]).forEach(fn=>fn({type:name}))};
}
const item={line_id:'l1',product_id:'p1',name:'Burger',qty:2,unit_price:17.5,options:[{name:'Bien cuit'}]};
(async()=>{
 const first=screen();first.context.ORDER=[item];first.fields[0].value='Jean-Luc';first.fields[1].value='0711111111';first.service.mode='salle';first.service.table=3;first.context.MANUAL_DISCOUNT=20;first.context.current='Sandwiches';first.context.selections={'1:0':true};first.context.renderOrder();
 await first.context.window.bechefaaPrepareIncomingPrint();
 assert.equal(first.context.ORDER.length,1,'receiving print must not clear cashier cart');
 const returned=screen(first.local,first.session,'?epson=success');
 assert.deepEqual(JSON.parse(JSON.stringify(returned.context.ORDER)),[item]);
 assert.equal(returned.context.TICKET_TYPE,'Salle');assert.equal(returned.context.MANUAL_DISCOUNT,20);
 assert.deepEqual(returned.service,{mode:'salle',table:3});assert.equal(returned.context.current,'Sandwiches');
 assert.equal(returned.context.selections['1:0'],true);assert.equal(returned.fields[0].value,'Jean-Luc');assert.equal(returned.fields[1].value,'0711111111');
 const otherTab=screen(first.local,storage());assert.equal(otherTab.context.ORDER.length,0,'unrelated POS tab must not steal active cart');
 const callbackTab=screen(first.local,storage(),'?epson=success');assert.equal(callbackTab.context.ORDER.length,1,'Epson callback in a fresh tab must recover print handoff');
 returned.context.ORDER=[];returned.context.LAST_SAVED_ORDER={id:'saved'};returned.context.renderOrder();const savedReturn=screen(returned.local,returned.session);assert.equal(savedReturn.context.ORDER.length,0,'saved cart must never resurrect');
 const busy=screen();busy.context.ORDER=[item];let finish;
 busy.context.SAVE_IN_FLIGHT=new Promise(resolve=>{finish=()=>{busy.context.ORDER=[];busy.context.renderOrder();busy.context.SAVE_IN_FLIGHT=null;resolve();};});
 let prepared=false;const pending=busy.context.window.bechefaaPrepareIncomingPrint().then(()=>prepared=true);
 await Promise.resolve();assert.equal(prepared,false,'do not interrupt an in-flight server save');finish();await pending;
 const busyReturn=screen(busy.local,busy.session);assert.equal(busyReturn.context.ORDER.length,0,'confirmed saved order must not restore as unsaved');
 const edits=screen();edits.context.ORDER=[item];edits.context.window.bechefaaPendingEdit.draftContext=()=>({id:'saved-order',status:'Enregistrée'});edits.context.renderOrder();
 let restoredEdit=null;const saved=edits.local;
 const editReturn=screen(edits.local,edits.session,'',ctx=>{ctx.window.bechefaaPendingEdit.restoreDraftContext=order=>{restoredEdit=order;ctx.LAST_SAVED_ORDER=order;};});
 assert.equal(restoredEdit.id,'saved-order');assert.equal(editReturn.context.LAST_SAVED_ORDER.id,'saved-order');
 const key=[...saved.data.keys()].find(k=>k.startsWith('bechefaa_active_cart_v2_'));
 assert.equal(JSON.parse(saved.data.get(key)).edit.id,'saved-order');
 const partial=screen();partial.fields[0].value='Client';partial.context.window.bechefaaProductDraft={isOpen:()=>true};partial.context.renderOrder();
 let reopened=false;const partialReturn=screen(partial.local,partial.session,'',ctx=>{ctx.window.bechefaaProductDraft={isOpen:()=>false,restore:()=>{reopened=true;}};});
 assert.equal(reopened,true,'first product options reopen even before adding it to empty cart');assert.equal(partialReturn.fields[0].value,'Client');assert.equal(partialReturn.context.ORDER.length,0);
 const fail=screen();fail.context.ORDER=[item];fail.local.setItem=()=>{throw Error('quota')};fail.session.setItem=()=>{throw Error('blocked')};
 await assert.rejects(()=>fail.context.window.bechefaaPrepareIncomingPrint(),/Panier non sauvegardé/);
 assert.equal(fail.context.ORDER.length,1,'storage failure must keep current cart');
 console.log('Active cart: Epson round trip, fresh-tab callback, options/table/customer/discount, save completion, edit context and storage failure passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
