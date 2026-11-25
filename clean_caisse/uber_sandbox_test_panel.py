"""One isolated panel for sandbox POS and kitchen; alerts never drive printing."""


def panel(kitchen=False):
    mode = 'kitchen' if kitchen else 'pos'
    title = 'Cuisine Uber — TEST' if kitchen else 'Uber Eats — TEST'
    return _PANEL.replace('__MODE__', mode).replace('__TITLE__', title)


_PANEL = r'''
<style id="uber-sandbox-pos-style">
#uber-sandbox-pos{position:fixed;right:12px;bottom:12px;z-index:10010;background:#fff;color:#18251d;border:2px solid #167d46;border-radius:12px;box-shadow:0 4px 22px #0003;font:16px Arial,sans-serif;max-width:min(540px,94vw)}
#uber-sandbox-pos[data-mode="kitchen"]{position:static;max-width:100%;margin:20px 0}
#uber-sandbox-pos summary{padding:14px;cursor:pointer;font-weight:bold;background:#e7f6ec;border-radius:10px}
#uber-sandbox-pos section{padding:14px;max-height:65vh;overflow:auto}
#uber-sandbox-pos[data-mode="kitchen"] section{max-height:none}
#uber-sandbox-pos article{padding:12px 0;border-top:1px solid #ddd}
#uber-sandbox-pos p,#uber-sandbox-pos li{font:16px/1.45 Arial,sans-serif;margin:6px 0}
#uber-sandbox-pos ul{padding-left:24px;margin:6px 0}
#uber-sandbox-pos button{font:16px Arial,sans-serif;cursor:pointer;padding:10px;margin:4px}
#uber-sandbox-pos[data-board="true"] [data-uber-test-orders]{display:none}
.column:has(#uber-test-todo article) #todo>.empty,.column:has(#uber-test-doing article) #doing>.empty,.column:has(#uber-test-done article) #done>.empty{display:none}
#uber-test-doing .uber-test-kitchen-card{border-left-color:#2563eb}
#uber-test-done .uber-test-kitchen-card{border-left-color:#16a34a}
.uber-test-kitchen-card h3{font-size:20px;color:#176138}
#uber-sandbox-arrival{position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:2147483000;max-width:calc(100vw - 24px);width:max-content;background:#06C167;color:#000;border:2px solid #048848;border-radius:10px;padding:14px 20px;font:900 18px/1.4 Arial,sans-serif;box-shadow:0 8px 26px #0006;text-align:center;cursor:pointer}
#uber-sandbox-arrival[hidden]{display:none!important}
</style>
<details id="uber-sandbox-pos" data-mode="__MODE__"><summary>__TITLE__ · <span data-uber-test-count>…</span></summary>
<section><p>Commandes d’essai, hors ventes et statistiques. Aucune impression ni modification du panier en cours.</p>
<button type="button" data-uber-test-refresh>Actualiser les commandes de test</button>
<button type="button" data-uber-test-audio>Activer les alertes sonores Uber TEST</button>
<p id="uber-sandbox-arrival" data-uber-test-arrival hidden role="alert" aria-live="assertive" tabindex="0" title="Cliquer pour fermer cette alerte"></p>
<p data-uber-test-action-status role="status"></p><p data-uber-test-status role="status"></p><div data-uber-test-orders></div>
<p><a href="/administration/uber-sandbox/kitchen" target="_blank" rel="noopener">Ouvrir la cuisine Uber de test</a> · <a href="/administration/uber-sandbox/orders">Importer une commande acceptée chez Uber</a></p></section></details>
<script id="uber-sandbox-pos-script">
(function(){
'use strict';
const root=document.getElementById('uber-sandbox-pos');if(!root)return;
const kitchen=root.dataset.mode==='kitchen',board=root.dataset.board==='true';
const count=root.querySelector('[data-uber-test-count]'),status=root.querySelector('[data-uber-test-status]'),list=root.querySelector('[data-uber-test-orders]'),button=root.querySelector('[data-uber-test-refresh]'),audioButton=root.querySelector('[data-uber-test-audio]'),arrival=root.querySelector('[data-uber-test-arrival]');
const actionStatus=root.querySelector('[data-uber-test-action-status]');
// Marketplace arrival alerts are sound-only; command cards remain visible.
arrival.addEventListener('click',()=>{arrival.hidden=true;});
arrival.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();arrival.hidden=true;}});
const noticeKey='bechefaa_uber_test_notices_v1_'+root.dataset.mode+'_'+(board?'board':'panel');
let notified=new Set();try{const saved=JSON.parse(sessionStorage.getItem(noticeKey)||'[]');if(Array.isArray(saved))notified=new Set(saved);}catch(error){}
let audio=null,csrf='',busy=false,initialized=false,armed=false;const seen=new Set();
function text(tag,value,parent){const el=document.createElement(tag);el.textContent=value;parent.appendChild(el);return el;}
function money(value){return value&&Number.isInteger(value.amount)?(value.amount/100).toLocaleString('fr-FR',{minimumFractionDigits:2,maximumFractionDigits:2})+' '+value.currency_code:'montant non transmis';}
function item(value,parent,depth){if(depth>8)return;const line=text('li',String(value.quantity)+' × '+String(value.title)+(value.removed?' (retiré)':'')+(value.total_price?' — '+money(value.total_price):''),parent);if(Array.isArray(value.options)&&value.options.length){const options=document.createElement('ul');line.appendChild(options);value.options.forEach(v=>item(v,options,depth+1));}}
function beep(){if(window.bechefaaUberTestSound){window.bechefaaUberTestSound.notify();return;}if(!armed||!audio||audio.state!=='running')return;try{[0,.50,1].forEach(delay=>{const oscillator=audio.createOscillator(),gain=audio.createGain(),at=audio.currentTime+delay;oscillator.type='square';oscillator.frequency.value=1040;gain.gain.setValueAtTime(0,at);gain.gain.linearRampToValueAtTime(1,at+.02);gain.gain.setValueAtTime(1,at+.32);gain.gain.linearRampToValueAtTime(0,at+.40);oscillator.connect(gain);gain.connect(audio.destination);oscillator.start(at);oscillator.stop(at+.42);});}catch(error){status.textContent='Le son est indisponible. La commande reste affichée.';}}
audioButton.addEventListener('click',async()=>{try{if(window.bechefaaUberTestSound){const ready=await window.bechefaaUberTestSound.activate();if(!ready)throw new Error('audio blocked or muted');audioButton.textContent='Alertes sonores Uber TEST activées';return;}const Audio=window.AudioContext||window.webkitAudioContext;if(!Audio)throw new Error('audio unavailable');if(!audio)audio=new Audio();await audio.resume();if(audio.state!=='running')throw new Error('audio blocked');armed=true;audioButton.textContent='Alertes sonores Uber TEST activées';audioButton.disabled=true;beep();}catch(error){status.textContent='Son non activé. Vérifiez les réglages sonores de cet écran et d’Uber Eats, puis réessayez.';}});
function notify(ids){if(!ids.length)return;ids.forEach(id=>notified.add(id));try{sessionStorage.setItem(noticeKey,JSON.stringify([...notified].slice(-500)));}catch(error){}beep();}
async function action(url,payload,target){target.disabled=true;actionStatus.textContent='Mise à jour de la commande de test…';try{const response=await fetch(url,{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-Uber-Test-CSRF':csrf},body:JSON.stringify(payload)});const data=await response.json();if(!response.ok||!data.ok)throw new Error(data.message||'Action non effectuée. Actualisez et réessayez.');await refresh();actionStatus.textContent=data.message||'État de préparation mis à jour dans la cuisine de test.';if(!kitchen){target.disabled=true;target.textContent='Envoyée dans la cuisine de test';}}catch(error){actionStatus.textContent=error.message;target.disabled=false;}}
async function refresh(){if(busy)return;busy=true;button.disabled=true;try{
 const response=await fetch(kitchen?'/api/uber/sandbox/kitchen-display':'/api/uber/sandbox/pos-display',{cache:'no-store',credentials:'same-origin',headers:{Accept:'application/json'}});
 if(!response.ok)throw new Error('lecture indisponible');const data=await response.json();if(!data.ok||!Array.isArray(data.orders))throw new Error('réponse invalide');csrf=data.csrf||'';
 const ids=data.orders.map(snapshot=>snapshot.order.id),newIds=data.orders.filter(snapshot=>{
  const id=snapshot.order.id;if(seen.has(id)||notified.has(id))return false;if(initialized)return true;
  const at=Date.parse(kitchen?snapshot.sent_at:snapshot.imported_at),age=Date.now()-at;
  return (!kitchen||snapshot.stage==='À préparer')&&Number.isFinite(age)&&age>=0&&age<600000;
 }).map(snapshot=>snapshot.order.id);
 const cards=[];
 data.orders.forEach(snapshot=>{const order=snapshot.order,card=document.createElement('article');card.className=board?'card uber-test-kitchen-card':'';card.dataset.uberTestStage=snapshot.stage||'';text('h3','TEST · Uber '+String(order.display_id||order.id.slice(-5)),card);text('p',kitchen?'Préparation TEST : '+snapshot.stage:'État lu à l’import : '+String(order.current_state),card);if(!kitchen)text('p',data.kitchen_status_available===false?'Préparation TEST : lecture indisponible':'Préparation TEST : '+(snapshot.kitchen_stage||'Non envoyée en cuisine'),card);const ul=document.createElement('ul');card.appendChild(ul);order.items.forEach(v=>item(v,ul,0));text('p','Total restaurant Uber : '+money(order.charges.total),card);text('p',(kitchen?'Envoyée le ':'Importée le ')+new Date(kitchen?snapshot.sent_at:snapshot.imported_at).toLocaleString('fr-FR'),card);
 if(csrf){if(kitchen){const next=snapshot.stage==='À préparer'?'En préparation':(snapshot.stage==='En préparation'?'Terminée':null);if(next){const stageButton=text('button',next==='En préparation'?'Commencer la préparation TEST':'Terminer la préparation TEST',card);stageButton.type='button';stageButton.addEventListener('click',()=>action('/api/uber/sandbox/kitchen/stage',{order_id:order.id,previous:snapshot.stage,stage:next},stageButton));}}else{const sendButton=text('button',snapshot.kitchen_stage?'Déjà envoyée en cuisine — '+snapshot.kitchen_stage:'Envoyer dans la cuisine de test',card);sendButton.type='button';sendButton.disabled=Boolean(snapshot.kitchen_stage)||data.kitchen_status_available===false;sendButton.addEventListener('click',()=>action('/api/uber/sandbox/kitchen/dispatch',{order_id:order.id},sendButton));}}
 const a=document.createElement('a');a.textContent='Relire l’état actuel chez Uber';a.href='/administration/uber-sandbox/orders?order_id='+encodeURIComponent(order.id);card.appendChild(a);cards.push(card);});if(board){for(const [stage,id] of [['À préparer','todo'],['En préparation','doing'],['Terminée','done']]){const target=document.getElementById('uber-test-'+id);if(target)target.replaceChildren(...cards.filter(card=>card.dataset.uberTestStage===stage));}}else list.replaceChildren(...cards);count.textContent=String(data.orders.length);status.textContent=data.orders.length?'':(kitchen?'Aucune commande envoyée dans la cuisine de test.':'Aucune commande importée dans ce bloc de test.');ids.forEach(id=>seen.add(id));initialized=true;notify(newIds);
}catch(error){status.textContent='Lecture indisponible. Cliquez sur Actualiser pour réessayer.';}finally{busy=false;button.disabled=false;}}
button.addEventListener('click',refresh);refresh();const poll=setInterval(refresh,5000);window.addEventListener('pagehide',()=>clearInterval(poll),{once:true});document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
if((kitchen&&!board)||new URLSearchParams(location.search).has('uber_test_import'))root.open=true;
})();
</script>
'''

