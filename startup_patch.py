# BÉCHÉFAA V0.5.45 — Catalogue central source unique + groupes réutilisables + photo importée
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent
APP_JS = BASE / "static" / "app.js"
INDEX = BASE / "static" / "index.html"


def patch_app_js():
    src = APP_JS.read_text(encoding="utf-8")

    # Une seule logique POS : le Catalogue central prend la priorité sur les anciens profils Wix.
    if "V0.5.44 CENTRAL CATALOGUE SOURCE UNIQUE" not in src:
        needle = "function profile(p){\n let ek=exactKey(p);"
        replacement = r'''/* === V0.5.44 CENTRAL CATALOGUE SOURCE UNIQUE === */
const CENTRAL_PROFILE_BY_ID=Object.create(null),CENTRAL_PROFILE_BY_NAME=Object.create(null);
function centralProductFor(p){
 const id=String(p?.id??"");
 if(Object.prototype.hasOwnProperty.call(CENTRAL_PROFILE_BY_ID,id))return CENTRAL_PROFILE_BY_ID[id];
 const name=norm(p?.name);
 if(Object.prototype.hasOwnProperty.call(CENTRAL_PROFILE_BY_NAME,name))return CENTRAL_PROFILE_BY_NAME[name];
 return null;
}
async function loadCentralCatalogMaster(){
 try{
  const r=await fetch("/api/catalog-admin?t="+Date.now(),{cache:"no-store"});
  if(!r.ok)throw new Error("HTTP "+r.status);
  const j=await r.json(),data=j?.data;
  if(!data||!Array.isArray(data.products)||!Array.isArray(data.categories))return;

  // Migration unique : restaure la configuration validée de Formule Enfant si elle a disparu.
  data._migrations=data._migrations||{};
  if(!data._migrations.formuleEnfantOptionsV1){
   const fe=data.products.find(p=>norm(p?.name)==="formule enfant");
   if(fe && (!Array.isArray(fe.options)||!fe.options.length)){
    fe.options=[
     {key:"choix_tender",title:"Choix du Tender",required:true,max:1,choices:[["Tender classique",0],["Tender Crispy",0]]},
     {key:"boisson_hors_caprisun",title:"Boisson",required:false,max:1,choices:[["Caprisun",0],["Coca cola",1.5],["Coca Zero",1.5],["Orangina",1.5]]}
    ];
   }
   data._migrations.formuleEnfantOptionsV1=true;
   await fetch("/api/catalog-admin",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({data})});
  }

  Object.keys(CENTRAL_PROFILE_BY_ID).forEach(k=>delete CENTRAL_PROFILE_BY_ID[k]);
  Object.keys(CENTRAL_PROFILE_BY_NAME).forEach(k=>delete CENTRAL_PROFILE_BY_NAME[k]);
  const legacy=Array.isArray(window.PRODUCTS)?window.PRODUCTS:[];
  const legacyById=new Map(legacy.map(x=>[String(x.id),x]));
  const legacyByName=new Map(legacy.map(x=>[norm(x.name),x]));
  const active=data.products.filter(p=>p?.active!==false&&(p?.channels?.caisse!==false));
  active.forEach((p,i)=>{
   const keys=[];
   (Array.isArray(p.options)?p.options:[]).forEach((g,gi)=>{
    const safeId=String(p.id??p.name??("product"+i)).replace(/[^a-zA-Z0-9_-]/g,"_");
    const key=`central_${safeId}_${gi}`;
    const choices=(Array.isArray(g?.choices)?g.choices:[]).map(c=>Array.isArray(c)?[String(c[0]??"Option"),Number(c[1]||0)]:[String(c?.name??c?.label??"Option"),Number(c?.price??c?.extra??0)]);
    GROUPS[key]={title:String(g?.title||g?.key||"Options"),required:!!g?.required,max:Math.max(0,Number(g?.max??1)),choices};
    keys.push(key);
   });
   CENTRAL_PROFILE_BY_ID[String(p.id??"")]=keys;
   CENTRAL_PROFILE_BY_NAME[norm(p.name)]=keys;
  });
  window.PRODUCTS=active.map((p,i)=>{
   const old=legacyById.get(String(p.id))||legacyByName.get(norm(p.name))||{};
   return {id:String(p.id??old.id??("central-"+i)),cat:String(p.category||old.cat||""),name:String(p.name||old.name||"Produit"),price:Number(p.price??old.price??0),image:String(p.photo||old.image||""),desc:String(p.ingredients||old.desc||"")};
  });
  const used=new Set(window.PRODUCTS.map(p=>p.cat));
  const cats=data.categories.filter(c=>c?.active!==false&&used.has(c.name)).map(c=>c.name);
  window.CATEGORIES=cats.length?cats:[...used];
  if(!window.CATEGORIES.includes(cat))cat=window.CATEGORIES[0]||"";
  rc();rp();
  console.log(`BÉCHÉFAA: Catalogue central chargé (${window.PRODUCTS.length} produits).`);
 }catch(e){console.error("BÉCHÉFAA Catalogue central -> POS:",e)}
}
window.BECHEFAA_RELOAD_CATALOG=loadCentralCatalogMaster;
setTimeout(loadCentralCatalogMaster,0);
function profile(p){
 const central=centralProductFor(p);
 if(central!==null)return central;
 let ek=exactKey(p);'''
        if needle in src:
            src = src.replace(needle, replacement, 1)

    # IDs texte acceptés.
    src = src.replace('$("products").querySelectorAll(".product").forEach(b=>b.onclick=()=>openProduct(+b.dataset.id))','$("products").querySelectorAll(".product").forEach(b=>b.onclick=()=>openProduct(b.dataset.id))')
    src = src.replace('current=window.PRODUCTS.find(x=>x.id===id); selections={}; const prof=profile(current);','current=window.PRODUCTS.find(x=>String(x.id)===String(id)); selections={}; const prof=profile(current);')

    # Photo : URL cachée mais valeur conservée, import direct visible.
    old_photo = '<label>Photo / URL<input id="pfPhoto" value="${p.photo||""}" placeholder="Photo du produit"></label>'
    new_photo = '''<input id="pfPhoto" type="hidden" value="${p.photo||"}">
   <label>Photo du produit<input id="pfPhotoFile" type="file" accept="image/*"></label>
   <div id="pfPhotoPreview" class="catalog-photo-preview">${p.photo?`<img src="${p.photo}" alt="Aperçu">`:`<small>Aucune photo</small>`}</div>'''
    src = src.replace(old_photo, new_photo)

    # Supprime définitivement caisse -> catalogue.
    src = src.replace('<button type="button" id="pfAddOptionGroup">+ Groupe</button><button type="button" id="pfReloadOptions">↻ Reprendre caisse</button>','<button type="button" id="pfAddOptionGroup">+ Groupe</button>')
    src = re.sub(r'\n\s*\$\("pfReloadOptions"\)\.onclick=\(\)=>\{.*?\n\s*\};','',src,count=1,flags=re.S)

    # V0.5.45 : bibliothèque de groupes réutilisables.
    if "V0.5.45 REUSABLE OPTION GROUPS" not in src:
        product_needle = " function productForm(p){"
        library_helpers = r''' /* === V0.5.45 REUSABLE OPTION GROUPS === */
 function cloneOptionGroup(g){
  return {key:"custom_"+Date.now()+"_"+Math.random().toString(36).slice(2),title:String(g?.title||"Options"),required:!!g?.required,max:Math.max(0,Number(g?.max??1)),choices:(Array.isArray(g?.choices)?g.choices:[]).map(c=>Array.isArray(c)?[String(c[0]??"Option"),Number(c[1]||0)]:[String(c?.name??c?.label??"Option"),Number(c?.price??c?.extra??0)])};
 }
 function optionGroupSignature(g){
  const c=(Array.isArray(g?.choices)?g.choices:[]).map(x=>Array.isArray(x)?[String(x[0]||""),Number(x[1]||0)]:[String(x?.name||x?.label||""),Number(x?.price||x?.extra||0)]);
  return JSON.stringify([String(g?.title||"Options").trim().toLowerCase(),!!g?.required,Math.max(0,Number(g?.max??1)),c]);
 }
 function ensureOptionLibrary(){
  state.optionTemplates=Array.isArray(state.optionTemplates)?state.optionTemplates:[];
  const known=new Set(state.optionTemplates.map(optionGroupSignature));
  (state.products||[]).forEach(prod=>(prod.options||[]).forEach(g=>{
   const sig=optionGroupSignature(g);if(known.has(sig))return;
   const x=cloneOptionGroup(g);x.id="tpl_"+Date.now()+"_"+Math.random().toString(36).slice(2);state.optionTemplates.push(x);known.add(sig);
  }));
  return state.optionTemplates;
 }
 function rememberProductGroups(groups){
  const lib=ensureOptionLibrary(),known=new Set(lib.map(optionGroupSignature));
  (groups||[]).forEach(g=>{const sig=optionGroupSignature(g);if(known.has(sig))return;const x=cloneOptionGroup(g);x.id="tpl_"+Date.now()+"_"+Math.random().toString(36).slice(2);lib.push(x);known.add(sig);});
 }
'''
        if product_needle in src:
            src = src.replace(product_needle, library_helpers + product_needle, 1)

        title_old = '<div class="catalog-options-title"><b>Options du produit</b><div><button type="button" id="pfAddOptionGroup">+ Groupe</button></div></div>\n    <div id="pfOptionsList"></div>'
        title_new = '''<div class="catalog-options-title"><b>Options du produit</b><div><button type="button" id="pfAddOptionGroup">+ Nouveau groupe</button></div></div>
    <div class="catalog-option-library"><select id="pfSavedGroup"><option value="">Ajouter un groupe enregistré…</option></select><button type="button" id="pfUseSavedGroup">Ajouter</button></div>
    <div id="pfOptionsList"></div>'''
        src = src.replace(title_old, title_new)

        render_marker = '   renderPfOptions();\n   $("pfAddOptionGroup").onclick='
        if render_marker in src:
            handler = r'''   const refreshSavedGroups=()=>{
    const sel=$("pfSavedGroup");if(!sel)return;const lib=ensureOptionLibrary();
    sel.innerHTML='<option value="">Ajouter un groupe enregistré…</option>'+lib.map((g,i)=>`<option value="${i}">${g.title} — ${(g.choices||[]).length} choix</option>`).join("");
   };
   refreshSavedGroups();
   $("pfUseSavedGroup")?.addEventListener("click",()=>{
    const sel=$("pfSavedGroup"),idx=Number(sel?.value);if(!sel||sel.value===""||!Number.isInteger(idx))return;
    captureOptions();const tpl=ensureOptionLibrary()[idx];if(!tpl)return;p.options.push(cloneOptionGroup(tpl));renderPfOptions();
   });
   renderPfOptions();
   $("pfAddOptionGroup").onclick='''
            src = src.replace(render_marker, handler, 1)

        # Tous les groupes utilisés sur un produit deviennent réutilisables lors de l'enregistrement.
        src = src.replace('captureOptions();p.name=$("pfName").value.trim();','captureOptions();rememberProductGroups(p.options);p.name=$("pfName").value.trim();',1)

    marker = '   renderPfOptions();\n   $("pfAddOptionGroup").onclick='
    if 'pfPhotoFile' in src and 'compressCatalogPhoto' not in src and marker in src:
        photo_js = r'''   async function compressCatalogPhoto(file){
    return await new Promise((resolve,reject)=>{
     const fr=new FileReader();fr.onerror=()=>reject(new Error("Lecture photo impossible"));
     fr.onload=()=>{const im=new Image();im.onerror=()=>reject(new Error("Image invalide"));im.onload=()=>{
      const max=1200,ratio=Math.min(1,max/Math.max(im.width,im.height)),c=document.createElement("canvas");
      c.width=Math.max(1,Math.round(im.width*ratio));c.height=Math.max(1,Math.round(im.height*ratio));
      c.getContext("2d").drawImage(im,0,0,c.width,c.height);resolve(c.toDataURL("image/jpeg",0.80));};im.src=fr.result;};fr.readAsDataURL(file);
    });
   }
   const pfPhotoFile=$("pfPhotoFile"),pfPhotoPreview=$("pfPhotoPreview"),pfPhoto=$("pfPhoto");
   const updatePhotoPreview=()=>{if(pfPhotoPreview)pfPhotoPreview.innerHTML=pfPhoto?.value?`<img src="${pfPhoto.value}" alt="Aperçu">`:`<small>Aucune photo</small>`};
   pfPhotoFile?.addEventListener("change",async()=>{const file=pfPhotoFile.files?.[0];if(!file)return;if(!file.type.startsWith("image/"))return alert("Choisissez une image.");try{pfPhotoFile.disabled=true;pfPhoto.value=await compressCatalogPhoto(file);updatePhotoPreview()}catch(e){alert("Impossible de charger cette photo.")}finally{pfPhotoFile.disabled=false;}});
   renderPfOptions();
   $("pfAddOptionGroup").onclick='''
        src = src.replace(marker, photo_js, 1)

    # Sauvegarde réellement confirmée par la base centrale.
    save_pattern = r'async function save\(\)\{.*?\n \}\n async function loadCentralState\(\)\{'
    save_replacement = r'''async function save(){
   localStorage.setItem(KEY,JSON.stringify(state));
   const st=document.getElementById("catalogSaveStatus");
   try{
    if(st)st.textContent="Enregistrement…";
    const r=await fetch("/api/catalog-admin",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({data:state})});
    if(!r.ok)throw new Error(await r.text());
    if(st)st.textContent="✓ Sauvegardé dans la base centrale";
    await window.BECHEFAA_RELOAD_CATALOG?.();
    return true;
   }catch(e){if(st)st.textContent="⚠ Échec de sauvegarde — fiche conservée";console.error("Sauvegarde catalogue:",e);return false;}
 }
 async function loadCentralState(){'''
    src = re.sub(save_pattern, save_replacement, src, count=1, flags=re.S)

    pf_pattern = r'\$\("pfSave"\)\.onclick=\(\)=>\{captureOptions\(\);.*?if\(isNew\)state\.products\.push\(p\);save\(\);close\(\);render\(\)\};'
    pf_replacement = r'''$("pfSave").onclick=async()=>{
    captureOptions();rememberProductGroups(p.options);p.name=$("pfName").value.trim();p.category=$("pfCat").value;p.price=Number($("pfPrice").value||0);p.photo=$("pfPhoto").value;p.ingredients=$("pfIngredients").value.trim();p.schedule=$("pfSchedule").value;p.active=$("pfActive").checked;
    p.channels={caisse:$("chCaisse").checked,site:$("chSite").checked,ubereats:$("chUber").checked,deliveroo:$("chDeliveroo").checked};if(!p.name)return alert("Nom obligatoire");if(isNew)state.products.push(p);
    const btn=$("pfSave");if(btn){btn.disabled=true;btn.textContent="ENREGISTREMENT…";}const ok=await save();if(btn){btn.disabled=false;btn.textContent="Enregistrer";}
    if(!ok){if(isNew)state.products=state.products.filter(x=>x!==p);return alert("La sauvegarde n'a pas abouti. La fiche reste ouverte.");}close();render();
   };'''
    src = re.sub(pf_pattern, pf_replacement, src, count=1, flags=re.S)

    APP_JS.write_text(src, encoding="utf-8")


def patch_index():
    src = INDEX.read_text(encoding="utf-8")
    src = re.sub(r'app\.js\?v=\d+', 'app.js?v=0545', src, count=1)
    src = src.replace('<button id="catSyncOptions">⚙ Synchroniser les options</button>\n','')
    INDEX.write_text(src, encoding="utf-8")


try:
    patch_app_js();patch_index()
    print("BÉCHÉFAA V0.5.45: groupes réutilisables + source unique catalogue + photo importée")
except Exception as exc:
    print("BÉCHÉFAA V0.5.45 patch error:", exc)
