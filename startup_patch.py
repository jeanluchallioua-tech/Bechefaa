# BÉCHÉFAA — Catalogue V2 runtime
# Source unique du catalogue POS : /api/catalog-admin (PostgreSQL).
# Wix/V1 ne doit plus fournir produits, photos, catégories ou options.

from pathlib import Path
import re
import sys
import dbcompat

BASE = Path(__file__).resolve().parent
APP_PY = BASE / "app.py"
APP_JS = BASE / "static" / "app.js"


def bind_postgresql_runtime():
    """Remplace le module sqlite3 déjà importé par app.py par dbcompat."""
    bound = False
    for module in list(sys.modules.values()):
        try:
            module_file = getattr(module, "__file__", None)
            if module_file and Path(module_file).resolve() == APP_PY.resolve():
                setattr(module, "sqlite3", dbcompat)
                bound = True
        except Exception:
            pass
    print("BÉCHÉFAA DB: PostgreSQL runtime lié directement." if bound else "BÉCHÉFAA DB: module app en cours d'import, liaison différée au runtime.")


def patch_pos_catalog_v2():
    src = APP_JS.read_text(encoding="utf-8")
    marker = "BECHEFAA_CATALOGUE_V2_SOURCE_UNIQUE"
    if marker in src:
        return

    profile_pattern = r"function profile\(p\)\{.*?\n\}\nfunction rc\(\)\{"
    if not re.search(profile_pattern, src, flags=re.S):
        print("BÉCHÉFAA V2: bloc profile() introuvable, aucun patch appliqué.")
        return

    replacement = r'''/* === BECHEFAA_CATALOGUE_V2_SOURCE_UNIQUE === */
const CENTRAL_PROFILE_BY_ID=Object.create(null),CENTRAL_PROFILE_BY_NAME=Object.create(null);
let CENTRAL_CATALOG_READY=false;

const CENTRAL_OPTION_DEFS={
 garnitures:{title:"Retirer garniture",required:false,max:30},
 supplements:{title:"Suppléments",required:false,max:0},
 sauces:{title:"Sauces",required:false,max:3},
 saucesSupp:{title:"Choix des sauces supplémentaire",required:false,max:3},
 cuisson:{title:"Cuisson",required:false,max:1},
 pain:{title:"Choix du pain",required:false,max:1},
 boissons:{title:"Boisson",required:false,max:1},
 accompagnements:{title:"Accompagnement",required:false,max:1},
 viandes:{title:"Choix des viandes",required:false,max:1},
 poulet:{title:"Choix du poulet",required:false,max:1},
 tender:{title:"Type de tender",required:false,max:1}
};

function centralProductFor(p){
 const id=String(p?.id??"");
 if(Object.prototype.hasOwnProperty.call(CENTRAL_PROFILE_BY_ID,id))return CENTRAL_PROFILE_BY_ID[id];
 const name=norm(p?.name);
 if(Object.prototype.hasOwnProperty.call(CENTRAL_PROFILE_BY_NAME,name))return CENTRAL_PROFILE_BY_NAME[name];
 return null;
}

function compileCentralOptions(data,p){
 const selections=p?.optionSelections||{},lists=data?.optionLists||{},custom=data?.optionListDefs||{};
 const selectedKeys=Object.keys(selections).filter(k=>Array.isArray(selections[k])&&selections[k].length);
 if(selectedKeys.length){
  const out=[];
  for(const k of selectedKeys){
   const ids=selections[k];
   const source=Array.isArray(lists[k])?lists[k]:[];
   const choices=ids.map(i=>source[Number(i)]).filter(Boolean).map(c=>{
    const x=Array.isArray(c)?c:[String(c?.name||c?.label||"Option"),Number(c?.price||0)];
    let label=String(x[0]??"Option");
    if(k==="garnitures"&&!/^sans\s/i.test(label))label="Sans "+label;
    return [label,Number(x[1]||0)];
   });
   if(!choices.length)continue;
   const d=custom[k]||CENTRAL_OPTION_DEFS[k]||{};
   out.push({key:"central_"+k,title:String(d.title||d.label||k),required:!!d.required,max:Math.max(0,Number(d.max??1)),choices});
  }
  return out;
 }
 return [];
}

async function loadCentralCatalogMaster(){
 try{
  const r=await fetch("/api/catalog-admin?t="+Date.now(),{cache:"no-store"});
  if(!r.ok)throw new Error("HTTP "+r.status);
  const j=await r.json(),data=j?.data;
  if(!data||!Array.isArray(data.products)||!Array.isArray(data.categories))throw new Error("Catalogue V2 absent");

  Object.keys(CENTRAL_PROFILE_BY_ID).forEach(k=>delete CENTRAL_PROFILE_BY_ID[k]);
  Object.keys(CENTRAL_PROFILE_BY_NAME).forEach(k=>delete CENTRAL_PROFILE_BY_NAME[k]);

  const active=data.products.filter(p=>p?.active!==false&&(p?.channels?.caisse!==false));
  active.forEach((p,i)=>{
   const groups=compileCentralOptions(data,p),keys=[];
   groups.forEach((g,gi)=>{
    const safeId=String(p.id??p.name??("product"+i)).replace(/[^a-zA-Z0-9_-]/g,"_");
    const key=`v2_${safeId}_${gi}`;
    const choices=(Array.isArray(g?.choices)?g.choices:[]).map(c=>Array.isArray(c)?[String(c[0]??"Option"),Number(c[1]||0)]:[String(c?.name??c?.label??"Option"),Number(c?.price??c?.extra??0)]);
    GROUPS[key]={title:String(g?.title||g?.key||"Options"),required:!!g?.required,max:Math.max(0,Number(g?.max??1)),choices};
    keys.push(key);
   });
   CENTRAL_PROFILE_BY_ID[String(p.id??"")]=keys;
   CENTRAL_PROFILE_BY_NAME[norm(p.name)]=keys;
  });

  window.PRODUCTS=active.map((p,i)=>({
   id:String(p.id??("v2-"+i)),cat:String(p.category||""),name:String(p.name||"Produit"),
   price:Number(p.price||0),image:String(p.photo||""),desc:String(p.ingredients||p.description||"")
  }));
  const used=new Set(window.PRODUCTS.map(p=>p.cat));
  const cats=data.categories.map(c=>typeof c==="string"?{name:c,active:true}:c).filter(Boolean);
  window.CATEGORIES=cats.filter(c=>c?.active!==false&&used.has(c.name)).map(c=>c.name);
  if(!window.CATEGORIES.length)window.CATEGORIES=[...new Set(window.PRODUCTS.map(p=>p.cat).filter(Boolean))];
  if(!window.CATEGORIES.includes(cat))cat=window.CATEGORIES[0]||"";
  CENTRAL_CATALOG_READY=true;
  window.BECHEFAA_CATALOG_V2_STATUS={ok:true,products:window.PRODUCTS.length,categories:window.CATEGORIES.length,updatedAt:j?.updatedAt||0};
  rc();rp();
  console.log(`BÉCHÉFAA V2: PostgreSQL chargé (${window.PRODUCTS.length} produits).`);
 }catch(e){
  CENTRAL_CATALOG_READY=true;
  window.PRODUCTS=[];window.CATEGORIES=[];cat="";
  window.BECHEFAA_CATALOG_V2_STATUS={ok:false,error:String(e?.message||e)};
  rc();rp();
  console.error("BÉCHÉFAA V2: catalogue PostgreSQL indisponible. Aucun fallback V1.",e);
 }
}
window.BECHEFAA_RELOAD_CATALOG=loadCentralCatalogMaster;

function profile(p){
 const central=centralProductFor(p);
 if(central!==null)return central;
 return [];
}
function rc(){'''
    src = re.sub(profile_pattern, replacement, src, count=1, flags=re.S)

    src = src.replace(
        '$("products").querySelectorAll(".product").forEach(b=>b.onclick=()=>openProduct(+b.dataset.id))',
        '$("products").querySelectorAll(".product").forEach(b=>b.onclick=()=>openProduct(b.dataset.id))'
    )
    src = src.replace(
        'current=window.PRODUCTS.find(x=>x.id===id); selections={}; const prof=profile(current);',
        'current=window.PRODUCTS.find(x=>String(x.id)===String(id)); selections={}; const prof=profile(current);'
    )
    src = src.replace('let ek=exactKey(current),ids=ek?WIX_GROUP_IDS[ek]:null;', 'let ek=null,ids=null;')
    src = src.replace('let opts=JSON.parse(JSON.stringify(selections)),txt=optionText(opts),u=price(current.price)+optionExtra(),ek=exactKey(current);', 'let opts=JSON.parse(JSON.stringify(selections)),txt=optionText(opts),u=price(current.price)+optionExtra(),ek=null;')
    src = src.replace(
        '/* V0.5.10 : rendu initial du catalogue restauré */\nrc();\nrp();',
        '/* Catalogue V2 : chargement PostgreSQL au démarrage */\nloadCentralCatalogMaster();'
    )

    APP_JS.write_text(src, encoding="utf-8")
    print("BÉCHÉFAA V2: Catalogue PostgreSQL = source unique POS.")


