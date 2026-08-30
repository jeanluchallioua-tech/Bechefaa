(() => {

  /* V0.5.37 — notification persistante des nouvelles commandes du site */
  let knownOrderIds=null;
  const seenKey="bechefaa_site_seen_orders_v0537";
  const seenOrders=()=>new Set(JSON.parse(localStorage.getItem(seenKey)||"[]").map(String));
  const saveSeen=s=>localStorage.setItem(seenKey,JSON.stringify([...s].slice(-200)));
  function ringSiteOrder(){
    try{navigator.vibrate?.([180,100,180]);}catch(e){}
    try{
      const AC=window.AudioContext||window.webkitAudioContext;
      if(AC){
        const ac=new AC();
        [880,1100,880].forEach((f,i)=>{
          const o=ac.createOscillator(),g=ac.createGain();
          o.connect(g);g.connect(ac.destination);o.frequency.value=f;g.gain.value=.12;
          o.start(ac.currentTime+i*.22);o.stop(ac.currentTime+i*.22+.16);
        });
      }
    }catch(e){}
  }
  function showSiteOrderAlert(o){
    const box=document.getElementById("siteOrderAlert"),txt=document.getElementById("siteOrderAlertText");
    if(!box||!txt)return;
    box.dataset.orderId=String(o.id);
    txt.textContent=`#${o.num||""} · ${o.customer||"Client"} · ${Number(o.total||0).toFixed(2)} €`;
    box.classList.remove("hidden");
    ringSiteOrder();
    try{
      if(Notification.permission==="granted") new Notification("Nouvelle commande BÉCHÉFAA",{body:txt.textContent});
    }catch(e){}
  }
  window.BECHEFAA_NOTIFY_ORDERS=(fresh)=>{
    if(!Array.isArray(fresh))return;
    const ids=new Set(fresh.map(o=>String(o.id)));
    const seen=seenOrders();
    const site=fresh.filter(o=>String(o.id).startsWith("SITE-"));
    if(knownOrderIds===null){
      knownOrderIds=ids;
      const recent=site.find(o=>!seen.has(String(o.id)) && (Date.now()-Number(o.createdAt||0)<10*60*1000));
      if(recent)showSiteOrderAlert(recent);
      return;
    }
    const newcomers=site.filter(o=>!knownOrderIds.has(String(o.id))&&!seen.has(String(o.id)));
    knownOrderIds=ids;
    if(newcomers.length)showSiteOrderAlert(newcomers[0]);
  };
  window.addEventListener("load",()=>{
    document.getElementById("siteOrderAlertAck")?.addEventListener("click",()=>{
      const box=document.getElementById("siteOrderAlert"); if(!box)return;
      const id=box.dataset.orderId; const s=seenOrders(); if(id)s.add(String(id)); saveSeen(s);
      box.classList.add("hidden");
    });
  });

  const MODE = location.pathname.replaceAll("/","").toLowerCase() || "caisse";
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => [...document.querySelectorAll(s)];
  const bridge = () => window.BECHEFAA_APP;

  async function api(path, options={}) {
    const res = await fetch(path, {
      headers: {"Content-Type":"application/json", ...(options.headers||{})},
      ...options
    });
    if(!res.ok) throw new Error(await res.text());
    return res.status === 204 ? null : res.json();
  }


  /* V0.5.38 — contrôle autonome des commandes SITE pour la notification */
  let lastSitePollIds=new Set();
  let sitePollBooted=false;
  async function pollSiteOrdersForAlert(){
    try{
      const fresh=await api("/api/orders");
      if(!Array.isArray(fresh))return;
      const site=fresh.filter(o=>String(o.id).startsWith("SITE-"));
      const seen=seenOrders();
      if(!sitePollBooted){
        lastSitePollIds=new Set(site.map(o=>String(o.id)));
        sitePollBooted=true;
        const recent=site.find(o=>!seen.has(String(o.id)) && Date.now()-Number(o.createdAt||0)<5*60*1000);
        if(recent)showSiteOrderAlert(recent);
        return;
      }
      const n=site.find(o=>!lastSitePollIds.has(String(o.id))&&!seen.has(String(o.id)));
      lastSitePollIds=new Set(site.map(o=>String(o.id)));
      if(n)showSiteOrderAlert(n);
    }catch(e){console.error("BÉCHÉFAA site-order alert poll:",e)}
  }

  async function refreshOrders(){
    try{
      const fresh=await api("/api/orders");
      const app=bridge();
      if(app && Array.isArray(fresh)){
        const local=app.getOrders();
        local.splice(0,local.length,...fresh);
        localStorage.setItem("bechefaa_orders",JSON.stringify(local));
        app.renderBoards();
        window.BECHEFAA_NOTIFY_ORDERS?.(fresh);
      }
      renderHistory();
      enhanceKitchenChecks();
    }catch(e){console.error("BÉCHÉFAA refreshOrders:",e)}
  }

  async function refreshClients() {
    try {
      const fresh = await api("/api/clients");
      if(Array.isArray(fresh) && bridge()) {
        bridge().replaceClients(fresh);
      }
    } catch(e) {
      console.error("BÉCHÉFAA clients sync:", e);
    }
  }

  function modeUI() {
    const brand = $(".brand small");
    if(brand) brand.textContent = "POS V0.5.38 CLEAN · " + MODE.toUpperCase();

    if(MODE === "cuisine") {
      $$(".nav").forEach(b => b.classList.add("hidden")); /* barre rapide tablette reste disponible */
      $$(".view").forEach(v => v.classList.add("hidden"));
      const k = $("#kitchen");
      if(k) k.classList.remove("hidden");
      document.body.classList.add("mode-kitchen");
    } else if(MODE === "salle") {
      const source = $$('.channel[data-ch="CAISSE"]')[0];
      if(source) source.textContent = "Salle";
      document.body.classList.add("mode-salle");
    } else {
      document.body.classList.add("mode-caisse");
    }
  }

  function installCloudHooks() {
    const validate = $("#validate");
    if(validate) {
      validate.addEventListener("click", () => {
        /* V0.5.24 CLEAN :
           Une modification est déjà sauvegardée par PATCH /api/orders/<id>/full.
           Ne surtout pas lancer ensuite le POST générique de création, sinon
           l'ancienne version de la commande réécrit items_json. */
        if(bridge()?.isEditingOrder?.()) return;

        setTimeout(async () => {
          try {
            const o = bridge()?.newestOrder();
            if(!o) return;
            const payload = JSON.parse(JSON.stringify(o));
            if(MODE === "salle") payload.source = "SALLE";
            await api("/api/orders", {
              method:"POST",
              body:JSON.stringify(payload)
            });
            await refreshOrders();
          } catch(e) {
            console.error("BÉCHÉFAA create order:", e);
          }
        }, 100);
      });
    }

    const saveClient = $("#saveClient");
    if(saveClient) {
      saveClient.addEventListener("click", () => {
        setTimeout(async () => {
          try {
            const c = bridge()?.newestClient();
            if(!c) return;
            await api("/api/clients", {
              method:"POST",
              body:JSON.stringify(c)
            });
            await refreshClients();
          } catch(e) {
            console.error("BÉCHÉFAA create client:", e);
          }
        }, 100);
      });
    }

    document.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-m]");
      if(!b) return;

      /* V0.5.4 : le changement de colonne cuisine est géré ici,
         avant le onclick historique d'app.js. */
      e.preventDefault();
      e.stopPropagation();
      if(typeof e.stopImmediatePropagation === "function") e.stopImmediatePropagation();

      const id = b.dataset.m;
      const o = bridge()?.findOrder(id);
      if(!o) return;

      const next =
        o.status === "À préparer" ? "En préparation" :
        o.status === "En préparation" ? "Prête" :
        o.status === "Prête" ? (((o.source||"").toUpperCase()==="LIVRAISON") ? "En livraison" : "Terminée") :
        o.status === "En livraison" ? "Terminée" : o.status;

      b.disabled = true;
      const oldLabel = b.textContent;
      b.textContent = "…";

      /* Retour visuel immédiat sur tablette */
      o.status = next;
      bridge()?.refreshBoards();
      enhanceKitchenChecks();

      try {
        await api(`/api/orders/${id}`, {
          method:"PATCH",
          body:JSON.stringify({status:next})
        });
        await refreshOrders();
      } catch(err) {
        console.error("BÉCHÉFAA status sync:", err);
        await refreshOrders();
        alert("La commande n'a pas pu changer de statut. Vérifiez la connexion.");
      } finally {
        b.disabled = false;
        b.textContent = oldLabel;
      }
    }, true);
  }

  function enhanceKitchenChecks() {
    const root = $("#kitchenBoard");
    const app = bridge();
    if(!root || !app) return;

    root.querySelectorAll(".order").forEach(card => {
      const orderId = card.dataset.orderId || card.querySelector("[data-m]")?.dataset.m;
      if(!orderId) return;

      const order = app.findOrder(orderId);
      if(!order) return;

      const rows = [...card.querySelectorAll("li")];
      rows.forEach((li, i) => {
        let cb = li.querySelector(".native-kcheck") || li.querySelector(".cloud-kcheck");
        if(!cb) {
          cb = document.createElement("input");
          cb.type = "checkbox";
          cb.className = "cloud-kcheck";
          cb.setAttribute("aria-label", `Article ${i+1} préparé`);
          li.prepend(cb);

          cb.addEventListener("change", async () => {
            li.classList.toggle("kitchen-done", cb.checked);
            updateKitchenProgress(card);
            try {
              await api(`/api/orders/${orderId}/items/${i}`, {
                method:"PATCH",
                body:JSON.stringify({prepared:cb.checked})
              });
              await refreshOrders();
            } catch(e) {
              console.error("BÉCHÉFAA kitchen item:", e);
            }
          });
        }
        cb.checked = !!order.items?.[i]?.prepared;
        li.classList.toggle("kitchen-done", cb.checked);
      });

      updateKitchenProgress(card);
    });
  }

  function updateKitchenProgress(card) {
    const checks = [...card.querySelectorAll(".cloud-kcheck")];
    if(!checks.length) return;

    let p = card.querySelector(".cloud-progress");
    if(!p) {
      p = document.createElement("div");
      p.className = "cloud-progress";
      card.appendChild(p);
    }

    const done = checks.filter(x => x.checked).length;
    const ready = done === checks.length;
    p.textContent = ready
      ? `✓ COMMANDE PRÊTE · ${done}/${checks.length}`
      : `Préparation · ${done}/${checks.length}`;
    card.classList.toggle("kitchen-ready", ready);
  }

  window.__bechefaaRefreshOrders=refreshOrders;

  window.addEventListener("load", async () => {
    modeUI();
    installCloudHooks();

    let tries = 0;
    while(!bridge() && tries < 40) {
      await new Promise(r => setTimeout(r, 50));
      tries++;
    }

    await Promise.all([refreshOrders(), refreshClients()]);
    enhanceKitchenChecks();
    await pollSiteOrdersForAlert();
    setInterval(pollSiteOrdersForAlert,1500);
    document.addEventListener("pointerdown",()=>{
      try{if("Notification" in window && Notification.permission==="default") Notification.requestPermission().catch(()=>{});}catch(e){}
    },{once:true});
    // V0.5.3: pas de MutationObserver sur kitchenBoard.
    // Il créait une boucle de rendu sur tablette et finissait par figer l’interface.
setInterval(refreshOrders, 2500);
  });
})();

