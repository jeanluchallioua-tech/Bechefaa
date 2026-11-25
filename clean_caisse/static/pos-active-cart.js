/* Current POS draft stays independent of received orders and Epson navigation. */
(function(){
'use strict';
function install(){
 if(window.bechefaaActiveCartProtection||typeof ORDER==='undefined'||typeof renderOrder!=='function')return;
 const PREFIX='bechefaa_active_cart_v2_',OWNER='bechefaa_active_cart_owner_v2',HANDOFF='bechefaa_active_cart_print_v2';
 let owner='';try{owner=sessionStorage.getItem(OWNER)||'';}catch(_){}
 if(new URLSearchParams(location.search).has('epson')){try{const pending=JSON.parse(localStorage.getItem(HANDOFF)||'null');if(pending&&typeof pending.owner==='string'&&Date.now()-pending.at<600000)owner=pending.owner;}catch(_){}}
 if(!owner)owner=typeof crypto!=='undefined'&&crypto.randomUUID?crypto.randomUUID():Date.now().toString(36)+Math.random().toString(36).slice(2);
 try{sessionStorage.setItem(OWNER,owner);}catch(_){}
 const key=PREFIX+owner;let restoring=false,restoreBlocked=false;
 const clone=value=>JSON.parse(JSON.stringify(value));
 function storageRead(){for(const store of [localStorage,sessionStorage]){try{const raw=store.getItem(key);if(raw)return JSON.parse(raw);}catch(_){}}return null;}
 function fields(){const values={};document.querySelectorAll('.customer-box input[id],.customer-box textarea[id],.customer-box select[id]').forEach(el=>{if(el.type!=='password')values[el.id]={value:el.value,checked:el.checked};});return values;}
 function snapshot(){return{version:2,at:Date.now(),items:clone(ORDER),ticket:TICKET_TYPE,
  discount:typeof MANUAL_DISCOUNT!=='undefined'?MANUAL_DISCOUNT:0,
  category:typeof current!=='undefined'?current:null,fields:fields(),
  product:typeof currentProduct!=='undefined'?clone(currentProduct):null,
  groups:typeof currentGroups!=='undefined'?clone(currentGroups):[],
  selections:typeof selections!=='undefined'?clone(selections):{},
  service:window.bechefaaServiceDraft?window.bechefaaServiceDraft.read():null,
  options_open:!!(window.bechefaaProductDraft&&window.bechefaaProductDraft.isOpen()),
  edit:window.bechefaaPendingEdit&&window.bechefaaPendingEdit.draftContext?window.bechefaaPendingEdit.draftContext():null};}
 function clear(){for(const store of [localStorage,sessionStorage]){try{store.removeItem(key);}catch(_){}}}
 function persist(forPrint=false){
  if(restoring)return true;if(restoreBlocked||!Array.isArray(ORDER))return false;
  try{
   const data=snapshot();const unsaved=typeof LAST_SAVED_ORDER==='undefined'||!LAST_SAVED_ORDER;
   const workspace=unsaved&&(Boolean(data.service&&data.service.mode)||Object.values(data.fields).some(field=>String(field.value||'').trim()));
   if(!ORDER.length&&!data.options_open&&!workspace){clear();return true;}
   data.workspace=true;const raw=JSON.stringify(data);let saved=false;
   for(const store of [localStorage,sessionStorage]){try{store.setItem(key,raw);saved=true;}catch(_){}}
   if(saved&&forPrint){try{localStorage.setItem(HANDOFF,JSON.stringify({owner,at:Date.now()}));}catch(_){}}
   if(!saved)throw Error('storage unavailable');return true;
  }catch(_){const el=document.getElementById('active-cart-warning')||document.createElement('p');el.id='active-cart-warning';el.setAttribute('role','alert');el.textContent='Sauvegarde locale du panier indisponible. Gardez cet écran ouvert et enregistrez la commande.';const host=document.getElementById('order-message')||document.body;if(!el.parentNode)host.appendChild(el);return false;}
 }
 function restore(){
  const saved=storageRead();
  if(!saved||saved.version!==2||Date.now()-Number(saved.at)>86400000||!Array.isArray(saved.items)||(!saved.items.length&&!saved.workspace)||ORDER.length)return;
  if(!saved.items.every(item=>item&&typeof item.name==='string'&&Number.isFinite(Number(item.unit_price))&&Number(item.qty)>0))return;
  if(saved.edit&&(!window.bechefaaPendingEdit||!window.bechefaaPendingEdit.restoreDraftContext)){
   restoreBlocked=true;const el=document.getElementById('order-message');if(el)el.textContent='Modification conservée. Rechargez la caisse pour charger sa protection avant de poursuivre.';return;
  }
  restoring=true;
  try{
   ORDER=clone(saved.items);TICKET_TYPE=String(saved.ticket||'Comptoir');
   if(typeof MANUAL_DISCOUNT!=='undefined')MANUAL_DISCOUNT=Number(saved.discount)||0;
   if(typeof current!=='undefined')current=saved.category||null;
   if(typeof currentProduct!=='undefined')currentProduct=clone(saved.product||null);
   if(typeof currentGroups!=='undefined')currentGroups=clone(saved.groups||[]);
   if(typeof selections!=='undefined')selections=clone(saved.selections||{});
   Object.entries(saved.fields||{}).forEach(([id,value])=>{const el=document.getElementById(id);if(el&&el.type!=='password'){el.value=String(value.value||'');if(typeof value.checked==='boolean')el.checked=value.checked;}});
   if(saved.service&&window.bechefaaServiceDraft)window.bechefaaServiceDraft.restore(saved.service);
   if(saved.edit&&window.bechefaaPendingEdit&&window.bechefaaPendingEdit.restoreDraftContext)window.bechefaaPendingEdit.restoreDraftContext(saved.edit);
   if(saved.options_open&&window.bechefaaProductDraft)window.bechefaaProductDraft.restore();
   renderOrder();if(typeof render==='function'&&typeof DATA!=='undefined'&&DATA)render();
   document.dispatchEvent(new CustomEvent('bechefaa:draft-restored',{detail:{service:saved.service}}));
  }finally{restoring=false;}
 }
 restore();
 const original=renderOrder;renderOrder=function(){const result=original.apply(this,arguments);persist();return result;};
 window.bechefaaPrepareIncomingPrint=async function(){
  if(typeof SAVE_IN_FLIGHT!=='undefined'&&SAVE_IN_FLIGHT)await SAVE_IN_FLIGHT;
  if(window.bechefaaPendingEdit&&window.bechefaaPendingEdit.whenSaved)await window.bechefaaPendingEdit.whenSaved();
  if(!persist(true))throw Error('Panier non sauvegardé : enregistrez-le avant de relancer l’impression.');
 };
 window.bechefaaActiveCartProtection={persist,restore};
 document.addEventListener('input',()=>persist());document.addEventListener('change',()=>setTimeout(()=>persist(),0));document.addEventListener('click',()=>setTimeout(()=>persist(),0));
 document.addEventListener('bechefaa:order-saved',()=>persist());document.addEventListener('bechefaa:new-order',clear);
 window.addEventListener('pagehide',()=>persist());window.addEventListener('beforeunload',()=>persist());
}
function ready(){setTimeout(()=>setTimeout(install,0),0);}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',ready);else ready();
})();