def patch_direct_product_options():
    """Fait de p.options la source d'autorité des options du produit V2.

    Le gestionnaire Catalogue central enregistre p.options dans l'ordre voulu.
    optionSelections reste seulement un secours pour les anciens enregistrements.
    Cette étape s'exécute même si le patch V2 principal était déjà présent.
    """
    try:
        src = APP_JS.read_text(encoding="utf-8")
        marker = "BECHEFAA_V2_DIRECT_PRODUCT_OPTIONS_0610"
        if marker in src:
            return
        pattern = r"function compileCentralOptions\(data,p\)\{.*?\n\}\n\nasync function loadCentralCatalogMaster"
        replacement = r'''function compileCentralOptions(data,p){ /* BECHEFAA_V2_DIRECT_PRODUCT_OPTIONS_0610 */
 const direct=Array.isArray(p?.options)?p.options:[];
 if(direct.length){
  return direct.map((g,gi)=>({
   key:String(g?.key||("v2_direct_"+gi)),
   title:String(g?.title||g?.label||g?.key||"Options"),
   required:!!g?.required,
   max:Math.max(0,Number(g?.max??1)),
   choices:(Array.isArray(g?.choices)?g.choices:[]).map(c=>{
    if(Array.isArray(c))return [String(c[0]??"Option"),Number(c[1]||0)];
    return [String(c?.name??c?.label??"Option"),Number(c?.price??c?.extra??0)];
   })
  })).filter(g=>g.choices.length);
 }
 const selections=p?.optionSelections||{},lists=data?.optionLists||{},custom=data?.optionListDefs||{};
 const selectedKeys=Object.keys(selections).filter(k=>Array.isArray(selections[k])&&selections[k].length);
 const out=[];
 for(const k of selectedKeys){
  const ids=selections[k],source=Array.isArray(lists[k])?lists[k]:[];
  const choices=ids.map(i=>source[Number(i)]).filter(Boolean).map(c=>{
   const x=Array.isArray(c)?c:[String(c?.name||c?.label||"Option"),Number(c?.price||0)];
   let label=String(x[0]??"Option");
   if(k==="garnitures"&&!/^sans\s/i.test(label))label="Sans "+label;
   return [label,Number(x[1]||0)];
  });
  if(!choices.length)continue;
  const d=custom[k]||CENTRAL_OPTION_DEFS[k]||{};
  out.push({key:"central_"+k,title:String(d.title||d.label||k),required:!!d.required,max:Math.max(0,Number(d.max??1)),choices});
 }
 return out;
}

async function loadCentralCatalogMaster'''
        src, count = re.subn(pattern, replacement, src, count=1, flags=re.S)
        if count:
            APP_JS.write_text(src, encoding="utf-8")
            print("BÉCHÉFAA V2: p.options du Catalogue central = source d'autorité POS.")
        else:
            print("BÉCHÉFAA V2: compileCentralOptions() introuvable pour mise à jour directe.")
    except Exception as exc:
        print("BÉCHÉFAA V2 direct options patch ignoré:", exc)


try:
    bind_postgresql_runtime()
    patch_pos_catalog_v2()
    patch_direct_product_options()
except Exception as exc:
    print("BÉCHÉFAA V2 startup error:", exc)
