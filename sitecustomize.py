# BÉCHÉFAA POS — bootstrap de migrations + liaison Catalogue central -> options POS
from sitecustomize_core import *  # conserve la migration des descriptions existante

from pathlib import Path

_PATCH_MARKER = "V0.5.39 CENTRAL POS OPTIONS"
_APP_JS = Path(__file__).resolve().parent / "static" / "app.js"


def _patch_pos_catalog_options():
    try:
        src = _APP_JS.read_text(encoding="utf-8")
        if _PATCH_MARKER in src:
            return

        needle = "function profile(p){\n let ek=exactKey(p);"
        if needle not in src:
            print("BÉCHÉFAA catalogue POS: point d'injection introuvable, patch ignoré.")
            return

        replacement = r'''/* === V0.5.39 CENTRAL POS OPTIONS ===
   Les options configurées dans Catalogue central deviennent prioritaires sur
   les anciens profils codés en dur de la caisse. Le profil historique reste
   uniquement en secours tant qu'un produit n'existe pas dans le catalogue. */
const CENTRAL_PROFILE_BY_ID=Object.create(null), CENTRAL_PROFILE_BY_NAME=Object.create(null);
async function loadCentralCatalogOptions(){
 try{
  const r=await fetch("/api/catalog-admin?t="+Date.now(),{cache:"no-store"});
  if(!r.ok)throw new Error("HTTP "+r.status);
  const j=await r.json(), products=j?.data?.products;
  if(!Array.isArray(products))return;
  products.forEach((p)=>{
   const keys=[];
   const enabled=p?.active!==false && (p?.channels?.caisse!==false);
   if(enabled){
    (Array.isArray(p.options)?p.options:[]).forEach((g,i)=>{
     const safeId=String(p.id??p.name??"product").replace(/[^a-zA-Z0-9_-]/g,"_");
     const key=`central_${safeId}_${i}`;
     const choices=(Array.isArray(g?.choices)?g.choices:[]).map(c=>{
      if(Array.isArray(c))return [String(c[0]??"Option"),Number(c[1]||0)];
      return [String(c?.name??c?.label??"Option"),Number(c?.price??c?.extra??0)];
     });
     GROUPS[key]={
      title:String(g?.title||g?.key||"Options"),
      required:!!g?.required,
      max:Math.max(0,Number(g?.max??1)),
      choices
     };
     keys.push(key);
    });
   }
   CENTRAL_PROFILE_BY_ID[String(p.id??"")]=keys;
   CENTRAL_PROFILE_BY_NAME[norm(p.name)]=keys;
  });
  if(typeof rp==="function")rp();
 }catch(e){console.error("BÉCHÉFAA options Catalogue central -> POS:",e)}
}
setTimeout(loadCentralCatalogOptions,0);
function profile(p){
 const centralId=String(p?.id??"");
 if(Object.prototype.hasOwnProperty.call(CENTRAL_PROFILE_BY_ID,centralId))return CENTRAL_PROFILE_BY_ID[centralId];
 const centralName=norm(p?.name);
 if(Object.prototype.hasOwnProperty.call(CENTRAL_PROFILE_BY_NAME,centralName))return CENTRAL_PROFILE_BY_NAME[centralName];
 let ek=exactKey(p);'''

        patched = src.replace(needle, replacement, 1)
        _APP_JS.write_text(patched, encoding="utf-8")
        print("BÉCHÉFAA catalogue POS: options centrales activées (V0.5.39).")
    except Exception as exc:
        # Le POS doit rester démarrable même si ce correctif ne peut pas s'appliquer.
        print("BÉCHÉFAA catalogue POS: patch ignoré:", exc)


_patch_pos_catalog_options()