/* === V0.5.5 HISTORIQUE / MODIFICATION / TICKETS === */
(() => {
 const $x=s=>document.querySelector(s);
 let editingId=null;
 const bridge=()=>window.BECHEFAA_APP;
 const money=n=>Number(n||0).toLocaleString("fr-FR",{style:"currency",currency:"EUR"});
 async function apiX(path,opt={}){
   const r=await fetch(path,{headers:{"Content-Type":"application/json",...(opt.headers||{})},...opt});
   if(!r.ok)throw new Error(await r.text());
   return r.status===204?null:r.json();
 }
 function fmt(txt){
   if(!txt)return "";
   return txt.split(";;").filter(Boolean).map(b=>{
     const [t,r=""]=b.split("::");
     return `<div class="opt-display"><strong>${t} :</strong>${r.split("|").filter(Boolean).map(x=>`<span>${x}</span>`).join("")}</div>`;
   }).join("");
 }
 function editable(o){return ["À préparer","En préparation","Prête"].includes(o?.status);}
 function renderHistory(){
   const root=$x("#historyList"); if(!root||!bridge())return;
   const q=($x("#historySearch")?.value||"").toLowerCase();
   const st=$x("#historyStatus")?.value||"";
   const list=[...bridge().getOrders()].filter(o=>{
     if(st&&o.status!==st)return false;
     const hay=[o.num,o.customer,o.phone,o.status,o.source].join(" ").toLowerCase();
     return !q||hay.includes(q);
   });
   root.innerHTML=list.length?list.map(o=>`
    <div class="history-card">
      <div class="history-head">
        <div>
      <strong>#${o.num||o.id} · ${o.customer||"Client comptoir"}</strong>
      <div class="sub">${o.status} · ${o.source||""} · ${money(o.total)} ${o.modificationFlag?`· <strong>MODIFIÉE</strong>`:""}</div>
      ${o.phone?`<div class="history-client-detail">📞 ${o.phone}</div>`:""}
      ${o.email?`<div class="history-client-detail">✉ ${o.email}</div>`:""}
      ${o.address?`<div class="history-client-detail">📍 ${o.address}${o.postalCode||o.city?`, ${o.postalCode||""} ${o.city||""}`:""}</div>`:""}
    </div>
        <div class="history-actions">
          <button data-view-order="${o.id}">Voir</button>
          ${editable(o)?`<button data-edit-order="${o.id}">Modifier</button>`:""}
          <button data-print-counter="${o.id}">Ticket comptoir</button>
          <button data-print-delivery="${o.id}">Ticket livraison</button>
        </div>
      </div>
    </div>`).join(""):'<div class="empty">Aucune commande</div>';
 }
 function openOrder(id,edit){
   const o=bridge()?.findOrder(id); if(!o)return;
   editingId=String(id);
   $x("#orderModalTitle").textContent=`Commande #${o.num||o.id}`;
   $x("#orderModalMeta").textContent=`${o.customer||"Client comptoir"} · ${o.status}`;
   const can=edit&&editable(o);
   $x("#saveOrderEdit").style.display=can?"":"none";
   $x("#orderEditBody").innerHTML=`
    <div class="edit-client-grid">
      <label>Client<input id="editCustomer" value="${o.customer||""}" ${can?"":"disabled"}></label>
      <label>Téléphone<input id="editPhone" value="${o.phone||""}" ${can?"":"disabled"}></label><label>Email<input id="editEmail" value="${o.email||""}" ${can?"":"disabled"}></label>
      <label>Adresse<input id="editAddress" value="${o.address||""}" ${can?"":"disabled"}></label>
      <label>Code postal<input id="editPostal" value="${o.postalCode||""}" ${can?"":"disabled"}></label>
      <label>Ville<input id="editCity" value="${o.city||""}" ${can?"":"disabled"}></label>
      <label>Type<select id="editSource" ${can?"":"disabled"}>
        ${["CAISSE","SALLE","SUR PLACE","À EMPORTER","LIVRAISON","WIX","UBER EATS","DELIVEROO"].map(x=>`<option ${o.source===x?"selected":""}>${x}</option>`).join("")}
      </select></label>
    </div>
    <h3>Articles</h3>
    ${(o.items||[]).map((i,idx)=>`
      <div class="edit-item" data-edit-index="${idx}">
        <div class="edit-item-main">
          <input class="edit-qty" type="number" min="0" value="${i.qty||1}" ${can?"":"disabled"}>
          <div><strong>${i.name}</strong>${fmt(i.optionsText)}</div>
          <strong>${money((i.unit||0)*(i.qty||1))}</strong>
        </div>
        ${can?`<button class="danger" data-remove-edit="${idx}">Supprimer</button>`:""}
      </div>`).join("")}`;
   $x("#orderModal").classList.remove("hidden");
 }
 async function saveEdit(){
   const o=bridge()?.findOrder(editingId); if(!o||!editable(o))return;
   const rows=[...document.querySelectorAll("[data-edit-index]")];
   const items=rows.map(r=>{
     const idx=+r.dataset.editIndex, x={...(o.items[idx]||{})};
     x.qty=Math.max(0,+r.querySelector(".edit-qty").value||0); return x;
   }).filter(x=>x.qty>0);
   const patch={
     customer:$x("#editCustomer").value.trim()||"Client comptoir",
     phone:$x("#editPhone").value.trim(),
     email:$x("#editEmail")?.value.trim()||"",
     address:$x("#editAddress").value.trim(),
     postalCode:$x("#editPostal").value.trim(),
     city:$x("#editCity").value.trim(),
     source:$x("#editSource").value,
     items,
     total:items.reduce((s,i)=>s+(+i.unit||0)*(+i.qty||0),0),
     modificationFlag:true,modifiedAt:Date.now()
   };
   await apiX(`/api/orders/${editingId}/full`,{method:"PATCH",body:JSON.stringify(patch)});
   $x("#orderModal").classList.add("hidden");
   await window.__bechefaaRefreshOrders?.();
   renderHistory();
 }
 async function printLatestOrder(id,delivery=false){
    try{
      const fresh=await api("/api/orders");
      const o=(fresh||[]).find(x=>String(x.id)===String(id));
      if(o)return ticket(o,delivery);
    }catch(e){}
    const o=bridge()?.findOrder?.(id);
    if(o)return ticket(o,delivery);
    alert("Commande introuvable.");
  }

  async function printAuthoritativeOrder(id,delivery=false){
    try{
      const o=await api(`/api/orders/${id}?t=${Date.now()}`);
      if(!o || !Array.isArray(o.items))throw new Error("Commande invalide");
      return ticket(o,delivery);
    }catch(e){
      console.error("BÉCHÉFAA impression:",e);
      alert("Impossible de charger la dernière version de la commande pour l'impression.");
    }
  }

  function ticket(o,delivery){
   const customerName=o.customer||"Client comptoir";
   const clientBlock=delivery
    ? `<section class="customer-block">
         <div class="customer-name">${customerName}</div>
         ${o.phone?`<div><b>Tél :</b> ${o.phone}</div>`:""}
         ${o.email?`<div><b>Email :</b> ${o.email}</div>`:""}
         ${o.address?`<div><b>Adresse :</b> ${o.address}</div>`:""}
         ${(o.postalCode||o.city)?`<div><b>CP / Ville :</b> ${o.postalCode||""} ${o.city||""}</div>`:""}
       </section>`
    : `<section class="customer-block compact">
         <div class="customer-name">${customerName}</div>
       </section>`;

   const items=(o.items||[]).map(i=>`
     <div class="item">
       <div class="item-main">
         <span class="qty">${i.qty}×</span>
         <span class="item-name">${i.name}</span>
         <span class="item-price">${money((i.unit||0)*(i.qty||0))}</span>
       </div>
       ${i.optionsText?`<div class="item-options">${fmt(i.optionsText)}</div>`:""}
     </div>`).join("");

   const mode=delivery?"LIVRAISON":"COMPTOIR / EMPORTER";

   const html=`<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Commande #${o.num||o.id}</title>
<style>
  @page{size:80mm auto;margin:2.5mm}
  *{box-sizing:border-box}
  html,body{margin:0;padding:0;background:#fff}
  body{
    width:75mm;
    margin:0 auto;
    padding:1.5mm 1mm 4mm;
    font-family:Arial,Helvetica,sans-serif;
    font-size:11.5pt;
    line-height:1.25;
    color:#000;
  }
  .brand{text-align:center;font-size:18pt;font-weight:900;letter-spacing:.5px;margin-bottom:1mm}
  .mode{text-align:center;font-size:11pt;font-weight:900;border-top:1.5px solid #000;border-bottom:1.5px solid #000;padding:1.5mm 0;margin-bottom:2mm}
  .order-number{text-align:center;font-size:20pt;font-weight:900;margin:1.5mm 0 2mm}
  .customer-block{font-size:11pt;margin-bottom:2mm}
  .customer-block.compact{margin-bottom:1.5mm}
  .customer-name{font-size:14pt;font-weight:900;margin-bottom:1mm}
  .sep{border-top:1px dashed #000;margin:2mm 0}
  .item{padding:1.3mm 0;border-bottom:1px dotted #777}
  .item-main{display:grid;grid-template-columns:9mm 1fr auto;gap:1.5mm;align-items:start}
  .qty{font-weight:900}
  .item-name{font-weight:900}
  .item-price{font-weight:900;text-align:right;white-space:nowrap}
  .item-options{font-size:10pt;margin:1mm 0 0 10.5mm}
  .opt-display{margin:.8mm 0}
  .opt-display strong{display:block;font-weight:900}
  .opt-display span{display:block;margin-left:2mm}
  .total{
    display:flex;justify-content:space-between;
    font-size:17pt;font-weight:900;
    border-top:2px solid #000;border-bottom:2px solid #000;
    padding:2mm 0;margin-top:2.5mm
  }
  .footer{text-align:center;font-size:9pt;margin-top:3mm}
  @media print{
    body{width:75mm}
    button{display:none!important}
  }
</style>
</head>
<body>
  <div class="brand">BÉCHÉFAA</div>
  <div class="mode">${mode}</div>
  <div class="order-number">N° ${o.num||o.id}</div>
  ${clientBlock}
  <div class="sep"></div>
  ${items}
  <div class="total"><span>TOTAL</span><span>${money(o.total)}</span></div>
  <div class="footer">Merci</div>
<script>
window.onload=()=>{setTimeout(()=>window.print(),150)};
<\/script>
</body>
</html>`;

   const w=window.open("","_blank","width=480,height=760");
   if(!w){alert("Autorisez les fenêtres pop-up pour imprimer.");return;}
   w.document.open();
   w.document.write(html);
   w.document.close();
 }
 function printOrder(id,delivery){
   const o=bridge()?.findOrder(id); if(!o)return;
   const w=window.open("","_blank","width=480,height=700");
   if(!w){alert("Autorisez les pop-up pour imprimer.");return;}
   w.document.write(ticket(o,delivery));w.document.close();
 }
 document.addEventListener("click",e=>{
   let b=e.target.closest("[data-view-order]");if(b){openOrder(b.dataset.viewOrder,false);return}
   b=e.target.closest("[data-edit-order]");if(b){$x("#orderModal")?.classList.add("hidden");bridge()?.beginEditOrder?.(b.dataset.editOrder);return}
   b=e.target.closest("[data-print-counter]");if(b){printOrder(b.dataset.printCounter,false);return}
   b=e.target.closest("[data-print-delivery]");if(b){printOrder(b.dataset.printDelivery,true);return}
   b=e.target.closest("[data-remove-edit]");if(b){b.closest("[data-edit-index]")?.remove();return}
   b=e.target.closest('[data-view="history"],[data-qview="history"]');if(b)setTimeout(renderHistory,0);
 });
 window.addEventListener("load",()=>{
   $x("#historySearch")?.addEventListener("input",renderHistory);
   $x("#historyStatus")?.addEventListener("change",renderHistory);
   $x("#closeOrderModal")?.addEventListener("click",()=> $x("#orderModal").classList.add("hidden"));
   $x("#saveOrderEdit")?.addEventListener("click",saveEdit);
   $x("#printCounter")?.addEventListener("click",()=>printOrder(editingId,false));
   $x("#printDelivery")?.addEventListener("click",()=>printOrder(editingId,true));
 });
 window.BECHEFAA_V055={renderHistory};
})();

