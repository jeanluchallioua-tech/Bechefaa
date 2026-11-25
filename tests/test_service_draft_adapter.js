const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const raw=fs.readFileSync('clean_caisse/service_mode_ui_phase42.py','utf8');
const code=raw.match(/<script id="phase42-service-mode-script">([\s\S]*?)<\/script>/)[1];
const button=value=>({dataset:value,classList:{toggle(){}},addEventListener(){}});
const ticket={querySelectorAll:()=>['salle','emporter','livraison'].map(mode=>button({ticket:mode})),addEventListener(){}};
const grid={classList:{toggle(){}},querySelectorAll:()=>Array.from({length:9},(_,i)=>button({phase42Table:i+1})),addEventListener(){}};
const sent=[];const context={window:{fetch:(url,init)=>{sent.push(JSON.parse(init.body));return Promise.resolve({});}},
 document:{readyState:'complete',querySelector:()=>ticket,getElementById:id=>id==='phase42-table-grid'?grid:null,addEventListener(){}}};
vm.runInNewContext(code,context);
context.window.bechefaaServiceDraft.restore({mode:'salle',table:3});
context.window.fetch('/api/orders',{method:'POST',body:JSON.stringify({items:[]})});
assert.equal(sent[0].service_mode,'SALLE');assert.equal(sent[0].table_number,3);
context.window.bechefaaServiceDraft.restore({mode:'livraison',table:null});
context.window.fetch('/api/orders',{method:'POST',body:JSON.stringify({items:[]})});
assert.equal(sent[1].service_mode,'LIVRAISON');assert.equal(sent[1].table_number,null);
console.log('Restored service mode and table are used by the real order payload adapter.');
