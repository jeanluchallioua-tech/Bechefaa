document.addEventListener("DOMContentLoaded",()=>{
const $=x=>document.getElementById(x),euro=n=>n.toLocaleString("fr-FR",{style:"currency",currency:"EUR"});
let cat=window.CATEGORIES[0],ch="CAISSE",cart=[],sel=null,editingOrderId=null,editingOriginalItems=[],editingLineId=null,clients=JSON.parse(localStorage.getItem("b_clients043")||"[]"),orders=JSON.parse(localStorage.getItem("b_orders043")||"[]"),current=null,selections={};

const price=p=>["UBER EATS","DELIVEROO"].includes(ch)?+(p*1.15).toFixed(2):p;

/* V0.5.1 : passerelle publique utilisée par cloud.js.
   Elle permet au module Cloud d'accéder aux données qui restent
   volontairement encapsulées dans l'application principale. */
window.BECHEFAA_APP = {
  getOrders: () => orders,
  replaceOrders: (fresh) => {
    orders.length = 0;
    (fresh || []).forEach(o => orders.push(o));
    saveO();
    boards();
  },
  getClients: () => clients,
  replaceClients: (fresh) => {
    clients.length = 0;
    (fresh || []).forEach(c => clients.push(c));
    saveC();
    rClients();
  },
  newestOrder: () => orders[0] || null,
  newestClient: () => clients[0] || null,
  isEditingOrder: () => !!editingOrderId,
  refreshBoards: () => boards(),
  findOrder: (id) => orders.find(o => String(o.id) === String(id)) || null,
  getProducts: () => Array.isArray(window.PRODUCTS) ? window.PRODUCTS : [],
  getCatalogOptionsForProduct: (productOrId) => {
    const p = typeof productOrId === "object"
      ? productOrId
      : (window.PRODUCTS || []).find(x => String(x.id) === String(productOrId));
    if(!p) return [];
    const keys = profile(p);
    return keys.map(k => {
      const g = GROUPS[k];
      return g ? {
        key:k,
        title:g.title || k,
        required:!!g.required,
        max:Number(g.max ?? 1),
        choices:JSON.parse(JSON.stringify(g.choices || []))
      } : null;
    }).filter(Boolean);
  },
  updateLocalOrder: (id, patch) => {
    const o = orders.find(x => String(x.id) === String(id));
    if(!o) return null;
    Object.assign(o, patch); saveO(); boards(); return o;
  },
  beginEditOrder: (id) => {
    const o=orders.find(x=>String(x.id)===String(id));
    if(!o || !["À préparer","En préparation","Prête"].includes(o.status)) return false;
    editingOrderId=String(o.id);
    editingOriginalItems=JSON.parse(JSON.stringify(o.items||[]));
    cart=(o.items||[]).map(x=>({...JSON.parse(JSON.stringify(x)),lineId:x.lineId||Date.now()+Math.random()}));
    ch=o.source||"CAISSE";
    sel=o.customerId ? clients.find(c=>String(c.id)===String(o.customerId)) : null;
    if(!sel && o.customer && o.customer!=="Client comptoir"){
      sel={id:o.customerId||null,name:o.customer,phone:o.phone||"",email:o.email||"",address:o.address||"",postalCode:o.postalCode||"",city:o.city||""};
    }
    document.querySelectorAll(".channel").forEach(b=>b.classList.toggle("active",b.dataset.ch===ch));
    if(sel){
      $("selected").classList.remove("hidden");
      $("selected").innerHTML=`<div class="selected-client-title">✓ Client actif</div><b>${sel.name}</b><br>${sel.phone||""}${sel.address?`<br>${sel.address}`:""}`;
    }
    rCart(); rp();
    const v=$("validate"); if(v)v.textContent="ENREGISTRER ET RENVOYER EN CUISINE";
    let banner=$("editOrderBanner");
    if(!banner){
      banner=document.createElement("div"); banner.id="editOrderBanner"; banner.className="edit-order-banner";
      const ticket=document.querySelector(".ticket"); if(ticket)ticket.prepend(banner);
    }
    banner.textContent=`MODIFICATION COMMANDE #${o.num}`;
    document.querySelectorAll(".view").forEach(v=>v.classList.add("hidden"));
    $("pos").classList.remove("hidden");
    document.querySelectorAll(".nav").forEach(n=>n.classList.toggle("active",n.dataset.view==="pos"));
    window.scrollTo(0,0);
    return true;
  }
};


/* Choix issus du catalogue Wix Restaurants BÉCHÉFAA */
const GROUPS={
 cuisson:{title:"Cuisson",required:false,max:1,choices:[["Bleu",0],["Saignant",0],["À point",0],["Bien cuit",0]]},
 pain:{title:"Choix du pain",required:true,max:1,choices:[["Baguette",0],["Tacos",0],["Pita",0],["Pain kebab",0],["Laffa",3],["Pita panée",3.5],["Tacos pané",3.5]]},
 sauces:{title:"Sauces",required:false,max:3,choices:[["Ketchup",0],["Mayonnaise",0],["Barbecue",0],["Harissa maison",0],["Harissa-mayo",0],["Moutarde au miel",0],["Tartare",0],["Tehina",0],["Houmous",0],["Sauce américaine",0],["Sauce maison",0],["Sans sauces",0]]},
 supplements:{title:"Suppléments",required:false,max:0,choices:[["Avocat",2],["Bacon",3],["Cheddar",2],["Œuf",2],["Oignons crispy",2],["Plaque Cheddar",6.5],["Steak",6.5],["Frites Maison",5],["Pain noir",2]]},
 accompagnement:{title:"Choix d'accompagnement",required:false,max:1,choices:[["Frites",0],["Riz",0],["Pâtes sauce tomate",0],["Salades",0]]},
 poulet:{title:"Choix du poulet",required:true,max:1,choices:[["Poulet crispy",0],["Poulet grillé",0],["Poulet pané",0],["Poulet parguit",0]]},
 viande:{title:"Choix de la viande",required:true,max:1,choices:[["Parguit",0],["Poulet pané",0],["Poulet crispy",0],["Poulet grillé",0],["Shawarma",0],["Merguez",0],["Kebab",0],["Steak haché",0],["Falafel",0]]},
 tender:{title:"Type de tender",required:false,max:1,choices:[["Classic Panure traditionnelle Maison",0],["Crispy Panure extra croustillante Maison",0],["Cheesy tradition maison, cœur cheddar",1.5]]},
 garniture:{title:"Retirer / garniture",required:false,max:5,choices:[["Nature",0],["Sans salade verte",0],["Sans tomate",0],["Sans oignons rouges",0],["Sans oignons confits",0],["Sans cornichons",0],["Sans cheddar",0],["Sans avocat",0],["Sans œuf",0],["Sans aubergines",0],["Sans choux blanc",0],["Sans choux rouge",0],["Sans houmous",0],["Sans téhina",0]]},
 boisson:{title:"Boisson",required:false,max:1,choices:[["Coca Cola",0],["Coca zéro",0],["Ice Tea pêche",0],["Oasis Tropical",0],["Sprite",0],["Perrier",0],["Évian",0],["Schweppes agrumes",0]]}
};

/* Correspondances de groupes réellement lues sur Wix.
   Les profils exacts prennent priorité; les autres restent sur le profil V0.4.3
   jusqu'à validation de leur ID Wix individuel. */
const EXACT={
 "Smash Burger":["cuisson","garniture","supplements"],
 "Double smash Burger":["cuisson","garniture","supplements"],
 "Cheese Burger":["cuisson","garniture","supplements"],
 "Bacon Burger":["cuisson","garniture","supplements"],
 "Chicken/Crispy Burger":["garniture","supplements"],
 "Sandwich Poulet grillé / Pané / Crispy":["pain","poulet","supplements"],
 "Sandwich steak haché":["pain","cuisson","garniture","supplements"],
 "Assiette Falafel Maison":["garniture","sauces","accompagnement"],
 "Tornado Potato":["supplements"],
 "Frites Maison":["sauces"],
 'Classic Burger':["cuisson", "garniture", "supplements"],
 'Sandwich Fait ton sandwich':["pain", "viande", "garniture", "sauces", "supplements"],
 'Assiette Shawarma':["cuisson", "garniture", "sauces", "accompagnement"],
 'Assiette Entrecôte':["cuisson", "sauces", "accompagnement"],
 'Assiette Poulet pané / crispy':["sauces", "accompagnement"],
 'MENU Classic Burger':["garniture", "boisson", "supplements"],
 'MENU SMASH Burger':["garniture", "boisson", "supplements"],
 'MENU Cheese Burger':["garniture", "boisson", "supplements"],
 'MENU Oriental Burger':["garniture", "boisson", "supplements"],
 "MENU Bechefaa's Burger":["garniture", "boisson", "supplements"],
 'Menu sandwich Merguez':["pain", "sauces", "garniture", "boisson", "supplements"],
 'Menu sandwich Entrecôte':["pain", "sauces", "garniture", "boisson", "supplements"],
 'MENU KIDS':["garniture", "boisson"],
 'Tender Chicken Maison 10 pièces':["tender", "sauces"],
 'Oignons rings 8 pièces':["supplements", "sauces"]
};
const WIX_GROUP_IDS={
 "Smash Burger":["b6c0c948-f34d-4d73-97fa-d1be347392a2","57d28489-33f5-4c99-bcb8-0f25188996e6","8c93a125-f155-4a5d-9612-d2eaee2910b5","d76054c5-a0e0-49c6-b722-e205c9cf00ec"],
 "Double smash Burger":["b6c0c948-f34d-4d73-97fa-d1be347392a2","57d28489-33f5-4c99-bcb8-0f25188996e6","8c93a125-f155-4a5d-9612-d2eaee2910b5"],
 "Cheese Burger":["b6c0c948-f34d-4d73-97fa-d1be347392a2","b999bd51-2557-44dd-b698-3a84e822a6c4","b4b442fc-b30c-476c-8016-c6f1549461a6"],
 "Bacon Burger":["b6c0c948-f34d-4d73-97fa-d1be347392a2","767954a4-2452-48e0-9cf5-ee82f644779a","487a8fc3-5dfc-4ccf-a2b8-63d5f4eeaa0c"],
 "Chicken/Crispy Burger":["9dcd3bcd-fe4a-407a-9b73-ecfd22555007","bdea0dcc-4cef-4daf-9c9c-23f8c0ce60a2"],
 "Sandwich Poulet grillé / Pané / Crispy":["84131005-29ae-44ed-941e-bda0af0b1b09","3f955d38-1153-49d3-9670-531e236dc035","a2c259fe-d269-4476-992d-e5935d94b73a"],
 "Tornado Potato":["ef40ec0c-6ee9-4bc7-9eb8-10c0cbba4329"],
 'Sandwich steak haché':["84131005-29ae-44ed-941e-bda0af0b1b09", "b6c0c948-f34d-4d73-97fa-d1be347392a2", "36fedc15-44bf-4b15-a1a9-51272f634e45", "a2c259fe-d269-4476-992d-e5935d94b73a"],
 'Classic Burger':["b6c0c948-f34d-4d73-97fa-d1be347392a2", "5b3910be-c94e-4d5e-98cf-d2ccf0626cc7", "00dd0aba-4fa2-4607-a68d-c24f7f82cad7", "d76054c5-a0e0-49c6-b722-e205c9cf00ec"],
 'Sandwich Fait ton sandwich':["88fc4aab-405f-4fba-afa3-ecb89b8758a8", "62f0bb59-f7fd-4660-a85b-0309c7d0883f", "b6c0c948-f34d-4d73-97fa-d1be347392a2", "7060ff2d-c722-4263-85a2-e5f0db8d9062", "7354c89e-e8f3-4ef4-b077-f76235279fff"],
 'Assiette Shawarma':["b6c0c948-f34d-4d73-97fa-d1be347392a2", "fbcd38ec-67cc-453a-8ebc-3675bddfd2ab", "595fe8b6-82c0-4fd1-bd27-e4718e769463", "7caed328-827a-42e7-8ece-e5c3b722dfa0"],
 'Assiette Entrecôte':["830bf309-4bd1-452b-8e5c-f03fc12ac788", "95165190-8d9f-4b25-9406-cfddb758e540", "0476bfe5-e4be-4e27-96c7-7c53f9be94ea"],
 'Assiette Poulet pané / crispy':["830bf309-4bd1-452b-8e5c-f03fc12ac788", "95165190-8d9f-4b25-9406-cfddb758e540"],
 'MENU Classic Burger':["0476bfe5-e4be-4e27-96c7-7c53f9be94ea", "c223160c-67b2-496b-b9a2-67a95c7bda90", "586fbdf4-99f7-4fb9-bf51-0686c5cce8ea"],
 'MENU SMASH Burger':["0476bfe5-e4be-4e27-96c7-7c53f9be94ea", "4c1731a6-80d1-46d1-81fb-c7b83a0feedd", "586fbdf4-99f7-4fb9-bf51-0686c5cce8ea"],
 'MENU Cheese Burger':["0476bfe5-e4be-4e27-96c7-7c53f9be94ea", "4c1731a6-80d1-46d1-81fb-c7b83a0feedd", "586fbdf4-99f7-4fb9-bf51-0686c5cce8ea"],
 'MENU Oriental Burger':["0476bfe5-e4be-4e27-96c7-7c53f9be94ea", "4c1731a6-80d1-46d1-81fb-c7b83a0feedd", "586fbdf4-99f7-4fb9-bf51-0686c5cce8ea"],
 "MENU Bechefaa's Burger":["0476bfe5-e4be-4e27-96c7-7c53f9be94ea", "c223160c-67b2-496b-b9a2-67a95c7bda90", "586fbdf4-99f7-4fb9-bf51-0686c5cce8ea"],
 'Menu sandwich Merguez':["84131005-29ae-44ed-941e-bda0af0b1b09", "95165190-8d9f-4b25-9406-cfddb758e540", "0476bfe5-e4be-4e27-96c7-7c53f9be94ea", "c223160c-67b2-496b-b9a2-67a95c7bda90", "586fbdf4-99f7-4fb9-bf51-0686c5cce8ea"],
 'Menu sandwich Entrecôte':["84131005-29ae-44ed-941e-bda0af0b1b09", "95165190-8d9f-4b25-9406-cfddb758e540", "0476bfe5-e4be-4e27-96c7-7c53f9be94ea", "c223160c-67b2-496b-b9a2-67a95c7bda90", "586fbdf4-99f7-4fb9-bf51-0686c5cce8ea"],
 'MENU KIDS':["0476bfe5-e4be-4e27-96c7-7c53f9be94ea", "c223160c-67b2-496b-b9a2-67a95c7bda90"],
 'Tender Chicken Maison 10 pièces':["fd2d1e58-ff68-4353-8472-6658a6322bf2", "95165190-8d9f-4b25-9406-cfddb758e540"],
 'Oignons rings 8 pièces':["b146bf0e-e648-4879-bd8b-acbfe33d0edc", "95165190-8d9f-4b25-9406-cfddb758e540"]
};
function norm(s){return (s||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase().replace(/\s+/g," ").trim()}
function exactKey(p){
 const n=norm(p.name);
 return Object.keys(EXACT).find(k=>norm(k)===n) ||
        (n.includes("sandwich poulet") ? "Sandwich Poulet grillé / Pané / Crispy" :
         n.includes("fait ton sandwich") ? "Sandwich Fait ton sandwich" : null);
}
function profile(p){
 let ek=exactKey(p);
 if(ek)return EXACT[ek];
 let a=[],n=p.name.toLowerCase();
 if(p.cat==="Burger"){if(!n.includes("fish")&&!n.includes("chicken"))a.push("cuisson");a.push("garniture","supplements")}
 if(p.cat==="Sandwich"){if(!n.includes("hot-dog"))a.push("pain");a.push("garniture","sauces","supplements")}
 if(p.cat==="Assiette"){if(["entrecôte","merguez","mochy","shawarma","double steak"].some(x=>n.includes(x)))a.push("cuisson");a.push("sauces","accompagnement")}
 if(n.includes("poulet")||n.includes("chicken/crispy"))a.push("poulet");
 if(n.includes("pita pané")||n.includes("fait ton sandwich"))a.push("viande");
 if(n.includes("tender chicken"))a.push("tender");
 if(p.cat==="Nos formules MIDI"&&!n.includes("mochy"))a.push("boisson");
 if(n.includes("menu kids")||n.includes("formule enfant"))a.push("boisson");
 return [...new Set(a)];
}
function rc(){$("cats").innerHTML=window.CATEGORIES.map(c=>`<button data-c="${encodeURIComponent(c)}" class="${c===cat?"active":""}">${c}</button>`).join("");$("cats").querySelectorAll("button").forEach(b=>b.onclick=()=>{cat=decodeURIComponent(b.dataset.c);rc();rp()})}
function rp(){let l=window.PRODUCTS.filter(p=>p.cat===cat);$("products").innerHTML=l.map(p=>`<button class="product" data-id="${p.id}"><img src="${p.image}" alt=""><div class="pbody"><div class="pname">${p.name}</div><div class="price">${euro(price(p.price))}</div></div></button>`).join("");$("products").querySelectorAll(".product").forEach(b=>b.onclick=()=>openProduct(+b.dataset.id))}

function openExistingLineOptions(lineId){
 const line=cart.find(x=>String(x.lineId)===String(lineId));
 if(!line)return;
 current=window.PRODUCTS.find(x=>String(x.id)===String(line.id));
 if(!current)return alert("Produit introuvable.");
 editingLineId=String(line.lineId);
 selections=JSON.parse(JSON.stringify(line.options||{}));
 const prof=profile(current);
 if(!prof.length)return alert("Ce produit n'a pas d'options à modifier.");
 $("optTitle").textContent=`Modifier : ${current.name}`;
 $("optBase").textContent="Options actuelles";
 $("optionGroups").innerHTML=prof.map(k=>renderGroup(k)).join("");
 $("optionGroups").querySelectorAll(".optchoice").forEach(b=>{
   const k=b.dataset.g,n=decodeURIComponent(b.dataset.n);
   if((selections[k]||[]).some(x=>x.name===n))b.classList.add("selected");
   b.onclick=()=>toggleOption(b);
 });
 $("addConfigured").textContent="ENREGISTRER LES OPTIONS";
 $("optionModal").classList.remove("hidden");
 updateOptionTotal();
}
function openProduct(id){
 current=window.PRODUCTS.find(x=>x.id===id); selections={}; const prof=profile(current);
 if(!prof.length){addConfiguredDirect();return}
 $("optTitle").textContent=current.name;let ek=exactKey(current),ids=ek?WIX_GROUP_IDS[ek]:null;
 $("optBase").textContent=`${ch} · prix de base ${euro(price(current.price))}${ids?` · liaison Wix exacte (${ids.length} groupe${ids.length>1?"s":""})`:" · profil local en attente de liaison exacte"}`;
 $("optionGroups").innerHTML=prof.map(k=>renderGroup(k)).join("");
 $("optionGroups").querySelectorAll(".optchoice").forEach(b=>b.onclick=()=>toggleOption(b));
 $("optionModal").classList.remove("hidden");updateOptionTotal()
}
function renderGroup(k){
 const g=GROUPS[k],meta=[g.required?"Obligatoire":"Facultatif",g.max?`max. ${g.max}`:"plusieurs choix"].join(" · ");
 return `<div class="optgroup"><h3>${g.title}</h3><div class="optmeta">${meta}</div><div class="optchoices">${g.choices.map(([n,p])=>`<button class="optchoice" data-g="${k}" data-n="${encodeURIComponent(n)}" data-p="${p}">${n}${p?` +${euro(price(p))}`:""}</button>`).join("")}</div></div>`
}
function toggleOption(b){
 const k=b.dataset.g,g=GROUPS[k],name=decodeURIComponent(b.dataset.n),p=+b.dataset.p; selections[k]=selections[k]||[];
 let i=selections[k].findIndex(x=>x.name===name);
 if(i>=0){selections[k].splice(i,1);b.classList.remove("selected")}
 else{
   if(g.max===1){selections[k]=[];document.querySelectorAll(`[data-g="${k}"]`).forEach(x=>x.classList.remove("selected"))}
   else if(g.max&&selections[k].length>=g.max){alert(`Maximum ${g.max} choix.`);return}
   selections[k].push({name,price:p});b.classList.add("selected")
 }
 updateOptionTotal()
}
function optionExtra(){return Object.values(selections).flat().reduce((s,x)=>s+price(x.price),0)}
function updateOptionTotal(){$("optTotal").textContent=euro(price(current.price)+optionExtra())}
function validateRequired(){for(const k of profile(current)){if(GROUPS[k].required&&!(selections[k]?.length)){alert(`Choisissez : ${GROUPS[k].title}`);return false}}return true}

function optionText(o){
 const labels={garniture:"Retirer / garniture",supplements:"Suppléments",sauces:"Sauces",cuisson:"Cuisson",pain:"Pain",accompagnement:"Accompagnement",poulet:"Poulet",viande:"Viande",tender:"Tender",boisson:"Boisson"};
 return Object.entries(o||{}).filter(([,v])=>v.length).map(([k,v])=>`${labels[k]||GROUPS[k]?.title||k}::${v.map(x=>x.name).join("|")}`).join(";;");
}
function formatOptionHTML(txt){
 if(!txt)return "";
 const s=String(txt);
 // Format natif caisse : Groupe::choix|choix;;Groupe::choix
 if(s.includes("::") || s.includes(";;")){
   return s.split(";;").filter(Boolean).map(block=>{
     const [title,raw=""]=block.split("::");
     return `<div class="opt-display"><strong>${title} :</strong>${raw.split("|").filter(Boolean).map(x=>`<span>${x}</span>`).join("")}</div>`;
   }).join("");
 }
 // Format venant du site : Groupe: choix · Groupe: choix
 return s.split(/\s*[·•]\s*/).map(x=>x.trim()).filter(Boolean).map(block=>{
   const pos=block.indexOf(":");
   if(pos>0){
     const title=block.slice(0,pos).trim(), raw=block.slice(pos+1).trim();
     return `<div class="opt-display"><strong>${title} :</strong><span>${raw}</span></div>`;
   }
   return `<div class="opt-display"><span>${block}</span></div>`;
 }).join("");
}
function addConfiguredDirect(){let u=price(current.price),x=cart.find(i=>i.id===current.id&&!i.optionsText&&i.unit===u);x?x.qty++:cart.push({lineId:Date.now()+Math.random(),id:current.id,name:current.name,unit:u,qty:1,options:{},optionsText:""});rCart()}
function addConfigured(){
 if(!validateRequired())return;
 let opts=JSON.parse(JSON.stringify(selections)),txt=optionText(opts),u=price(current.price)+optionExtra(),ek=exactKey(current);
 if(editingLineId){
   const line=cart.find(x=>String(x.lineId)===String(editingLineId));
   if(line){line.unit=u;line.options=opts;line.optionsText=txt;line.wixModifierGroupIds=ek?(WIX_GROUP_IDS[ek]||[]):[]}
   editingLineId=null;
   $("addConfigured").textContent="AJOUTER À LA COMMANDE";
   $("optionModal").classList.add("hidden");rCart();return;
 }
 cart.push({lineId:Date.now()+Math.random(),id:current.id,name:current.name,unit:u,qty:1,options:opts,optionsText:txt,wixModifierGroupIds:ek?(WIX_GROUP_IDS[ek]||[]):[]});
 $("optionModal").classList.add("hidden");rCart();
}
function rCart(){$("cartItems").innerHTML=cart.length?cart.map(x=>`<div class="line"><div class="lineTop"><span><b>${x.qty}×</b> ${x.name}</span><b>${euro(x.qty*x.unit)}</b></div>${x.optionsText?`<div class="lineopts">${formatOptionHTML(x.optionsText)}</div>`:""}<div class="actions"><button data-dec="${x.lineId}">−</button><button data-inc="${x.lineId}">＋</button>${editingOrderId&&profile(window.PRODUCTS.find(p=>String(p.id)===String(x.id))||{}).length?`<button data-edit-options="${x.lineId}">Modifier options</button>`:""}<button class="danger" data-del="${x.lineId}">Supprimer</button></div></div>`).join(""):'<div class="empty">Commande vide</div>';$("total").textContent=euro(cart.reduce((s,x)=>s+x.qty*x.unit,0));document.querySelectorAll("[data-inc]").forEach(b=>b.onclick=()=>{let x=cart.find(x=>x.lineId==b.dataset.inc);x.qty++;rCart()});document.querySelectorAll("[data-dec]").forEach(b=>b.onclick=()=>{let x=cart.find(x=>x.lineId==b.dataset.dec);if(--x.qty<=0)cart=cart.filter(i=>i.lineId!=b.dataset.dec);rCart()});document.querySelectorAll("[data-del]").forEach(b=>b.onclick=()=>{cart=cart.filter(i=>i.lineId!=b.dataset.del);rCart()});document.querySelectorAll("[data-edit-options]").forEach(b=>b.onclick=()=>openExistingLineOptions(b.dataset.editOptions))}
function saveC(){localStorage.setItem("b_clients043",JSON.stringify(clients))}function saveO(){localStorage.setItem("b_orders043",JSON.stringify(orders))}
function find(q){q=q.toLowerCase().replace(/\s/g,"");return clients.filter(c=>c.name.toLowerCase().includes(q)||c.phone.replace(/\s/g,"").includes(q))}
$("cust").oninput=()=>{let q=$("cust").value.trim();$("matches").innerHTML=q?find(q).slice(0,5).map(c=>`<div class="match" data-cid="${c.id}"><b>${c.name}</b><br>${c.phone}</div>`).join(""):"";document.querySelectorAll("[data-cid]").forEach(e=>e.onclick=()=>pick(+e.dataset.cid))};function pick(id){
 sel=clients.find(c=>String(c.id)===String(id));
 if(!sel)return;
 $("selected").classList.remove("hidden");
 $("selected").innerHTML=`<div class="selected-client-title">✓ Client actif</div><b>${sel.name}</b><br>${sel.phone}${sel.email?`<br>${sel.email}`:""}${sel.address?`<br>${sel.address}`:""}${sel.postalCode||sel.city?`<br>${sel.postalCode||""} ${sel.city||""}`:""}`;
 $("matches").innerHTML="";
 $("cust").value="";
}
function rClients(q=""){let l=q?find(q):clients;$("clientList").innerHTML=l.map(c=>`<div class="clientrow" data-id="${c.id}"><b>${c.name}</b><br>${c.phone}</div>`).join("");document.querySelectorAll(".clientrow").forEach(e=>e.onclick=()=>{const id=+e.dataset.id;pick(id);detail(id)})}
function detail(id){
 let c=clients.find(x=>String(x.id)===String(id)),h=orders.filter(o=>String(o.customerId)===String(id));
 if(!c)return;
 $("clientDetail").innerHTML=`
   <div class="active-client-banner">✓ Client sélectionné pour la prochaine commande</div>
   <h2>${c.name}</h2>
   <p><b>Téléphone :</b> ${c.phone||""}</p>
   <p><b>Email :</b> ${c.email||""}</p>
   <p><b>Adresse :</b> ${c.address||""}</p>
   <p><b>Code postal / Ville :</b> ${c.postalCode||""} ${c.city||""}</p>
   <button id="useClientOrder" class="primary">Créer une commande pour ${c.name}</button>
   <h3>Historique (${h.length})</h3>
   ${h.map(o=>`<div class="line">#${o.num} · ${euro(o.total)}</div>`).join("")||"Aucune commande"}`;
 const b=$("useClientOrder");
 if(b)b.onclick=()=>{
   document.querySelectorAll(".view").forEach(v=>v.classList.add("hidden"));
   $("pos").classList.remove("hidden");
   document.querySelectorAll(".nav").forEach(n=>n.classList.toggle("active",n.dataset.view==="pos"));
   window.scrollTo(0,0);
 };
}
function move(id){
 let o=orders.find(x=>String(x.id)===String(id));if(!o)return;
 if(o.status==="À préparer")o.status="En préparation";
 else if(o.status==="En préparation")o.status="Prête";
 else if(o.status==="Prête")o.status=((o.source||"").toUpperCase()==="LIVRAISON"?"En livraison":"Terminée");
 else if(o.status==="En livraison")o.status="Terminée";
 saveO();boards();
}

function kitchenOptionsHtml(txt){
 if(!txt)return "";
 const parts=String(txt).split(/\s*[·•]\s*/).map(x=>x.trim()).filter(Boolean);
 return `<div class="kitchen-options-lines">${parts.map(p=>{
   const i=p.indexOf(":");
   if(i>0)return `<div><strong>${p.slice(0,i).trim()} :</strong> ${p.slice(i+1).trim()}</div>`;
   return `<div>${p}</div>`;
 }).join("")}</div>`;
}
function card(o){
 let n=o.status==="À préparer"?"DÉMARRER":o.status==="En préparation"?"PRÊTE":o.status==="Prête"?(((o.source||"").toUpperCase()==="LIVRAISON")?"EN LIVRAISON":"TERMINER"):o.status==="En livraison"?"LIVRÉE":"";
 return `<div class="order" data-order-id="${o.id}">
   <h3>#${o.num} · ${o.customer}</h3>
   <span class="badge">${o.source}</span> <span class="badge">${o.payment}</span>
   ${o.changeSummary&&(o.changeSummary.added?.length||o.changeSummary.removed?.length||o.changeSummary.modified?.length)?`
     <div class="change-summary">
       <strong>⚠ MODIFICATION</strong>
       ${(o.changeSummary.added||[]).map(x=>`<div class="change-added">AJOUTÉ : ${x}</div>`).join("")}
       ${(o.changeSummary.modified||[]).map(x=>`<div class="change-modified">MODIFIÉ : ${x}</div>`).join("")}
       ${(o.changeSummary.removed||[]).map(x=>`<div class="change-removed">SUPPRIMÉ : ${x}</div>`).join("")}
     </div>`:""}
   <ul>
     ${(o.items||[]).map((i,idx)=>`
       <li class="${i.prepared?"kitchen-done":""}" data-line-index="${idx}">
         <input type="checkbox" class="native-kcheck" data-korder="${o.id}" data-kindex="${idx}" ${i.prepared?"checked":""}>
         <div class="kitchen-item-content">
           <b>${i.qty}× ${i.name}</b>
           ${i.optionsText?`<div class="kitchen-options">${formatOptionHTML(i.optionsText)}</div>`:""}
         </div>
       </li>`).join("")}
   </ul>
   ${n?`<button data-m="${o.id}">${n}</button>`:""}
 </div>`;
}
function boards(){
 const k=["À préparer","En préparation","Prête"], all=["À préparer","En préparation","Prête","En livraison"];
 const build=ss=>ss.map(s=>`<div class="col"><h2>${s}</h2>${orders.filter(o=>o.status===s).map(card).join("")||'<div class="empty">Aucune</div>'}</div>`).join("");
 $("ordersBoard").innerHTML=build(all);$("kitchenBoard").innerHTML=build(k);
 document.querySelectorAll("[data-m]").forEach(b=>b.onclick=()=>move(+b.dataset.m));
 document.querySelectorAll(".native-kcheck").forEach(cb=>cb.onchange=async()=>{
   const oid=cb.dataset.korder,idx=+cb.dataset.kindex;cb.closest("li")?.classList.toggle("kitchen-done",cb.checked);
   const o=orders.find(x=>String(x.id)===String(oid));if(o?.items?.[idx]){o.items[idx].prepared=cb.checked;saveO()}
   try{await fetch(`/api/orders/${oid}/items/${idx}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({prepared:cb.checked})})}catch(e){}
 });
}
$("addConfigured").onclick=addConfigured;$("closeOptions").onclick=()=>$("optionModal").classList.add("hidden");
$("validate").onclick=async()=>{
 if(!cart.length)return alert("Ajoutez un produit.");
 let total=cart.reduce((s,x)=>s+x.qty*x.unit,0);

 if(editingOrderId){
   const o=orders.find(x=>String(x.id)===String(editingOrderId));
   if(!o)return alert("Commande introuvable.");
   const original=editingOriginalItems||[];
   const sig=x=>`${x.id}|${x.name}|${x.optionsText||""}|${x.unit}`;
   const oldMap=new Map(original.map(x=>[sig(x),x]));
   const newMap=new Map(cart.map(x=>[sig(x),x]));
   const added=[],removed=[],modified=[];
   for(const [k,x] of newMap){
     if(!oldMap.has(k)) added.push(`${x.qty}× ${x.name}`);
     else if((+oldMap.get(k).qty||0)!=(+x.qty||0)) modified.push(`${x.name} : ${oldMap.get(k).qty} → ${x.qty}`);
   }
   for(const [k,x] of oldMap) if(!newMap.has(k)) removed.push(`${x.qty}× ${x.name}`);
   const patch={
     customerId:sel?.id||o.customerId||null,
     customer:sel?.name||o.customer||"Client comptoir",
     phone:sel?.phone||o.phone||"",email:sel?.email||o.email||"",
     address:sel?.address||o.address||"",postalCode:sel?.postalCode||o.postalCode||"",
     city:sel?.city||o.city||"",source:ch,items:cart.map(x=>{
       const same=(editingOriginalItems||[]).find(o=>String(o.lineId)===String(x.lineId));
       return {...x,prepared:same?!!same.prepared:false};
     }),total,
     modificationFlag:true,modifiedAt:Date.now(),changeSummary:{added,removed,modified}
   };
   try{
     const r=await fetch(`/api/orders/${editingOrderId}/full`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(patch)});
     if(!r.ok){const t=await r.text();throw new Error(t||("HTTP "+r.status));}
     Object.assign(o,patch);
     saveO(); boards();
     const editedLocal=orders.find(x=>String(x.id)===String(editingOrderId));
     if(editedLocal){
       editedLocal.customerId=patch.customerId;
       editedLocal.customer=patch.customer;
       editedLocal.phone=patch.phone;
       editedLocal.email=patch.email;
       editedLocal.address=patch.address;
       editedLocal.postalCode=patch.postalCode;
       editedLocal.city=patch.city;
       editedLocal.items=JSON.parse(JSON.stringify(patch.items||[]));
       editedLocal.total=patch.total;
       editedLocal.changeSummary=patch.changeSummary;
       editedLocal.modificationFlag=true;
       editedLocal.modifiedAt=patch.modifiedAt;
       saveO();
       boards();
     }
     editingOrderId=null;editingOriginalItems=[];cart=[];sel=null;
     $("selected").classList.add("hidden");rCart();
     $("validate").textContent="ENVOYER EN CUISINE";
     document.getElementById("editOrderBanner")?.remove();
     await window.__bechefaaRefreshOrders?.(true);
     alert("Modifications enregistrées et renvoyées en cuisine.");
     return;
   }catch(e){alert("Erreur lors de l’enregistrement des modifications : "+(e?.message||"inconnue"));return}
 }

 let o={id:Date.now(),num:1000+orders.length+1,customerId:sel?.id||null,customer:sel?.name||"Client comptoir",phone:sel?.phone||"",email:sel?.email||"",address:sel?.address||"",postalCode:sel?.postalCode||"",city:sel?.city||"",source:ch,payment:ch==="WIX"?"PAYÉ EN LIGNE / STRIPE":ch==="CAISSE"?"À ENCAISSER":"PAYÉ PLATEFORME",status:"À préparer",items:cart.map(x=>({...x})),total};
 orders.unshift(o);saveO();cart=[];sel=null;$("selected").classList.add("hidden");rCart();boards();alert("Commande envoyée en cuisine.");
 document.body.style.overflow="";document.documentElement.style.overflow="";
 document.querySelectorAll(".modal").forEach(m=>m.classList.add("hidden"));
 const posView=document.getElementById("pos");if(posView)posView.scrollTop=0;
};$("clear").onclick=()=>{if(cart.length&&confirm("Vider toute la commande ?")){cart=[];rCart()}};$("fullscreen").onclick=()=>document.documentElement.requestFullscreen?.();
document.querySelectorAll(".channel").forEach(b=>b.onclick=()=>{document.querySelectorAll(".channel").forEach(x=>x.classList.remove("active"));b.classList.add("active");ch=b.dataset.ch;rp()});document.querySelectorAll(".nav").forEach(b=>b.onclick=()=>{document.querySelectorAll(".nav").forEach(x=>x.classList.remove("active"));b.classList.add("active");document.querySelectorAll(".view").forEach(v=>v.classList.add("hidden"));$(b.dataset.view).classList.remove("hidden");if(b.dataset.view==="clients")rClients();if(["orders","kitchen"].includes(b.dataset.view))boards()});
$("newClient").onclick=()=>$("clientModal").classList.remove("hidden");$("closeClient").onclick=()=>$("clientModal").classList.add("hidden");$("saveClient").onclick=()=>{
 const name=$("cname").value.trim();
 const firstName=$("cfirstname")?.value.trim()||"";
 const phone=$("cphone").value.trim();
 const email=$("cemail")?.value.trim()||"";
 const address=$("caddress").value.trim();
 const postalCode=$("cpostal")?.value.trim()||"";
 const city=$("ccity")?.value.trim()||"";
 if(!name||!phone)return alert("Nom et téléphone requis.");
 const fullName=(name+" "+firstName).trim();
 const c={id:Date.now(),name:fullName,lastName:name,firstName,phone,email,address,postalCode,city};
 clients.unshift(c);saveC();rClients();
 $("clientModal").classList.add("hidden");
 ["cname","cfirstname","cphone","cemail","caddress","cpostal","ccity"].forEach(id=>{const e=$(id);if(e)e.value=""});
};

/* V0.5.10 : rendu initial du catalogue restauré */
rc();
rp();
rCart();
rClients();
boards();

});

/* V0.5.2 : navigation tablette toujours disponible */
(function(){
  function ensureTabletNav(){
    if(document.getElementById("tabletQuickNav")) return;
    const nav=document.createElement("div");
    nav.id="tabletQuickNav";
    nav.innerHTML=`
      <button type="button" data-qview="pos">Caisse</button>
      <button type="button" data-qview="orders">Commandes</button>
      <button type="button" data-qview="kitchen">Cuisine</button>
      <button type="button" data-qview="clients">Clients</button><button type="button" data-qview="history">Historique</button>
    `;
    document.body.appendChild(nav);
    nav.addEventListener("click",e=>{
      const b=e.target.closest("[data-qview]");
      if(!b)return;
      const id=b.dataset.qview;
      document.querySelectorAll(".view").forEach(v=>v.classList.add("hidden"));
      const target=document.getElementById(id);
      if(target) target.classList.remove("hidden");
      document.body.style.overflow="";
      document.documentElement.style.overflow="";
      window.scrollTo({top:0,behavior:"smooth"});
      if(id==="kitchen" && typeof boards==="function") boards();
      if(id==="orders" && typeof boards==="function") boards();
      if(id==="clients" && typeof rClients==="function") rClients();
    });
  }
  window.addEventListener("load", ensureTabletNav);
})();


/* === V0.5.8 : navigation robuste === */
window.addEventListener("load",()=>{
  document.addEventListener("click",e=>{
    const b=e.target.closest("[data-view]");
    if(!b)return;
    const id=b.dataset.view;
    const target=document.getElementById(id);
    if(!target)return;

    e.preventDefault();
    document.querySelectorAll(".view").forEach(v=>v.classList.add("hidden"));
    target.classList.remove("hidden");

    document.querySelectorAll(".nav").forEach(n=>n.classList.remove("active"));
    b.classList.add("active");

    document.body.style.overflow="";
    document.documentElement.style.overflow="";
    window.scrollTo(0,0);

    if(id==="clients" && typeof rClients==="function") rClients();
    if((id==="orders" || id==="kitchen") && typeof boards==="function") boards();
    if(id==="history") setTimeout(()=>window.BECHEFAA_V055?.renderHistory?.(),0);
  },true);
});


/* === V0.5.9 : purge anciens caches hors connexion === */
window.addEventListener("load", async ()=>{
  try{
    if("caches" in window){
      const keys=await caches.keys();
      await Promise.all(keys.filter(k=>k!=="bechefaa-v059").map(k=>caches.delete(k)));
    }
    if("serviceWorker" in navigator){
      const regs=await navigator.serviceWorker.getRegistrations();
      for(const r of regs){
        try{ await r.update(); }catch(e){}
      }
    }
  }catch(e){}
});


/* === V0.5.27 CLEAN : Catalogue central — étape 1 isolée === */
(() => {
 const KEY="bechefaa_catalog_admin_v1";
 const $=id=>document.getElementById(id);
 const baseCats=["Nos formules MIDI","Entrées","Salades","Burger","Assiette","Sandwich","Suppléments","Accompagnement","Boissons","Desserts","Carte du soir"];
 function loadState(){
   try{const x=JSON.parse(localStorage.getItem(KEY));if(x&&Array.isArray(x.categories)&&Array.isArray(x.products))return x}catch(e){}
   const existing=(Array.isArray(window.PRODUCTS)?window.PRODUCTS:[]);
   const cats=[...new Set([...baseCats,...existing.map(p=>p.cat).filter(Boolean)])].map((name,i)=>({id:"c"+i,name,active:true}));
   return {categories:cats,products:existing.map((p,i)=>({
     id:String(p.id??("p"+i)),name:p.name||"Produit",category:p.cat||"",price:Number(p.price??p.unit??0),
     active:true,photo:"",ingredients:"",channels:{caisse:true,site:true,ubereats:false,deliveroo:false},
     schedule:"toujours"
   }))};
 }
 let state=loadState();
 async function save(){
   localStorage.setItem(KEY,JSON.stringify(state));
   try{
     const r=await fetch("/api/catalog-admin",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({data:state})});
     if(!r.ok) throw new Error(await r.text());
     const st=document.getElementById("catalogSaveStatus"); if(st)st.textContent="✓ Sauvegardé dans la base centrale";
   }catch(e){
     const st=document.getElementById("catalogSaveStatus"); if(st)st.textContent="⚠ Copie locale uniquement";
     console.error(e);
   }
 }
 async function loadCentralState(){
   try{
     const r=await fetch("/api/catalog-admin?t="+Date.now(),{cache:"no-store"});
     if(!r.ok)return;
     const j=await r.json();
     if(j.data&&Array.isArray(j.data.categories)&&Array.isArray(j.data.products)){
       state=j.data;localStorage.setItem(KEY,JSON.stringify(state));
     }else await save();
   }catch(e){console.warn("Catalogue central indisponible",e)}
 }
 const euro=n=>Number(n||0).toLocaleString("fr-FR",{style:"currency",currency:"EUR"});
 function render(){
   if(!$("catCategories"))return;
   $("catCategories").innerHTML=state.categories.map(c=>`<div class="catalog-row"><div><b>${c.name}</b><small>${c.active?"Active":"Masquée"}</small></div><button data-edit-cat="${c.id}">Modifier</button></div>`).join("");
   $("catFilter").innerHTML='<option value="">Toutes les catégories</option>'+state.categories.map(c=>`<option value="${c.name}">${c.name}</option>`).join("");
   const q=($("catSearch").value||"").toLowerCase(), f=$("catFilter").value;
   const list=state.products.filter(p=>(!q||p.name.toLowerCase().includes(q))&&(!f||p.category===f));
   $("catProducts").innerHTML=list.length?list.map(p=>`<div class="catalog-product-row">
      <div class="catalog-thumb">${p.photo?`<img src="${p.photo}" alt="">`:"📷"}</div>
      <div class="catalog-product-main"><b>${p.name}</b><small>${p.category||"Sans catégorie"} · ${euro(p.price)}</small>
      <div class="catalog-chips">${p.channels.caisse?"<span>Caisse</span>":""}${p.channels.site?"<span>Site</span>":""}${p.channels.ubereats?"<span>Uber</span>":""}${p.channels.deliveroo?"<span>Deliveroo</span>":""}</div></div>
      <button data-edit-prod="${p.id}">Modifier</button></div>`).join(""):"<p>Aucun produit.</p>";
   document.querySelectorAll("[data-edit-prod]").forEach(b=>b.onclick=()=>productForm(state.products.find(p=>p.id===b.dataset.editProd)));
   document.querySelectorAll("[data-edit-cat]").forEach(b=>b.onclick=()=>categoryForm(state.categories.find(c=>c.id===b.dataset.editCat)));
 }
 function open(title,body){$("catalogModalTitle").textContent=title;$("catalogModalBody").innerHTML=body;$("catalogModal").classList.remove("hidden")}
 function close(){$("catalogModal").classList.add("hidden")}
 function categoryForm(c){
   const isNew=!c;c=c||{id:"c"+Date.now(),name:"",active:true};
   open(isNew?"Nouvelle catégorie":"Modifier la catégorie",`<label>Nom<input id="cfName" value="${c.name}"></label>
   <label class="checkline"><input id="cfActive" type="checkbox" ${c.active?"checked":""}> Catégorie active</label>
   <button id="cfSave" class="catalog-save">Enregistrer</button>`);
   $("cfSave").onclick=()=>{c.name=$("cfName").value.trim();c.active=$("cfActive").checked;if(!c.name)return alert("Nom obligatoire");if(isNew)state.categories.push(c);save();close();render()};
 }
 function productForm(p){
   const isNew=!p;p=p||{id:"p"+Date.now(),name:"",category:state.categories[0]?.name||"",price:0,active:true,photo:"",ingredients:"",channels:{caisse:true,site:true,ubereats:false,deliveroo:false},schedule:"toujours"};
   open(isNew?"Nouveau produit":"Modifier le produit",`
   <label>Nom<input id="pfName" value="${p.name||""}"></label>
   <label>Catégorie<select id="pfCat">${state.categories.map(c=>`<option ${c.name===p.category?"selected":""}>${c.name}</option>`).join("")}</select></label>
   <label>Prix TTC (€)<input id="pfPrice" type="number" step="0.01" value="${p.price||0}"></label>
   <label>Photo / URL<input id="pfPhoto" value="${p.photo||""}" placeholder="Photo du produit"></label>
   <label>Ingrédients / composition<textarea id="pfIngredients">${p.ingredients||""}</textarea></label>
   <label>Disponibilité<select id="pfSchedule"><option value="toujours" ${p.schedule==="toujours"?"selected":""}>Toujours</option><option value="midi" ${p.schedule==="midi"?"selected":""}>Midi</option><option value="soir" ${p.schedule==="soir"?"selected":""}>Soir</option></select></label>
   <div class="catalog-options-editor">
    <div class="catalog-options-title"><b>Options du produit</b><div><button type="button" id="pfAddOptionGroup">+ Groupe</button><button type="button" id="pfReloadOptions">↻ Reprendre caisse</button></div></div>
    <div id="pfOptionsList"></div>
   </div>
   <div class="catalog-channel-form"><b>Publier sur :</b>
    <label><input id="chCaisse" type="checkbox" ${p.channels.caisse?"checked":""}> Caisse</label>
    <label><input id="chSite" type="checkbox" ${p.channels.site?"checked":""}> Site</label>
    <label><input id="chUber" type="checkbox" ${p.channels.ubereats?"checked":""}> Uber Eats</label>
    <label><input id="chDeliveroo" type="checkbox" ${p.channels.deliveroo?"checked":""}> Deliveroo</label>
   </div>
   <label class="checkline"><input id="pfActive" type="checkbox" ${p.active?"checked":""}> Produit actif</label>
   <button id="pfSave" class="catalog-save">Enregistrer</button>`);
   function renderPfOptions(){
     p.options=Array.isArray(p.options)?p.options:[];
     $("pfOptionsList").innerHTML=p.options.length?p.options.map((g,gi)=>`
      <div class="catalog-option-admin-group">
       <div class="catalog-option-fields">
        <label>Groupe<input data-og-title="${gi}" value="${String(g.title||g.key||"Options").replace(/"/g,"&quot;")}"></label>
        <label>Type<select data-og-required="${gi}"><option value="0" ${!g.required?"selected":""}>Facultatif</option><option value="1" ${g.required?"selected":""}>Obligatoire</option></select></label>
        <label>Max<input data-og-max="${gi}" type="number" min="0" value="${Number(g.max??1)}"></label>
        <button type="button" data-og-delete="${gi}">Supprimer</button>
       </div>
       <div>${(g.choices||[]).map((c,ci)=>{const n=Array.isArray(c)?c[0]:(c.name||c.label||"Option"),pr=Number(Array.isArray(c)?c[1]||0:c.price||c.extra||0);return `<div class="catalog-choice-edit"><input data-cn="${gi}:${ci}" value="${String(n).replace(/"/g,"&quot;")}"><input data-cp="${gi}:${ci}" type="number" step="0.01" value="${pr}"><button type="button" data-cd="${gi}:${ci}">×</button></div>`}).join("")}</div>
       <button type="button" data-ca="${gi}">+ Choix</button>
      </div>`).join(""):`<p>Aucune option. Cliquez sur « + Groupe ».</p>`;
     bindOptionEditor();
   }
   function captureOptions(){
    (p.options||[]).forEach((g,gi)=>{
     g.title=document.querySelector(`[data-og-title="${gi}"]`)?.value.trim()||"Options";
     g.key=g.key||("custom_"+Date.now()+"_"+gi);
     g.required=document.querySelector(`[data-og-required="${gi}"]`)?.value==="1";
     g.max=Math.max(0,Number(document.querySelector(`[data-og-max="${gi}"]`)?.value||0));
     g.choices=(g.choices||[]).map((c,ci)=>[document.querySelector(`[data-cn="${gi}:${ci}"]`)?.value.trim()||"Option",Number(document.querySelector(`[data-cp="${gi}:${ci}"]`)?.value||0)]);
    });
   }
   function bindOptionEditor(){
    document.querySelectorAll("[data-og-delete]").forEach(b=>b.onclick=()=>{captureOptions();p.options.splice(+b.dataset.ogDelete,1);renderPfOptions()});
    document.querySelectorAll("[data-ca]").forEach(b=>b.onclick=()=>{captureOptions();p.options[+b.dataset.ca].choices.push(["Nouveau choix",0]);renderPfOptions()});
    document.querySelectorAll("[data-cd]").forEach(b=>b.onclick=()=>{captureOptions();let [g,c]=b.dataset.cd.split(":").map(Number);p.options[g].choices.splice(c,1);renderPfOptions()});
   }
   renderPfOptions();
   $("pfAddOptionGroup").onclick=()=>{captureOptions();p.options.push({key:"custom_"+Date.now(),title:"Nouveau groupe",required:false,max:1,choices:[]});renderPfOptions()};
   $("pfReloadOptions").onclick=()=>{
     const bridge=window.BECHEFAA_APP;
     const liveProducts=bridge?.getProducts?.() || [];
     const live=liveProducts.find(x=>String(x.id)===String(p.id)) ||
                liveProducts.find(x=>normCatalogName(x.name)===normCatalogName(p.name));
     if(!live)return alert("Produit introuvable dans la carte caisse.");
     p.options=bridge?.getCatalogOptionsForProduct?.(live) || [];
     renderPfOptions();
   };
   $("pfSave").onclick=()=>{captureOptions();p.name=$("pfName").value.trim();p.category=$("pfCat").value;p.price=Number($("pfPrice").value||0);p.photo=$("pfPhoto").value.trim();p.ingredients=$("pfIngredients").value.trim();p.schedule=$("pfSchedule").value;p.active=$("pfActive").checked;
   p.channels={caisse:$("chCaisse").checked,site:$("chSite").checked,ubereats:$("chUber").checked,deliveroo:$("chDeliveroo").checked};if(!p.name)return alert("Nom obligatoire");if(isNew)state.products.push(p);save();close();render()};
 }

 function importExistingPosCatalog(){
   const existing=(Array.isArray(window.PRODUCTS)?window.PRODUCTS:[]);
   if(!existing.length){alert("Aucun produit de la carte actuelle n'a été trouvé.");return}
   let added=0,updated=0;
   const ensureCat=name=>{
     name=(name||"Sans catégorie").trim();
     let c=state.categories.find(x=>x.name===name);
     if(!c){c={id:"c"+Date.now()+Math.random().toString(36).slice(2),name,active:true};state.categories.push(c)}
     return name;
   };
   existing.forEach((p,i)=>{
     const id=String(p.id??("legacy-"+i));
     const name=String(p.name||p.label||"Produit").trim();
     const category=ensureCat(p.cat||p.category||"Sans catégorie");
     const price=Number(p.price??p.unit??p.unitPrice??0);
     const found=state.products.find(x=>String(x.id)===id) ||
                 state.products.find(x=>x.name===name && x.category===category);
     const options=window.BECHEFAA_APP?.getCatalogOptionsForProduct?.(p) || [];
     const base={
       id,name,category,price,active:p.active!==false,
       photo:p.image||p.photo||p.imageUrl||"",
       ingredients:p.ingredients||p.description||"",
       options,
       channels:{caisse:true,site:true,ubereats:false,deliveroo:false},
       schedule:p.schedule||"toujours"
     };
     if(found){
       // Preserve admin choices already made, but enrich missing legacy data.
       found.name=name;found.category=category;found.price=price;
       if(!found.photo)found.photo=base.photo;
       if(!found.ingredients)found.ingredients=base.ingredients;
       if(!found.options||!found.options.length)found.options=options;
       updated++;
     }else{state.products.push(base);added++}
   });
   save().then(()=>{render();alert(`Import terminé : ${added} produit(s) ajouté(s), ${updated} produit(s) mis à jour. Les produits existants conservent leurs réglages de diffusion.`)});
 }



 function normCatalogName(v){
   return String(v||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"")
     .toLowerCase().replace(/['’]/g,"").replace(/[^a-z0-9]+/g," ").trim();
 }

 async function syncAllCatalogOptions(){
   const bridge=window.BECHEFAA_APP;
   const live=bridge?.getProducts?.() || [];
   if(!live.length)return alert("La carte caisse n'est pas disponible.");
   let matched=0,withOptions=0,withoutOptions=0,unmatched=[];
   for(const lp of live){
     let target=state.products.find(x=>String(x.id)===String(lp.id));
     if(!target)target=state.products.find(x=>normCatalogName(x.name)===normCatalogName(lp.name));
     if(!target){unmatched.push(lp.name);continue}
     matched++;
     const groups=bridge?.getCatalogOptionsForProduct?.(lp) || [];
     target.options=groups;
     if(groups.length)withOptions++; else withoutOptions++;
   }
   await save();
   render();
   let msg=`Options synchronisées : ${matched} produits trouvés, ${withOptions} avec options, ${withoutOptions} sans options.`;
   if(unmatched.length)msg+=`\n${unmatched.length} produit(s) non associé(s).`;
   alert(msg);
 }

 window.addEventListener("load",async()=>{
   await loadCentralState();
   $("catSyncOptions")?.addEventListener("click",syncAllCatalogOptions);
   $("catImportExisting")?.addEventListener("click",importExistingPosCatalog);
   $("catNewCategory")?.addEventListener("click",()=>categoryForm());
   $("catNewProduct")?.addEventListener("click",()=>productForm());
   $("catalogModalClose")?.addEventListener("click",close);
   $("catSearch")?.addEventListener("input",render);
   $("catFilter")?.addEventListener("change",render);
   render();
 });
})();
