(() => {
  const $ = id => document.getElementById(id);
  const clone = x => JSON.parse(JSON.stringify(x));
  const API = '/api/v2/catalog';
  let state = null;

  const baseDefs = {
    garnitures:{label:'Garnitures / ingrédients retirables',title:'Retirer garniture',max:30,required:false,fixed:false,priceMode:'extra',seed:[['Salade verte',0],['Tomate',0],['Oignons rouges',0],['Oignons confits',0],['Cornichons',0],['Cheddar',0],['Avocat',0],['Œuf',0],['Aubergines',0],['Salade israélienne',0],['Choux blanc',0],['Choux rouge',0],['Houmous',0],['Tehina',0],['Harissa',0],['Ketchup',0],['Mayonnaise',0],['Moutarde',0],['Sauce maison',0],['Sauce barbecue',0],['Sauce tartare',0],['Sauce harissa-mayo',0],['Moutarde au miel',0]]},
    supplements:{label:'Suppléments',title:'Suppléments',max:0,required:false,fixed:false,priceMode:'extra',seed:[['Avocat',2],['Bacon',3],['Cheddar',2],['Œuf',2],['Oignons crispy',2],['Plaque Cheddar',6.5],['Steak 150 g',6.5],['Frites Maison',5],['Pita',3.5],['Pita panée',6.5],['Piment',2],['Demi-baguette',1.5],['Bassar',3],['Bassar shawarma',3]]},
    sauces:{label:'Sauces',title:'Sauces',max:3,required:false,fixed:false,priceMode:'extra',seed:[['Ketchup',0],['Mayonnaise',0],['Barbecue',0],['Harissa maison',0],['Harissa-mayo',0],['Moutarde',0],['Moutarde au miel',0],['Tartare',0],['Tehina',0],['Houmous',0],['Sauce américaine',0],['Sauce maison',0],['Sauce blanche à l’ail maison',0],['Sauce chili douce',0],['Sans sauces',0]]},
    saucesSupp:{label:'Sauces supplémentaires',title:'Choix des sauces supplémentaire',max:3,required:false,fixed:false,priceMode:'extra',seed:[['Barbecue',1],['Harissa',1],['Houmous',1]]},
    cuisson:{label:'Cuisson',title:'Cuisson',max:1,required:false,fixed:true,priceMode:'extra',seed:[['Bleu',0],['Saignant',0],['À point',0],['Bien cuit',0]]},
    pain:{label:'Pains',title:'Choix du pain',max:1,required:false,fixed:false,priceMode:'extra',seed:[['Baguette',0],['Tacos',0],['Pita',0],['Pain kebab',0],['Laffa',3],['Pita panée',3.5],['Tacos pané',3.5]]},
    boissons:{label:'Boissons',title:'Boisson',max:1,required:false,fixed:false,priceMode:'extra',seed:[['Coca Cola',0],['Coca zéro',0],['Ice Tea pêche',0],['Oasis Tropical',0],['Sprite',0],['Perrier',0],['Évian',0],['Schweppes agrumes',0],['Caprisun',0],['Boisson autre que Caprisun',1.5]]},
    accompagnements:{label:'Accompagnements',title:'Accompagnement',max:1,required:false,fixed:false,priceMode:'extra',seed:[['Frites',0],['Pate sauce tomate',0],['Riz',0],['Mini salade',0]]},
    viandes:{label:'Viandes',title:'Choix des viandes',max:1,required:false,fixed:false,priceMode:'extra',seed:[['Parguit',0],['Poulet pané',0],['Poulet crispy',0],['Poulet grillé',0],['Shawarma',0],['Merguez',0],['Kebab',0],['Steak',0],['Falafel',0]]},
    poulet:{label:'Choix du poulet',title:'Choix du poulet',max:1,required:false,fixed:false,priceMode:'extra',seed:[['Poulet crispy',0],['Poulet grillé',0],['Poulet pané',0],['Poulet parguit',0]]},
    tender:{label:'Type de tender',title:'Type de tender',max:1,required:false,fixed:false,priceMode:'extra',seed:[['Classic Panure traditionnelle Maison',0],['Crispy Panure extra croustillante Maison',0],['Cheesy tradition maison, cœur cheddar',1.5]]}
  };

  const norm = s => String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
  const esc = s => String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
  const safeKey = s => String(s||'').replace(/[^a-zA-Z0-9_-]/g,'_');
  const defs = () => ({...baseDefs,...(state?.optionListDefs||{})});

  function orderMode(k){ return state.optionListOrderModes?.[k] || (k==='cuisson' ? 'manual' : 'alpha'); }
  function normalizeManualOrder(k){
    state.optionListOrders=state.optionListOrders||{};
    const len=(state.optionLists[k]||[]).length;
    const valid=new Set(Array.from({length:len},(_,i)=>i));
    const saved=Array.isArray(state.optionListOrders[k])?state.optionListOrders[k]:[];
    const out=saved.filter(i=>Number.isInteger(i)&&valid.has(i));
    for(let i=0;i<len;i++) if(!out.includes(i)) out.push(i);
    state.optionListOrders[k]=out;
    return out;
  }
  function visibleEntries(k){
    const entries=(state.optionLists[k]||[]).map((x,i)=>({x:Array.isArray(x)?x:[String(x?.name||x||'Option'),Number(x?.price||0)],i}));
    if(orderMode(k)==='manual'){
      const pos=new Map(normalizeManualOrder(k).map((i,p)=>[i,p]));
      return entries.sort((a,b)=>(pos.get(a.i)??999999)-(pos.get(b.i)??999999));
    }
    return entries.sort((a,b)=>String(a.x[0]).localeCompare(String(b.x[0]),'fr',{sensitivity:'base'}));
  }

  function mergeSeed(existing,seed){
    const out=Array.isArray(existing)?existing:[];
    const known=new Set(out.map(x=>norm(Array.isArray(x)?x[0]:x?.name)));
    for(const x of seed||[]) if(!known.has(norm(x[0]))){out.push(clone(x));known.add(norm(x[0]));}
    return out;
  }

  function ensure(){
    state.optionLists=state.optionLists||{};
    state.optionListDefs=state.optionListDefs||{};
    state.optionListOrderModes=state.optionListOrderModes||{};
    state.optionListOrders=state.optionListOrders||{};
    state.products=Array.isArray(state.products)?state.products:[];
    state.categories=Array.isArray(state.categories)?state.categories:[];
    for(const [k,d] of Object.entries(baseDefs)) state.optionLists[k]=mergeSeed(state.optionLists[k],d.seed);
    for(const k of Object.keys(state.optionListDefs)){
      state.optionLists[k]=Array.isArray(state.optionLists[k])?state.optionLists[k]:[];
      const d=state.optionListDefs[k];
      if(!['extra','absolute'].includes(d.priceMode)) d.priceMode='extra';
    }
    if(!state.optionListOrderModes.cuisson) state.optionListOrderModes.cuisson='manual';
    for(const k of Object.keys(defs())) if(orderMode(k)==='manual') normalizeManualOrder(k);
    for(const p of state.products) p.optionSelections=p.optionSelections||{};
  }

  function setStatus(text,isError=false){
    const s=$('status'); if(!s) return;
    s.textContent=text||'';
    s.style.color=isError?'#b00020':'';
  }

  async function load(){
    const r=await fetch(API+'/admin?t='+Date.now(),{cache:'no-store'});
    if(!r.ok) throw new Error('HTTP '+r.status);
    const j=await r.json();
    state=j.data||{categories:[],products:[],optionLists:{},optionListDefs:{}};
    ensure();
    renderAll();
    if(!state.products.length) setStatus('Catalogue V2 vide — utilisez « Importer le catalogue actuel » avant toute affectation.');
  }

  function validateLibrary(){
    const errors=[];
    for(const [k,d] of Object.entries(defs())){
      const seen=new Set();
      for(const item of state.optionLists[k]||[]){
        const name=String(Array.isArray(item)?item[0]:item?.name||'').trim();
        if(!name){errors.push(`${d.label||d.title}: élément sans nom`);continue;}
        const n=norm(name);
        if(seen.has(n)) errors.push(`${d.label||d.title}: doublon « ${name} »`);
        seen.add(n);
      }
      if((d.priceMode||'extra')==='absolute' && Number(d.max??1)!==1) errors.push(`${d.label||d.title}: un prix total doit avoir 1 seul choix maximum`);
    }
    return errors;
  }

  async function save(){
    captureAllLists(); captureCustomDefs();
    const errors=validateLibrary();
    if(errors.length) throw new Error(errors.join('\n'));
    setStatus('Enregistrement…');
    const r=await fetch(API+'/admin',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({data:state})});
    const j=await r.json().catch(()=>({}));
    if(!r.ok) throw new Error((j.errors||[j.error||('HTTP '+r.status)]).join('\n'));
    setStatus('✓ Sauvegardé');
    setTimeout(()=>setStatus(''),1800);
  }

  async function migrateLegacy(){
    if(!confirm('Créer une copie du catalogue actuel dans le Catalogue V2 ? L’ancien catalogue ne sera pas modifié.')) return;
    setStatus('Import de la copie du catalogue actuel…');
    const r=await fetch(API+'/migrate-legacy',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const j=await r.json().catch(()=>({}));
    if(!r.ok){
      if(j.reason==='v2_not_empty'){setStatus('Catalogue V2 déjà initialisé. Aucun écrasement effectué.');return;}
      throw new Error(j.error||j.reason||('HTTP '+r.status));
    }
    await load();
    setStatus(`✓ Copie importée : ${j.products||0} produits, ${j.categories||0} catégories`);
  }

  function renderAll(){
    const sel=$('product');
    if(sel){
      sel.innerHTML=(state.products||[]).map((p,i)=>`<option value="${i}">${esc(p.name)} — ${esc(p.category||'Sans catégorie')}</option>`).join('');
      sel.onchange=renderProduct;
    }
    renderLists(); renderProduct();
  }

  function priceModeLabel(d,price){
    const n=Number(price||0); if(!n) return '';
    return (d.priceMode||'extra')==='absolute' ? ` (${n.toFixed(2)} € prix total)` : ` (+${n.toFixed(2)} €)`;
  }

  function renderLists(){
    const root=$('lists'); if(!root)return;
    const all=defs();
    root.innerHTML=Object.entries(all).map(([k,d])=>{
      const custom=!!state.optionListDefs[k],sk=safeKey(k),mode=orderMode(k);
      return `<section class="card"><div style="display:flex;justify-content:space-between;gap:8px;align-items:center"><h3>${esc(d.label||d.title||'Options')}${d.fixed?' <small>(fixe)</small>':''}</h3><select data-order-mode="${esc(k)}" title="Ordre d’affichage"><option value="alpha" ${mode==='alpha'?'selected':''}>A → Z</option><option value="manual" ${mode==='manual'?'selected':''}>Manuel</option></select></div>`+
        `${custom?`<div class="list-settings"><input data-def-label="${esc(k)}" value="${esc(d.label||d.title)}"><input type="number" min="0" data-def-max="${esc(k)}" value="${Number(d.max??1)}"><select data-def-price-mode="${esc(k)}"><option value="extra" ${(d.priceMode||'extra')==='extra'?'selected':''}>Supplément</option><option value="absolute" ${d.priceMode==='absolute'?'selected':''}>Prix total</option></select></div><label class="muted"><input type="checkbox" data-def-required="${esc(k)}" ${d.required?'checked':''}> Choix obligatoire</label>`:''}`+
        `<div class="items" id="list-${sk}"></div>${d.fixed?'':`<button type="button" data-add="${esc(k)}">+ Ajouter un élément</button>`}${custom?` <button class="danger" type="button" data-delete-list="${esc(k)}">Supprimer la liste</button>`:''}</section>`;
    }).join('');
    for(const k of Object.keys(all)) renderList(k);
    root.querySelectorAll('[data-add]').forEach(b=>b.onclick=()=>{const k=b.dataset.add;captureList(k);state.optionLists[k].push(['Nouvel élément',0]);if(orderMode(k)==='manual')normalizeManualOrder(k);renderList(k);renderProduct();});
    root.querySelectorAll('[data-delete-list]').forEach(b=>b.onclick=()=>deleteCustomList(b.dataset.deleteList));
    root.querySelectorAll('[data-order-mode]').forEach(s=>s.onchange=()=>{
      const k=s.dataset.orderMode;
      captureList(k);
      if(s.value==='manual' && orderMode(k)!=='manual') state.optionListOrders[k]=visibleEntries(k).map(e=>e.i);
      state.optionListOrderModes[k]=s.value;
      if(s.value==='manual') normalizeManualOrder(k);
      renderList(k); renderProduct();
    });
  }

  function renderList(k){
    const box=$('list-'+safeKey(k)),d=defs()[k]; if(!box||!d)return;
    const manual=orderMode(k)==='manual';
    box.innerHTML=visibleEntries(k).map(({x,i})=>`<div class="row" data-order-index="${i}" ${manual?'draggable="true"':''}>${manual?'<span title="Glisser pour déplacer" style="cursor:grab;font-size:18px;user-select:none">☰</span>':''}<input type="text" data-ln-key="${esc(k)}" data-ln-index="${i}" value="${esc(x[0])}"><input type="number" step="0.01" data-lp-key="${esc(k)}" data-lp-index="${i}" value="${Number(x[1]||0)}">${d.fixed?'':`<button class="danger" type="button" data-ld-index="${i}">×</button>`}</div>`).join('');
    box.querySelectorAll('input').forEach(el=>el.onchange=()=>{captureList(k);renderProduct();});
    box.querySelectorAll('[data-ld-index]').forEach(b=>b.onclick=()=>deleteListItem(k,Number(b.dataset.ldIndex)));
    if(manual) enableDragOrder(k,box);
  }

  function enableDragOrder(k,box){
    let dragged=null;
    box.querySelectorAll('[data-order-index]').forEach(row=>{
      row.addEventListener('dragstart',e=>{dragged=Number(row.dataset.orderIndex);e.dataTransfer.effectAllowed='move';});
      row.addEventListener('dragover',e=>{e.preventDefault();e.dataTransfer.dropEffect='move';});
      row.addEventListener('drop',e=>{
        e.preventDefault();
        const target=Number(row.dataset.orderIndex);
        if(dragged===null||dragged===target)return;
        captureList(k);
        const order=normalizeManualOrder(k).slice();
        const from=order.indexOf(dragged),to=order.indexOf(target);
        if(from<0||to<0)return;
        order.splice(from,1); order.splice(to,0,dragged);
        state.optionListOrders[k]=order;
        renderList(k); renderProduct();
      });
      row.addEventListener('dragend',()=>{dragged=null;});
    });
  }

  function deleteListItem(k,index){
    captureList(k);
    state.optionLists[k].splice(index,1);
    for(const p of state.products||[]){
      const ids=Array.isArray(p.optionSelections?.[k])?p.optionSelections[k]:[];
      p.optionSelections[k]=ids.filter(i=>i!==index).map(i=>i>index?i-1:i);
    }
    if(Array.isArray(state.optionListOrders?.[k])) state.optionListOrders[k]=state.optionListOrders[k].filter(i=>i!==index).map(i=>i>index?i-1:i);
    renderList(k); renderProduct();
  }

  function captureList(k){
    document.querySelectorAll('[data-ln-key]').forEach(el=>{
      if(el.dataset.lnKey!==k)return;
      const i=Number(el.dataset.lnIndex);
      const price=[...document.querySelectorAll('[data-lp-key]')].find(p=>p.dataset.lpKey===k&&Number(p.dataset.lpIndex)===i);
      state.optionLists[k][i]=[el.value.trim()||'Option',Number(price?.value||0)];
    });
  }
  function captureAllLists(){for(const k of Object.keys(defs()))captureList(k);}

  function captureCustomDefs(){
    for(const k of Object.keys(state.optionListDefs||{})){
      const label=[...document.querySelectorAll('[data-def-label]')].find(x=>x.dataset.defLabel===k)?.value.trim();
      const max=[...document.querySelectorAll('[data-def-max]')].find(x=>x.dataset.defMax===k)?.value;
      const req=[...document.querySelectorAll('[data-def-required]')].find(x=>x.dataset.defRequired===k)?.checked;
      const mode=[...document.querySelectorAll('[data-def-price-mode]')].find(x=>x.dataset.defPriceMode===k)?.value;
      if(label) state.optionListDefs[k].label=state.optionListDefs[k].title=label;
      if(max!==undefined) state.optionListDefs[k].max=Math.max(0,Number(max||0));
      if(req!==undefined) state.optionListDefs[k].required=!!req;
      if(['extra','absolute'].includes(mode)) state.optionListDefs[k].priceMode=mode;
    }
  }

  function currentProduct(){return state.products?.[Number($('product')?.value)];}

  function deriveSelection(p,k){
    if(Array.isArray(p.optionSelections?.[k]))return p.optionSelections[k];
    const d=defs()[k],g=(p.options||[]).find(g=>norm(g.key)===norm('central_'+k)||norm(g.title||g.key)===norm(d.title)||norm(g.key)===norm(k));
    if(!g)return[];
    return(g.choices||[]).map(c=>norm(Array.isArray(c)?c[0]:c.name||c.label)).map(n=>(state.optionLists[k]||[]).findIndex(x=>{const item=norm(x[0]);return k==='garnitures'?(n===item||n===norm('Sans '+x[0])):n===item;})).filter(i=>i>=0);
  }

  function renderProduct(){
    const p=currentProduct(),root=$('productOptions'); if(!root)return;
    if(!p){root.innerHTML='<div class="muted">Sélectionnez un produit pour afficher les cases à cocher.</div>';return;}
    p.optionSelections=p.optionSelections||{};
    root.innerHTML=Object.entries(defs()).map(([k,d])=>{
      const selected=new Set(deriveSelection(p,k));
      return `<section class="checkcard"><b>${esc(d.label||d.title)}</b><div class="muted">Choisissez uniquement ce qui convient à ${esc(p.name)}.</div>${visibleEntries(k).map(({x,i})=>`<label class="checkitem"><input type="checkbox" data-pick-key="${esc(k)}" data-pick-index="${i}" ${selected.has(i)?'checked':''}><span>${esc(x[0])}${priceModeLabel(d,x[1])}</span></label>`).join('')}</section>`;
    }).join('');
  }

  function buildOptions(p){
    const all=defs(),managedKeys=new Set(Object.keys(all).map(k=>norm('central_'+k))),managedTitles=new Set(Object.values(all).map(d=>norm(d.title)));
    const out=[...(p.options||[]).filter(g=>!managedKeys.has(norm(g.key))&&!managedTitles.has(norm(g.title||g.key)))];
    for(const [k,d] of Object.entries(all)){
      const ids=p.optionSelections[k]||[]; if(!ids.length)continue;
      const selected=new Set(ids);
      const choices=visibleEntries(k).filter(e=>selected.has(e.i)).map(e=>clone(state.optionLists[k][e.i])).filter(Boolean);
      if(k==='garnitures') choices.forEach(c=>{if(!/^sans\s/i.test(c[0]))c[0]='Sans '+c[0];});
      out.push({key:'central_'+k,title:d.title,required:!!d.required,max:Number(d.max??1),priceMode:d.priceMode||'extra',choices});
    }
    return out;
  }

  function newCustomList(){
    let name=prompt('Nom de la nouvelle liste d’options :','Nombre de pièces'); if(!name)return;
    name=name.trim(); if(!name)return;
    const key='custom_'+Date.now();
    state.optionListDefs[key]={label:name,title:name,max:1,required:false,fixed:false,priceMode:'extra'};
    state.optionLists[key]=[];
    state.optionListOrderModes[key]='alpha';
    renderLists(); renderProduct();
  }

  async function deleteCustomList(k){
    if(!confirm('Supprimer cette liste ? Elle sera aussi retirée des produits auxquels elle est affectée.'))return;
    delete state.optionListDefs[k]; delete state.optionLists[k]; delete state.optionListOrderModes[k]; delete state.optionListOrders[k];
    for(const p of state.products||[]){delete p.optionSelections?.[k];p.options=(p.options||[]).filter(g=>norm(g.key)!==norm('central_'+k));}
    await save(); renderLists(); renderProduct();
  }

  $('newList').onclick=newCustomList;
  if($('migrateLegacy')) $('migrateLegacy').onclick=()=>migrateLegacy().catch(e=>{console.error(e);setStatus('Erreur : '+e.message,true);});
  $('saveLibrary').onclick=async()=>{try{await save();renderAll();alert('Bibliothèque centrale V2 enregistrée.');}catch(e){console.error(e);setStatus('Erreur : '+e.message,true);alert(e.message);}};
  $('saveProduct').onclick=async()=>{
    try{
      const p=currentProduct(); if(!p)return alert('Sélectionnez d’abord un produit.');
      captureAllLists(); captureCustomDefs();
      for(const k of Object.keys(defs())) p.optionSelections[k]=[...document.querySelectorAll('[data-pick-key]:checked')].filter(el=>el.dataset.pickKey===k).map(el=>Number(el.dataset.pickIndex));
      p.options=buildOptions(p);
      await save();
      alert('Options de '+p.name+' enregistrées dans le Catalogue V2.');
    }catch(e){console.error(e);setStatus('Erreur : '+e.message,true);alert(e.message);}
  };

  load().catch(e=>{console.error(e);setStatus('Erreur : '+e.message,true);});
})();