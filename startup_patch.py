# BÉCHÉFAA V0.5.42 - correctifs directs du POS au démarrage
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent
APP_JS = BASE / "static" / "app.js"
INDEX = BASE / "static" / "index.html"


def patch_app_js():
    src = APP_JS.read_text(encoding="utf-8")

    if "V0.5.42 CENTRAL CATALOGUE SOURCE UNIQUE" not in src:
        needle = "function profile(p){\n let ek=exactKey(p);"
        replacement = r'''/* === V0.5.42 CENTRAL CATALOGUE SOURCE UNIQUE === */
const CENTRAL_PROFILE_BY_ID=Object.create(null),CENTRAL_PROFILE_BY_NAME=Object.create(null);
async function loadCentralCatalogForPos(){
 try{
  const r=await fetch("/api/catalog-admin?t="+Date.now(),{cache:"no-store"});
  if(!r.ok)throw new Error("HTTP "+r.status);
  const j=await r.json(),data=j?.data;
  if(!data||!Array.isArray(data.products))return;
  Object.keys(CENTRAL_PROFILE_BY_ID).forEach(k=>delete CENTRAL_PROFILE_BY_ID[k]);
  Object.keys(CENTRAL_PROFILE_BY_NAME).forEach(k=>delete CENTRAL_PROFILE_BY_NAME[k]);
  const legacy=Array.isArray(window.PRODUCTS)?window.PRODUCTS:[];
  const legacyById=new Map(legacy.map(x=>[String(x.id),x]));
  const legacyByName=new Map(legacy.map(x=>[norm(x.name),x]));
  const active=(data.products||[]).filter(p=>p?.active!==false&&(p?.channels?.caisse!==false));
  active.forEach((p)=>{
   const keys=[];
   (Array.isArray(p.options)?p.options:[]).forEach((g,i)=>{
    const safeId=String(p.id??p.name??"product").replace(/[^a-zA-Z0-9_-]/g,"_");
    const key=`central_${safeId}_${i}`;
    const choices=(Array.isArray(g?.choices)?g.choices:[]).map(c=>Array.isArray(c)?[String(c[0]??"Option"),Number(c[1]||0)]:[String(c?.name??c?.label??"Option"),Number(c?.price??c?.extra??0)]);
    GROUPS[key]={title:String(g?.title||g?.key||"Options"),required:!!g?.required,max:Math.max(0,Number(g?.max??1)),choices};
    keys.push(key);
   });
   CENTRAL_PROFILE_BY_ID[String(p.id??"")]=keys;
   CENTRAL_PROFILE_BY_NAME[norm(p.name)]=keys;
  });
  window.PRODUCTS=active.map(p=>{
   const old=legacyById.get(String(p.id))||legacyByName.get(norm(p.name))||{};
   return {id:String(p.id??p.name),cat:String(p.category||old.cat||""),name:String(p.name||old.name||"Produit"),price:Number(p.price||0),image:String(p.photo||old.image||""),desc:String(p.ingredients||old.desc||"")};
  });
  const used=new Set(window.PRODUCTS.map(p=>p.cat));
  const cats=(Array.isArray(data.categories)?data.categories:[]).filter(c=>c?.active!==false&&used.has(c.name)).map(c=>c.name);
  window.CATEGORIES=cats.length?cats:[...used];
  if(!window.CATEGORIES.includes(cat))cat=window.CATEGORIES[0]||"";
  rc();rp();
 }catch(e){console.error("BÉCHÉFAA Catalogue central -> POS:",e)}
}
window.BECHEFAA_RELOAD_CATALOG=loadCentralCatalogForPos;
setTimeout(loadCentralCatalogForPos,0);
function profile(p){
 const cid=String(p?.id??"");
 if(Object.prototype.hasOwnProperty.call(CENTRAL_PROFILE_BY_ID,cid))return CENTRAL_PROFILE_BY_ID[cid];
 const cn=norm(p?.name);
 if(Object.prototype.hasOwnProperty.call(CENTRAL_PROFILE_BY_NAME,cn))return CENTRAL_PROFILE_BY_NAME[cn];
 let ek=exactKey(p);'''
        if needle in src:
            src = src.replace(needle, replacement, 1)

    src = src.replace('$("products").querySelectorAll(".product").forEach(b=>b.onclick=()=>openProduct(+b.dataset.id))','$("products").querySelectorAll(".product").forEach(b=>b.onclick=()=>openProduct(b.dataset.id))')
    src = src.replace('current=window.PRODUCTS.find(x=>x.id===id); selections={}; const prof=profile(current);','current=window.PRODUCTS.find(x=>String(x.id)===String(id)); selections={}; const prof=profile(current);')

    old_photo = '<label>Photo / URL<input id="pfPhoto" value="${p.photo||""}" placeholder="Photo du produit"></label>'
    new_photo = '''<label>Photo / URL<input id="pfPhoto" value="${p.photo||""}" placeholder="URL de la photo (facultatif)"></label>
   <label>Importer une photo<input id="pfPhotoFile" type="file" accept="image/*"></label>
   <div id="pfPhotoPreview" class="catalog-photo-preview">${p.photo?`<img src="${p.photo}" alt="Aperçu">`:`<small>Aucune photo</small>`}</div>'''
    src = src.replace(old_photo, new_photo)

    src = src.replace('<button type="button" id="pfAddOptionGroup">+ Groupe</button><button type="button" id="pfReloadOptions">↻ Reprendre caisse</button>','<button type="button" id="pfAddOptionGroup">+ Groupe</button>')

    src = re.sub(r'\n\s*\$\("pfReloadOptions"\)\.onclick=\(\)=>\{.*?\n\s*\};', '', src, count=1, flags=re.S)

    marker = '   renderPfOptions();\n   $("pfAddOptionGroup").onclick='
    if 'pfPhotoFile' in src and 'compressCatalogPhoto' not in src and marker in src:
        photo_js = r'''   async function compressCatalogPhoto(file){
    return await new Promise((resolve,reject)=>{
     const fr=new FileReader();
     fr.onerror=()=>reject(new Error("Lecture photo impossible"));
     fr.onload=()=>{
      const im=new Image();
      im.onerror=()=>reject(new Error("Image invalide"));
      im.onload=()=>{
       const max=1200,ratio=Math.min(1,max/Math.max(im.width,im.height));
       const c=document.createElement("canvas");c.width=Math.max(1,Math.round(im.width*ratio));c.height=Math.max(1,Math.round(im.height*ratio));
       c.getContext("2d").drawImage(im,0,0,c.width,c.height);
       resolve(c.toDataURL("image/jpeg",0.82));
      };im.src=fr.result;
     };fr.readAsDataURL(file);
    });
   }
   const pfPhotoFile=$("pfPhotoFile"),pfPhotoPreview=$("pfPhotoPreview"),pfPhoto=$("pfPhoto");
   const updatePhotoPreview=()=>{if(pfPhotoPreview)pfPhotoPreview.innerHTML=pfPhoto?.value?`<img src="${pfPhoto.value}" alt="Aperçu">`:`<small>Aucune photo</small>`};
   pfPhoto?.addEventListener("input",updatePhotoPreview);
   pfPhotoFile?.addEventListener("change",async()=>{
    const file=pfPhotoFile.files?.[0];if(!file)return;
    if(!file.type.startsWith("image/"))return alert("Choisissez une image.");
    try{pfPhoto.value=await compressCatalogPhoto(file);updatePhotoPreview()}catch(e){alert("Impossible de charger cette photo.")}
   });
   renderPfOptions();
   $("pfAddOptionGroup").onclick='''
        src = src.replace(marker, photo_js, 1)

    src = src.replace('if(st)st.textContent="✓ Sauvegardé dans la base centrale";','if(st)st.textContent="✓ Sauvegardé dans la base centrale"; await window.BECHEFAA_RELOAD_CATALOG?.();')

    APP_JS.write_text(src, encoding="utf-8")


def patch_index():
    src = INDEX.read_text(encoding="utf-8")
    src = src.replace('app.js?v=0538','app.js?v=0542')
    src = src.replace('<button id="catSyncOptions">⚙ Synchroniser les options</button>\n','')
    INDEX.write_text(src, encoding="utf-8")


try:
    patch_app_js()
    patch_index()
    print("BÉCHÉFAA V0.5.42: Catalogue central -> POS + import photo activés")
except Exception as exc:
    print("BÉCHÉFAA V0.5.42 patch error:", exc)