/* === V0.5.6 CLIENT CP/VILLE + TICKETS === */
(() => {
 const byId=id=>document.getElementById(id);
 async function fillCityFromPostal(){
   const cp=(byId("cpostal")?.value||"").replace(/\D/g,"").slice(0,5);
   if(byId("cpostal")) byId("cpostal").value=cp;
   if(cp.length!==5) return;
   try{
     const r=await fetch("https://geo.api.gouv.fr/communes?codePostal="+encodeURIComponent(cp)+"&fields=nom,codesPostaux&format=json&geometry=centre");
     if(!r.ok) return;
     const towns=await r.json();
     const names=[...new Set((towns||[]).map(x=>x.nom).filter(Boolean))].sort();
     const city=byId("ccity"); if(!city||!names.length)return;
     city.value=names[0];
     let dl=byId("cityChoices");
     if(!dl){dl=document.createElement("datalist");dl.id="cityChoices";document.body.appendChild(dl);city.setAttribute("list","cityChoices");}
     dl.innerHTML=names.map(n=>`<option value="${n}"></option>`).join("");
   }catch(e){}
 }
 window.addEventListener("load",()=>{
   const cp=byId("cpostal");
   if(cp){cp.addEventListener("input",()=>{if(cp.value.replace(/\D/g,"").length===5)fillCityFromPostal()});cp.addEventListener("blur",fillCityFromPostal);}
 });
})();

