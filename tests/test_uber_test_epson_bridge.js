'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('clean_caisse/epson_epos_network_phase6.py','utf8');
const helper=source.match(/ async function openPrintAssistant\(xml,label,orderId\)\{([\s\S]*?)\n async function printClient/)[0].replace(/\n async function printClient$/,'');
const bridge=source.match(/ window.bechefaaPrintOrderPack=printOrderPack;([\s\S]*?)\n async function printKitchen/)[1];
async function screen(host,android=true,ok=true){
 const calls=[];const location={hostname:host,origin:'https://'+host,pathname:'/pos',href:'unchanged'};
 const xml='<epos-print><image>kitchen</image><cut type="feed"/><image>client</image><cut type="feed"/></epos-print>';
 const context={window:{location},location,navigator:{userAgent:android?'Android':'Windows'},status(){},epsonDiag(){},printed:new Set(),
  nativeFetch:async(url,options)=>{calls.push({url,options});return{ok,text:async()=>xml};}};
 vm.runInNewContext('let assistantPending=false,assistantHidden=false;'+helper+bridge,context);
 return{context,calls,location,xml};
}
(async()=>{
 const host='app-fad0809f-954d-47e7-983d-afb7c3867cd0.cleverapps.io',id='4b54b4f9-7bc7-4f78-b25c-1d9ea41006b6';
 const tablet=await screen(host);await tablet.context.window.bechefaaPrintUberTestPack(id);
 assert.equal(tablet.calls[0].url,'/api/uber/sandbox/receipt-pack-xml/'+id);
 const url=new URL(tablet.location.href);assert.equal(url.protocol,'tmprintassistant:');
 assert.equal(url.searchParams.get('data'),tablet.xml);assert.equal(url.searchParams.get('success'),'https://'+host+'/pos?epson=success');
 assert.equal((url.searchParams.get('data').match(/<cut /g)||[]).length,2);
 const pc=await screen(host,false);await assert.rejects(()=>pc.context.window.bechefaaPrintUberTestPack(id),/Android/);assert.equal(pc.calls.length,0);
 const failed=await screen(host,true,false);await assert.rejects(()=>failed.context.window.bechefaaPrintUberTestPack(id),/indisponibles/);assert.equal(failed.location.href,'unchanged');
 const prod=await screen('caisse.bechefaa.fr');assert.equal(prod.context.window.bechefaaPrintUberTestPack,undefined);
 console.log('Uber TEST Epson bridge: fixed sandbox XML, both cuts, callback, PC rejection, failed fetch and production isolation passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
