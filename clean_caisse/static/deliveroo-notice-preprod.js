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
 if(banner){banner.classList.remove('visible');banner.hidden=true;banner.textContent='';}
}
async function checkDeliveroo(){
 if(deliverooNoticeBusy)return;
 deliverooNoticeBusy=true;
 try{
  const r=await fetch('/api/orders/history',{cache:'no-store'}),d=await r.json();
  if(!r.ok||!d.ok||!Array.isArray(d.orders))return;
  const banner=document.getElementById('deliveroo-alert');
  // Sound does not depend on a visual banner.
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