/* === V0.5.7 : fiche client complète + CP -> Ville === */
(() => {
  const byId=id=>document.getElementById(id);
  let cpTimer=null;
  async function lookupCity(){
    const cp=(byId("cpostal")?.value||"").replace(/\D/g,"").slice(0,5);
    if(byId("cpostal")) byId("cpostal").value=cp;
    if(cp.length!==5)return;
    const city=byId("ccity"), dl=byId("cityChoices");
    if(!city||!dl)return;
    city.placeholder="Recherche de la ville…";
    try{
      const r=await fetch("https://geo.api.gouv.fr/communes?codePostal="+encodeURIComponent(cp)+"&fields=nom,codesPostaux&format=json&geometry=centre");
      if(!r.ok)throw new Error("lookup");
      const data=await r.json();
      const names=[...new Set((data||[]).map(x=>x.nom).filter(Boolean))].sort((a,b)=>a.localeCompare(b,"fr"));
      dl.innerHTML=names.map(n=>`<option value="${n}"></option>`).join("");
      if(names.length===1) city.value=names[0];
      else if(names.length>1 && !city.value) city.value=names[0];
      city.placeholder="Ville";
    }catch(e){
      city.placeholder="Ville";
    }
  }
  window.addEventListener("load",()=>{
    const cp=byId("cpostal");
    if(!cp)return;
    cp.addEventListener("input",()=>{
      clearTimeout(cpTimer);
      cpTimer=setTimeout(()=>{if(cp.value.replace(/\D/g,"").length===5)lookupCity()},250);
    });
    cp.addEventListener("blur",lookupCity);
  });
})();


