"""Couche visuelle POS sombre alignée sur la maquette BÉCHÉFAA.

Aucune modification de schéma. La logique métier existante reste la source de vérité.
Cette couche corrige l'ergonomie, les liens, les tables, l'upsell et les actions directes POS.
"""


def register_pos_reference_dark(app):
    if getattr(app, "_bechefaa_pos_reference_dark", False):
        return

    original = app.view_functions.get("pos")
    if original is None:
        return

    addon = r'''
<style id="pos-reference-dark-style">
:root{--bg:#07090b;--p1:#0b0e11;--p2:#101418;--p3:#151a1f;--line:#2a3036;--txt:#f5f3ef;--muted:#8d949d;--gold:#e8b44a;--gold2:#f2c35b;--red:#c85448}
html,body{background:var(--bg)!important;color:var(--txt)!important}.top{height:52px!important;min-height:52px!important;background:#090b0d!important;border-bottom:1px solid #20252b!important;color:#fff!important;padding:0 18px 0 205px!important}.top>b{display:none!important}.top .status{margin-left:auto!important;color:#aeb5bc!important;font-size:11px!important}.layout{grid-template-columns:195px minmax(0,1fr) 430px!important;height:calc(100vh - 52px)!important;background:var(--bg)!important}
.main,.cart,.pos-v3-rail{scrollbar-width:none!important}.main::-webkit-scrollbar,.cart::-webkit-scrollbar,.cats::-webkit-scrollbar,.pos-v3-rail::-webkit-scrollbar{display:none!important}.main{background:#090b0e!important;color:#fff!important;overflow:auto!important}.cart{background:#0b0e11!important;color:#fff!important;border-left:1px solid #252b31!important;overflow:auto!important}.pos-v3-rail{min-width:195px!important;width:195px!important;background:#0b0e11!important;border-right:1px solid #20252b!important;padding:14px 10px!important;align-items:stretch!important;gap:6px!important;overflow:auto!important}
.pos-v3-brand{height:126px!important;background:transparent!important;margin:0 0 10px!important;display:flex!important;flex-direction:column!important;align-items:center!important;justify-content:center!important;gap:7px!important}.pos-v3-brand:before,.pos-v3-brand:after{display:none!important}.pos-ref-logo{width:72px;height:72px;object-fit:contain;display:block}.pos-ref-brandname{color:var(--gold)!important;font-size:15px;font-weight:900;letter-spacing:3px}.pos-v3-nav{min-height:54px!important;width:100%!important;display:flex!important;flex-direction:row!important;justify-content:flex-start!important;align-items:center!important;gap:12px!important;padding:0 15px!important;border-radius:8px!important;color:#b9bec5!important;font-size:13px!important;text-decoration:none!important}.pos-v3-nav span{font-size:20px!important;width:24px;text-align:center}.pos-v3-nav:hover{background:#15191e!important}.pos-v3-nav.active{background:linear-gradient(90deg,#392d17,#221b10)!important;border:1px solid #745b28!important;color:#fff!important;box-shadow:inset 3px 0 0 var(--gold)!important}.pos-v3-rail-spacer{flex:1!important}.pos-ref-recent{border:0!important;cursor:pointer!important;text-align:left!important;font-family:inherit!important}.pos-ref-recent span{display:inline-block!important}.pos-ref-recent-label{font-size:13px!important}
.pos-v3-toolbar{position:sticky!important;top:0!important;z-index:50!important;background:#0c0f12!important;border-bottom:1px solid #20252b!important;padding:12px 16px 10px!important;display:grid!important;grid-template-columns:1fr auto!important;gap:10px!important}.pos-v3-service{grid-column:1!important;display:grid!important;grid-template-columns:repeat(3,1fr)!important;gap:10px!important}.pos-v3-service .ticket-choice{display:contents!important}.pos-v3-service .ticket-choice button{height:58px!important;border:1px solid #30363d!important;border-radius:8px!important;background:#101418!important;color:#f0f1f2!important;font-size:14px!important;font-weight:900!important}.pos-v3-service .ticket-choice button.active{background:linear-gradient(180deg,#302716,#201a0f)!important;color:#f6d17a!important;border:2px solid var(--gold)!important}.pos-v3-clock{grid-column:2!important;grid-row:1!important;color:#aeb4ba!important}.pos-v3-time{color:#fff!important}.pos-v3-user{background:#11161b!important;border:1px solid #2c333a!important}.pos-v3-search{display:none!important}.title{display:none!important}
.pos-ref-tablebar{display:none;padding:9px 16px 10px;background:#0c0f12;border-bottom:1px solid #20252b;grid-template-columns:repeat(9,1fr);gap:7px}.pos-ref-tablebar.show{display:grid}.pos-ref-tablebar button{height:40px;background:#111519;color:#e9eaeb;border:1px solid #30363d;border-radius:7px;font-size:12px;font-weight:900;cursor:pointer}.pos-ref-tablebar button.active{background:var(--gold);color:#111;border-color:var(--gold)}#phase36-table-selector{position:absolute!important;left:-10000px!important;top:-10000px!important;display:block!important;width:1px!important;height:1px!important;overflow:hidden!important}
.cats{background:#0b0e11!important;padding:10px 16px!important;gap:8px!important;border-bottom:1px solid #20252b!important;overflow-x:auto!important;white-space:nowrap!important}.cat{background:#111519!important;color:#e7e8e9!important;border:1px solid #2a3037!important;border-radius:8px!important;padding:11px 18px!important;font-size:12px!important}.cat.active{background:linear-gradient(180deg,#f0c56a,#dca83e)!important;color:#111!important;border-color:#e7b34a!important}.grid{padding:14px 16px!important;grid-template-columns:repeat(auto-fill,minmax(175px,1fr))!important;gap:12px!important}.product{background:#0f1316!important;border:1px solid #292f35!important;border-radius:8px!important;padding:9px!important;min-height:230px!important;color:#fff!important;box-shadow:none!important;position:relative!important}.product:hover{transform:none!important;border-color:#6e572c!important}.product-photo{height:140px!important;border-radius:6px!important;background:#090b0d!important}.name{font-size:14px!important;color:#f7f7f6!important}.meta{color:#747c84!important}.badge{background:#302715!important;color:#e7bd5d!important}.price{color:var(--gold2)!important;font-size:19px!important;padding-right:44px!important}.product:after{content:'+';display:flex;align-items:center;justify-content:center;width:36px;height:36px;border-radius:50%;background:var(--gold);color:#111;font-size:22px;font-weight:900;position:absolute;right:10px;bottom:10px}
.cart:before{content:'Commande en cours'!important;padding:18px 16px 12px!important;font-size:19px!important;letter-spacing:0!important;color:#fff!important;text-transform:none!important;border-bottom:1px solid #242a30!important}.cart>.ticket-choice{display:none!important}.pos-recent-orders-btn{display:none!important}.touch-client-summary{background:#101418!important;color:#fff!important;border-color:#2c3238!important;margin:8px 14px!important}.touch-client-summary span{color:#8f969e!important}.touch-client-summary .tc-edit{background:#1b2026!important}.order-box{padding:8px 16px 6px!important}.order-box>h2{display:none!important}.empty{color:#858c94!important}.order-line{border-bottom:1px solid #262c32!important}.order-line-head{color:#fff!important}.order-opts{color:#a9afb5!important}.remove{color:#d46a60!important}.order-total{border-top:1px solid #343a40!important;color:#fff!important;font-size:27px!important}.order-total span:last-child{color:var(--gold2)!important}
#options{background:#0f1316!important;border:1px solid #2a3036!important;color:#fff!important;margin:8px 14px 10px!important}.selection-summary{background:#0b0e11!important;border-color:#292f35!important;color:#fff!important}.opt-group{border-top-color:#292f35!important}.rule{color:#858c94!important}.opt-value{background:#151a1f!important;color:#e7e9ea!important;border-color:#2b3239!important}.opt-value.selected{background:#2b2415!important;color:#f2c45e!important;border-color:#7b612d!important}.action.add{background:var(--gold)!important;color:#111!important}body.pos-ref-options-closed #options{display:none!important}
.pos-v2-upsell{display:none!important}.note{display:none!important}
.pos-ref-actions{position:sticky;bottom:0;background:#0b0e11;border-top:1px solid #262c32;padding:12px 14px 14px;z-index:30}.pos-ref-actions button{width:100%;min-height:58px;border-radius:8px;font-size:15px;font-weight:900;cursor:pointer;margin-top:8px}.pos-ref-kitchen{background:linear-gradient(180deg,#f0c568,#e4ad43);color:#111;border:0}.pos-ref-pay{background:#13171b;color:#fff;border:1px solid #4a5158}.pos-ref-actions button:disabled{opacity:.45;cursor:not-allowed}
.pos-recent-panel{background:#0f1316!important;color:#fff!important}.pos-recent-head{border-bottom-color:#2b3137!important}.pos-recent-head h2{color:#fff!important}.pos-recent-close{background:#20262c!important;color:#fff!important}.pos-recent-list{background:#0f1316!important}.pos-recent-row{background:#11161a!important;border-color:#2d3339!important;color:#fff!important}.pos-recent-title{color:#fff!important}.pos-recent-meta{color:#a7adb4!important}.pos-recent-empty{color:#a7adb4!important}.pos-recent-actions a{color:#fff!important}
.pos-ref-upsell-overlay,.pos-ref-pay-overlay{display:none;position:fixed;inset:0;z-index:25000;background:#000b;align-items:center;justify-content:center;padding:18px}.pos-ref-upsell-overlay.open,.pos-ref-pay-overlay.open{display:flex}.pos-ref-modal{width:min(560px,96vw);max-height:90vh;overflow:auto;background:#101418;border:1px solid #343b42;border-radius:16px;padding:18px;color:#fff;box-shadow:0 24px 70px #0008}.pos-ref-modal h2{margin:0 0 14px}.pos-ref-upsell-list{display:grid;gap:9px}.pos-ref-upsell-item{display:flex;align-items:center;gap:10px;border:1px solid #30363d;background:#0b0e11;border-radius:10px;padding:9px;cursor:pointer;color:#fff}.pos-ref-upsell-item img{width:54px;height:54px;border-radius:8px;object-fit:cover}.pos-ref-upsell-item b{flex:1;text-align:left}.pos-ref-upsell-price{color:var(--gold2);font-weight:900}.pos-ref-no,.pos-ref-cancel{width:100%;margin-top:12px;min-height:46px;border-radius:9px;border:1px solid #414850;background:#151a1f;color:#fff;font-weight:900;cursor:pointer}.pos-ref-pay-total{font-size:28px;color:var(--gold2);font-weight:900;text-align:center;margin:10px 0 14px}.pos-ref-pay-methods{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.pos-ref-pay-method{min-height:58px;border:1px solid #363d44;background:#151a1f;color:#fff;border-radius:9px;font-weight:900;cursor:pointer}.pos-ref-pay-method.active{background:var(--gold);color:#111;border-color:var(--gold)}.pos-ref-field{margin-top:12px}.pos-ref-field label{display:block;margin-bottom:6px;font-weight:900}.pos-ref-field input{width:100%;height:48px;background:#0b0e11;color:#fff;border:1px solid #363d44;border-radius:8px;padding:0 12px;font-size:18px}.pos-ref-pay-confirm{width:100%;min-height:52px;margin-top:14px;border:0;border-radius:9px;background:var(--gold);color:#111;font-weight:900;font-size:15px;cursor:pointer}.pos-ref-pay-error{color:#ef8a7f;font-weight:800;margin-top:10px}.pos-ref-hidden{display:none!important}
@media(max-width:1250px){.layout{grid-template-columns:165px minmax(0,1fr) 370px!important}.pos-v3-rail{min-width:165px!important;width:165px!important}.grid{grid-template-columns:repeat(auto-fill,minmax(155px,1fr))!important}.pos-ref-tablebar{grid-template-columns:repeat(5,1fr)}}

/* Tablette Samsung : source visuelle réelle du rail et des modes de service. */
html.bechefaa-tablet .layout{
  grid-template-columns:180px minmax(0,1fr) 285px!important;
}
html.bechefaa-tablet .pos-v3-rail{
  min-width:180px!important;
  width:180px!important;
}
html.bechefaa-tablet .pos-v3-rail a.pos-v3-nav.active[href="/pos"]{
  display:none!important;
}
html.bechefaa-tablet .pos-v3-toolbar{
  padding:12px 28px 10px!important;
  display:flex!important;
  justify-content:center!important;
  align-items:center!important;
}
html.bechefaa-tablet .pos-v3-service{
  width:min(920px,100%)!important;
  max-width:920px!important;
  margin:0 auto!important;
  display:block!important;
}
html.bechefaa-tablet .pos-v3-service .ticket-choice{
  width:100%!important;
  display:grid!important;
  grid-template-columns:repeat(3,minmax(0,1fr))!important;
  gap:18px!important;
  margin:0!important;
}
html.bechefaa-tablet .pos-v3-service .ticket-choice button{
  width:100%!important;
  min-width:0!important;
  height:68px!important;
  padding:0 24px!important;
  font-size:18px!important;
  white-space:nowrap!important;
  display:flex!important;
  align-items:center!important;
  justify-content:center!important;
}

html.bechefaa-tablet .grid{
  grid-template-columns:repeat(4,224px)!important;
  column-gap:18px!important;
  row-gap:18px!important;
  justify-content:center!important;
  padding-left:10px!important;
  padding-right:10px!important;
}
html.bechefaa-tablet .product{
  width:224px!important;
  max-width:224px!important;
  min-height:190px!important;
  padding:2px!important;
}
html.bechefaa-tablet .product-photo{
  width:220px!important;
  max-width:220px!important;
  height:145px!important;
  object-fit:cover!important;
  margin:0 auto 7px!important;
  display:block!important;
}
</style>
<script id="pos-reference-dark-script">
(function(){
 function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn);else fn()}
 ready(function(){
   const norm=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
   const euro=v=>Number(v||0).toFixed(2).replace('.',',')+' €';
   const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

   const rail=document.querySelector('.pos-v3-rail');
   if(rail){
     const brand=rail.querySelector('.pos-v3-brand');if(brand)brand.innerHTML='<img class="pos-ref-logo" src="https://bechefaa.fr/logo-bechefaa.jpg" alt="BÉCHÉFAA"><div class="pos-ref-brandname">BÉCHÉFAA</div>';
     rail.querySelectorAll('.pos-v3-nav').forEach(x=>x.remove());
     const spacer=rail.querySelector('.pos-v3-rail-spacer')||document.createElement('div');spacer.className='pos-v3-rail-spacer';
     rail.appendChild(spacer);
     function a(href,icon,label,active){const el=document.createElement('a');el.className='pos-v3-nav'+(active?' active':'');el.href=href;el.innerHTML='<span>'+icon+'</span>'+label;return el}
     rail.insertBefore(a('/pos','＋','Nouvelle commande',true),spacer);
     const recent=document.querySelector('.pos-recent-orders-btn');if(recent){recent.className='pos-v3-nav pos-ref-recent';recent.innerHTML='<span>▤</span><span class="pos-ref-recent-label">Commandes</span>';rail.insertBefore(recent,spacer)}else rail.insertBefore(a('/historique','▤','Commandes',false),spacer);
     rail.insertBefore(a('/cuisine','♨','Cuisine',false),spacer);
     rail.insertBefore(a('/clients','♙','Clients',false),spacer);
     rail.appendChild(a('/administration','⚙','Paramètres',false));
   }

   const salle=document.querySelector('.ticket-choice [data-ticket="Salle"]'),emp=document.querySelector('.ticket-choice [data-ticket="Emporter"]'),liv=document.querySelector('.ticket-choice [data-ticket="Livraison"]');
   if(salle)salle.innerHTML='🍴&nbsp;&nbsp;SUR PLACE';if(emp)emp.innerHTML='🛍&nbsp;&nbsp;À EMPORTER';if(liv)liv.innerHTML='🛵&nbsp;&nbsp;LIVRAISON';

   const toolbar=document.querySelector('.pos-v3-toolbar'),main=document.querySelector('.main');
   const tablebar=document.createElement('div');tablebar.className='pos-ref-tablebar';tablebar.innerHTML=Array.from({length:9},(_,i)=>'<button type="button" data-ref-table="'+(i+1)+'">Table '+(i+1)+'</button>').join('');if(toolbar)toolbar.insertAdjacentElement('afterend',tablebar);
   function setMode(mode){const on=mode==='Salle';tablebar.classList.toggle('show',on);if(on)document.getElementById('p36-salle')?.click();else if(mode==='Emporter')document.getElementById('p36-emporter')?.click()}
   tablebar.addEventListener('click',e=>{const b=e.target.closest('[data-ref-table]');if(!b)return;const n=Number(b.dataset.refTable),legacy=document.querySelector('[data-p36-table="'+n+'"]');legacy?.click();tablebar.querySelectorAll('button').forEach(x=>x.classList.toggle('active',x===b))});
   document.addEventListener('click',e=>{const b=e.target.closest('.ticket-choice [data-ticket]');if(b)setMode(b.dataset.ticket)});setTimeout(()=>{const a=document.querySelector('.ticket-choice [data-ticket].active');setMode(a?a.dataset.ticket:'Salle')},150);

   function prune(){document.querySelectorAll('#cats .cat').forEach(b=>{const t=norm(b.textContent);if(t==='carte du soir'||t==='test v2')b.remove()});document.querySelectorAll('#grid .product').forEach(p=>{const t=norm(p.querySelector('.meta')?.textContent);if(t==='carte du soir'||t==='test v2')p.remove()})}
   prune();new MutationObserver(prune).observe(document.getElementById('cats'),{childList:true});new MutationObserver(prune).observe(document.getElementById('grid'),{childList:true});

   if(typeof showOptions==='function'&&!showOptions.__refWrapped){const o=showOptions;showOptions=function(){document.body.classList.remove('pos-ref-options-closed');return o.apply(this,arguments)};showOptions.__refWrapped=true}

   const upsell=document.createElement('div');upsell.className='pos-ref-upsell-overlay';upsell.innerHTML='<div class="pos-ref-modal"><h2>Un petit plus ?</h2><div class="pos-ref-upsell-list"></div><button type="button" class="pos-ref-no">Non merci</button></div>';document.body.appendChild(upsell);const ul=upsell.querySelector('.pos-ref-upsell-list');
   function suggestions(){try{if(!DATA||!ORDER||!ORDER.length)return[];const ids=new Set(ORDER.map(x=>String(x.product_id||'')));const cats=ORDER.map(x=>norm((DATA.items||[]).find(p=>String(p.id)===String(x.product_id))?.category));const targets=cats.some(c=>['burger','sandwich','assiette','nos formules midi'].includes(c))?['boissons','accompagnement','desserts']:['boissons','desserts','accompagnement'];const out=[];for(const t of targets){const p=(DATA.items||[]).find(x=>!ids.has(String(x.id||''))&&norm(x.category)===t);if(p)out.push(p);if(out.length===3)break}return out}catch(e){return[]}}
   function openUpsell(){const s=suggestions();if(!s.length)return;ul.innerHTML=s.map(p=>'<button type="button" class="pos-ref-upsell-item" data-up="'+esc(p.id)+'" data-name="'+esc(p.name)+'">'+(p.photo?'<img src="'+esc(p.photo)+'" alt="">':'')+'<b>'+esc(p.name)+'</b><span class="pos-ref-upsell-price">'+euro(p.price)+'</span></button>').join('');upsell.classList.add('open')}
   upsell.querySelector('.pos-ref-no').onclick=()=>upsell.classList.remove('open');upsell.addEventListener('click',e=>{if(e.target===upsell)upsell.classList.remove('open');const b=e.target.closest('[data-up]');if(b){upsell.classList.remove('open');showOptions?.(b.dataset.up,b.dataset.name)}});
   if(typeof addCurrent==='function'&&!addCurrent.__refWrapped){const o=addCurrent;addCurrent=function(){const n=ORDER.length,r=o.apply(this,arguments);if(ORDER.length>n){document.body.classList.add('pos-ref-options-closed');setTimeout(openUpsell,80)}return r};addCurrent.__refWrapped=true}

   const actions=document.createElement('div');actions.className='pos-ref-actions';actions.innerHTML='<button type="button" class="pos-ref-kitchen">👨‍🍳&nbsp;&nbsp;ENVOYER EN CUISINE</button><button type="button" class="pos-ref-pay">💳&nbsp;&nbsp;ENCAISSER</button>';document.querySelector('.cart')?.appendChild(actions);const kbtn=actions.querySelector('.pos-ref-kitchen'),pbtn=actions.querySelector('.pos-ref-pay');
   async function ensureSaved(cb){if(LAST_SAVED_ORDER&&LAST_SAVED_ORDER.id){cb(LAST_SAVED_ORDER);return}if(!ORDER.length){alert('Ajoutez au moins un produit à la commande.');return}const before=LAST_SAVED_ORDER&&LAST_SAVED_ORDER.id;saveOrder();let tries=0;const t=setInterval(()=>{tries++;if(LAST_SAVED_ORDER&&LAST_SAVED_ORDER.id&&LAST_SAVED_ORDER.id!==before){clearInterval(t);cb(LAST_SAVED_ORDER)}else if(tries>50){clearInterval(t);alert('Impossible de récupérer la commande enregistrée.')}},100)}
   kbtn.onclick=()=>ensureSaved(o=>sendKitchen?.(o.id,o.num));

   const pay=document.createElement('div');pay.className='pos-ref-pay-overlay';pay.innerHTML='<div class="pos-ref-modal"><h2>Encaisser</h2><div class="pos-ref-pay-total">0,00 €</div><div class="pos-ref-pay-methods"><button class="pos-ref-pay-method" data-m="ESPÈCES">💶 Espèces</button><button class="pos-ref-pay-method" data-m="CB">💳 CB</button><button class="pos-ref-pay-method" data-m="TITRE RESTAURANT">🍽 Titre resto</button></div><div class="pos-ref-field"><label>Montant</label><input class="pos-ref-amount" inputmode="decimal"></div><div class="pos-ref-field pos-ref-cash pos-ref-hidden"><label>Montant reçu</label><input class="pos-ref-received" inputmode="decimal"></div><div class="pos-ref-pay-error"></div><button class="pos-ref-pay-confirm">Valider l’encaissement</button><button class="pos-ref-cancel">Annuler</button></div>';document.body.appendChild(pay);let payId=null,method=null;const totalEl=pay.querySelector('.pos-ref-pay-total'),amount=pay.querySelector('.pos-ref-amount'),received=pay.querySelector('.pos-ref-received'),cash=pay.querySelector('.pos-ref-cash'),err=pay.querySelector('.pos-ref-pay-error');
   function closePay(){pay.classList.remove('open');method=null;pay.querySelectorAll('.pos-ref-pay-method').forEach(x=>x.classList.remove('active'));err.textContent=''}pay.querySelector('.pos-ref-cancel').onclick=closePay;pay.addEventListener('click',e=>{if(e.target===pay)closePay()});pay.querySelectorAll('.pos-ref-pay-method').forEach(b=>b.onclick=()=>{method=b.dataset.m;pay.querySelectorAll('.pos-ref-pay-method').forEach(x=>x.classList.toggle('active',x===b));cash.classList.toggle('pos-ref-hidden',method!=='ESPÈCES');if(method==='ESPÈCES')received.value=amount.value});
   async function openPay(o){payId=o.id;err.textContent='';try{const r=await fetch('/api/orders/'+encodeURIComponent(payId)+'/payment-phase41',{cache:'no-store'}),d=await r.json();if(!r.ok||!d.ok)throw new Error(d.error||'Encaissement indisponible');if(d.order.payment_status==='PAYÉE'){alert('Commande déjà encaissée.');return}const due=Number(d.order.total||0);totalEl.textContent=euro(due);amount.value=due.toFixed(2);received.value='';cash.classList.add('pos-ref-hidden');pay.classList.add('open')}catch(e){alert(e.message)}}
   pbtn.onclick=()=>ensureSaved(openPay);pay.querySelector('.pos-ref-pay-confirm').onclick=async()=>{if(!method){err.textContent='Choisissez un moyen de paiement.';return}const a=Number(String(amount.value).replace(',','.'));if(!Number.isFinite(a)||a<=0){err.textContent='Montant invalide.';return}const body={method,amount:a};if(method==='ESPÈCES'){const r=Number(String(received.value).replace(',','.'));if(!Number.isFinite(r)||r<a){err.textContent='Montant reçu insuffisant.';return}body.received=r}try{const r=await fetch('/api/orders/'+encodeURIComponent(payId)+'/payment-phase41',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),d=await r.json();if(!r.ok||!d.ok)throw new Error(d.error||'Encaissement impossible');closePay();alert(d.payment_status==='PAYÉE'?'Paiement enregistré.':'Paiement partiel enregistré. Reste : '+euro(d.remaining_amount))}catch(e){err.textContent=e.message}};
 })
})();
</script>
'''

    def pos_reference_view(*args, **kwargs):
        response = app.make_response(original(*args, **kwargs))
        try:
            if response.status_code == 200 and response.mimetype == "text/html":
                html = response.get_data(as_text=True)
                if "pos-reference-dark-style" not in html:
                    html = html.replace("</body>", addon + "</body>")
                    response.set_data(html)
                    response.content_length = len(response.get_data())
                response.headers["X-Bechefaa-POS-Reference"] = "dark-v2"
        except Exception:
            pass
        return response

    app.view_functions["pos"] = pos_reference_view
    app._bechefaa_pos_reference_dark = True
