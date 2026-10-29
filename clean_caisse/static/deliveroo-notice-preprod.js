// Isolated preproduction replacement for the POS Deliveroo history poller.
const deliverooNoticeKey='bechefaa_deliveroo_notice_v1';
let deliverooNoticeState={seen:{},pending:[]},deliverooNoticeBusy=false,deliverooNoticeInitialized=false;
try{
 const saved=JSON.parse(sessionStorage.getItem(deliverooNoticeKey)||'null');
 if(saved&&saved.seen&&typeof saved.seen==='object'&&Array.isArray(saved.pending))deliverooNoticeState=saved;
}catch(_){}
function saveDeliverooNotice(){
 const ids=Object.keys(deliverooNoticeState.seen).slice(-500);
 deliverooNoticeState.seen=Object.fromEntries(ids.map(id=>[id,1]));
 try{sessionStorage.setItem(deliverooNoticeKey,JSON.stringify(deliverooNoticeState));}catch(_){}
}
function renderDeliverooNotice(banner){
 const pending=deliverooNoticeState.pending;
 banner.classList.toggle('visible',pending.length>0);
 banner.textContent=pending.length?'🛵 NOUVELLE COMMANDE DELIVEROO — '+pending.map(o=>o.ref?'réf. '+o.ref:'commande Deliveroo').join(', ')+' • Voir la cuisine / historique':'';
 if(!pending.length)return;
 // Remain visible independently of POS layout scrolling and overlays.
 Object.assign(banner.style,{position:'fixed',top:'64px',left:'12px',right:'12px',zIndex:'2147482999',cursor:'pointer'});
 banner.tabIndex=0;
 const dismiss=()=>{deliverooNoticeState.pending=[];saveDeliverooNotice();renderDeliverooNotice(banner);};
 banner.onclick=dismiss;
 banner.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();dismiss();}};
}
async function checkDeliveroo(){
 if(deliverooNoticeBusy)return;
 deliverooNoticeBusy=true;
 try{
  const r=await fetch('/api/orders/history',{cache:'no-store'}),d=await r.json();
  if(!r.ok||!d.ok||!Array.isArray(d.orders))return;
  const banner=document.getElementById('deliveroo-alert');
  // Retry next poll rather than silently consume an alert that could not render.
  if(!banner)return;
  const orders=d.orders.filter(o=>o.id&&String(o.sales_channel||o.source||'').toUpperCase()==='DELIVEROO'
    &&['À préparer','En préparation','Prête'].includes(String(o.status||'').trim()));
  const ids=new Set(orders.map(o=>String(o.id)));
  deliverooNoticeState.pending=deliverooNoticeState.pending.filter(o=>ids.has(o.id));
  const fresh=orders.filter(o=>!deliverooNoticeState.seen[String(o.id)]&&
    (deliverooNoticeInitialized||(Number(o.created_at)>0&&Date.now()-Number(o.created_at)>=0&&Date.now()-Number(o.created_at)<600000)));
  for(const order of fresh){
   const id=String(order.id);
   if(!deliverooNoticeState.pending.some(o=>o.id===id))deliverooNoticeState.pending.push({id,ref:String(order.platform_reference||'')});
  }
  renderDeliverooNotice(banner);
  for(const order of orders)deliverooNoticeState.seen[String(order.id)]=1;
  deliverooNoticeInitialized=true;
  saveDeliverooNotice();
  if(fresh.length&&typeof window.bechefaaNotifyDeliveroo==='function')window.bechefaaNotifyDeliveroo();
 }catch(e){console.warn('Deliveroo history check',e);}
 finally{deliverooNoticeBusy=false;}
}
checkDeliveroo();setInterval(checkDeliveroo,5000);
window.addEventListener('pageshow',checkDeliveroo);
window.addEventListener('focus',checkDeliveroo);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkDeliveroo();});