/* === V0.5.25 CLEAN : notifications multicanales === */
(() => {
  const seen = new Set();
  let initialized = false;
  let pendingCount = 0;
  let audioCtx = null;

  const $n = id => document.getElementById(id);

  function normalizedSource(o){
    const s=String(o?.source||"").toUpperCase();
    if(s.includes("UBER")) return "UBER EATS";
    if(s.includes("DELIVER")) return "DELIVEROO";
    if(s.includes("WIX") || s.includes("SITE")) return "SITE / WIX";
    return s || "CAISSE";
  }

  function sourceIcon(source){
    if(source==="UBER EATS") return "🟢";
    if(source==="DELIVEROO") return "🔵";
    if(source==="SITE / WIX") return "🌐";
    return "🧾";
  }

  function sourceTone(source){
    if(!audioCtx) audioCtx = new (window.AudioContext||window.webkitAudioContext)();
    const ctx=audioCtx;
    const now=ctx.currentTime;
    const freqs = source==="UBER EATS" ? [880,1040] :
                  source==="DELIVEROO" ? [660,880] :
                  source==="SITE / WIX" ? [520,780] : [440,660];
    freqs.forEach((f,i)=>{
      const osc=ctx.createOscillator();
      const gain=ctx.createGain();
      osc.frequency.value=f;
      osc.type="sine";
      gain.gain.setValueAtTime(0.0001, now+i*0.16);
      gain.gain.exponentialRampToValueAtTime(0.18, now+i*0.16+0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now+i*0.16+0.14);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now+i*0.16);
      osc.stop(now+i*0.16+0.15);
    });
  }

  function updateBadge(){
    const b=$n("ordersNavBadge");
    const side=$n("orderNotificationBadge");
    [b,side].forEach(el=>{
      if(!el) return;
      el.textContent=String(pendingCount);
      el.classList.toggle("hidden",pendingCount<=0);
    });
  }

  function showToast(o){
    const host=$n("orderToastHost") || document.body;
    const source=normalizedSource(o);
    const el=document.createElement("div");
    el.className="order-arrival-toast";
    el.innerHTML=`
      <div class="toast-source">${sourceIcon(source)} ${source}</div>
      <div class="toast-title">Nouvelle commande #${o.num||o.id}</div>
      <div class="toast-customer">${o.customer||"Client comptoir"}</div>
      <div class="toast-total">${Number(o.total||0).toLocaleString("fr-FR",{style:"currency",currency:"EUR"})}</div>
      <button type="button">Voir la commande</button>`;
    el.querySelector("button").onclick=()=>{
      document.querySelector('[data-view="orders"]')?.click();
      pendingCount=Math.max(0,pendingCount-1);
      updateBadge();
      el.remove();
    };
    host.appendChild(el);
    setTimeout(()=>el.remove(),12000);
  }

  function browserNotify(o){
    if(!("Notification" in window) || Notification.permission!=="granted") return;
    const source=normalizedSource(o);
    try{
      new Notification(`Nouvelle commande ${source}`,{
        body:`#${o.num||o.id} · ${o.customer||"Client comptoir"} · ${Number(o.total||0).toLocaleString("fr-FR",{style:"currency",currency:"EUR"})}`,
        tag:`bechefaa-order-${o.id}`
      });
    }catch(e){}
  }

  function announce(o){
    const source=normalizedSource(o);
    pendingCount++;
    updateBadge();
    showToast(o);
    try{ sourceTone(source); }catch(e){}
    browserNotify(o);
  }

  window.BECHEFAA_NOTIFY_ORDERS = (orders) => {
    if(!Array.isArray(orders)) return;
    if(!initialized){
      orders.forEach(o=>seen.add(String(o.id)));
      initialized=true;
      return;
    }
    const fresh=[];
    orders.forEach(o=>{
      const id=String(o.id);
      if(!seen.has(id)){
        seen.add(id);
        fresh.push(o);
      }
    });
    fresh.reverse().forEach(announce);
  };

  window.addEventListener("load",()=>{
    const btn=$n("enableNotifications");
    if(btn){
      const syncLabel=()=>{
        if(!("Notification" in window)){
          btn.textContent="🔕 Notifications navigateur indisponibles";
          btn.disabled=true;
        }else if(Notification.permission==="granted"){
          btn.textContent="🔔 Notifications activées";
          btn.classList.add("enabled");
        }else if(Notification.permission==="denied"){
          btn.textContent="🔕 Notifications bloquées";
        }
      };
      syncLabel();
      btn.addEventListener("click",async()=>{
        try{
          if("Notification" in window){
            const p=await Notification.requestPermission();
            if(audioCtx && audioCtx.state==="suspended") await audioCtx.resume();
            else if(!audioCtx) audioCtx=new (window.AudioContext||window.webkitAudioContext)();
            syncLabel();
            if(p==="granted"){
              btn.textContent="🔔 Notifications activées";
            }
          }
        }catch(e){}
      });
    }

    document.querySelector('[data-view="orders"]')?.addEventListener("click",()=>{
      pendingCount=0;
      updateBadge();
    });
  });
})();
