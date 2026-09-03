# BÉCHÉFAA — Catalogue V2 runtime
# PostgreSQL (/api/catalog-admin) est l'unique source produits/photos/options du POS.
# Les anciens profils Wix/V1 sont supprimés du chemin d'exécution au démarrage.

from pathlib import Path
import re

BASE = Path(__file__).resolve().parent
APP_JS = BASE / "static" / "app.js"
INDEX = BASE / "static" / "index.html"


def strip_embedded_v1_catalog():
    """Retire la carte embarquée de index.html afin qu'elle ne puisse plus être
    affichée ou récupérée comme source de secours avant le chargement PostgreSQL.
    """
    try:
        src = INDEX.read_text(encoding="utf-8")
        pmark = "window.PRODUCTS="
        pstart = src.find(pmark)
        pend = src.find("];window.CATEGORIES=", pstart)
        if pstart >= 0 and pend >= 0:
            cstart = pend + 2
            cend = src.find(";</script>", cstart)
            if cend >= 0:
                src = src[:pstart] + "window.PRODUCTS=[];window.CATEGORIES=[]" + src[cend:]
        src = re.sub(r'app\.js\?v=\d+', 'app.js?v=0602', src, count=1)
        INDEX.write_text(src, encoding="utf-8")
    except Exception as exc:
        print("BÉCHÉFAA V2: nettoyage index ignoré:", exc)


def strip_wix_catalog_logic(src):
    """Supprime les groupes/options et correspondances Wix codés en dur.
    GROUPS reste un conteneur vide, rempli uniquement depuis Catalogue V2.
    """
    start = src.find("/* Choix issus du catalogue Wix Restaurants BÉCHÉFAA */")
    end = src.find("function norm(s){", start)
    if start >= 0 and end >= 0:
        src = src[:start] + "/* Catalogue V2 : aucun groupe Wix/V1 embarqué */\nconst GROUPS={};\n" + src[end:]

    # exactKey ne doit plus pouvoir réactiver des profils historiques.
    src = re.sub(
        r'function exactKey\(p\)\{.*?\n\}',
        'function exactKey(p){return null;}',
        src,
        count=1,
        flags=re.S,
    )
    return src


def patch_pos_catalog_v2():
    src = APP_JS.read_text(encoding="utf-8")
    src = strip_wix_catalog_logic(src)

    marker = "BECHEFAA_CATALOGUE_V2_SOURCE_UNIQUE"
    if marker not in src:
        profile_pattern = r"function profile\(p\)\{.*?\n\}\nfunction rc\(\)\{"
        if not re.search(profile_pattern, src, flags=re.S):
            print("BÉCHÉFAA V2: bloc profile() introuvable, aucun pont V2 appliqué.")
            APP_JS.write_text(src, encoding="utf-8")
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

function selectionKeyForGroup(p,g,data){
 const selections=p?.optionSelections||{},custom=data?.optionListDefs||{};
 const gkey=String(g?.key||"").replace(/^central_/,"");
 if(Object.prototype.hasOwnProperty.call(selections,gkey))return gkey;
 const title=norm(g?.title||g?.key||"");
 for(const k of Object.keys(selections)){
  const d=custom[k]||CENTRAL_OPTION_DEFS[k]||{};
  if(norm(d.title||d.label||k)===title)return k;
 }
 return null;
}

function compileCentralOptions(data,p){
 const selections=p?.optionSelections||{},lists=data?.optionLists||{},custom=data?.optionListDefs||{};
 const selectedKeys=Object.keys(selections).filter(k=>Array.isArray(selections[k])&&selections[k].length);
 if(!selectedKeys.length)return [];

 // L'ordre visible dans le Catalogue V2 (p.options central_*) est prioritaire.
 // Les anciens groupes non central_* sont ignorés définitivement.
 const ordered=[];
 for(const g of (Array.isArray(p?.options)?p.options:[])){
  const k=selectionKeyForGroup(p,g,data);
  if(k&&selectedKeys.includes(k)&&!ordered.includes(k))ordered.push(k);
 }
 for(const k of selectedKeys)if(!ordered.includes(k))ordered.push(k);

 const out=[];
 for(const k of ordered){
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

async function loadCentralCatalogMaster(){
 try{
  const r=await fetch("/api/catalog-admin?t="+Date.now(),{cache:"no-store"});
  if(!r.ok)throw new Error("HTTP "+r.status);
  const j=await r.json(),data=j?.data;
  if(!data||!Array.isArray(data.products)||!Array.isArray(data.categories))throw new Error("Catalogue V2 absent");

  Object.keys(CENTRAL_PROFILE_BY_ID).forEach(k=>delete CENTRAL_PROFILE_BY_ID[k]);
  Object.keys(CENTRAL_PROFILE_BY_NAME).forEach(k=>delete CENTRAL_PROFILE_BY_NAME[k]);
  Object.keys(GROUPS).forEach(k=>delete GROUPS[k]);

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
   price:Number(p.price||0),image:String(p.photo||""),desc:String(p.ingredients||"")
  }));
  const used=new Set(window.PRODUCTS.map(p=>p.cat));
  window.CATEGORIES=data.categories.filter(c=>c?.active!==false&&used.has(c.name)).map(c=>c.name);
  if(!window.CATEGORIES.includes(cat))cat=window.CATEGORIES[0]||"";
  CENTRAL_CATALOG_READY=true;
  window.BECHEFAA_CATALOG_V2_STATUS={ok:true,source:"postgres-v2-only",products:window.PRODUCTS.length,categories:window.CATEGORIES.length,updatedAt:j?.updatedAt||0};
  rc();rp();
  console.log(`BÉCHÉFAA V2 ONLY: PostgreSQL chargé (${window.PRODUCTS.length} produits).`);
 }catch(e){
  CENTRAL_CATALOG_READY=true;window.PRODUCTS=[];window.CATEGORIES=[];cat="";
  window.BECHEFAA_CATALOG_V2_STATUS={ok:false,source:"postgres-v2-only",error:String(e?.message||e)};
  rc();rp();console.error("BÉCHÉFAA V2: PostgreSQL indisponible. Aucun fallback Wix/V1.",e);
 }
}
window.BECHEFAA_RELOAD_CATALOG=loadCentralCatalogMaster;

function profile(p){
 const central=centralProductFor(p);
 return central!==null?central:[];
}
function rc(){'''
        src = re.sub(profile_pattern, replacement, src, count=1, flags=re.S)

    src = src.replace('$("products").querySelectorAll(".product").forEach(b=>b.onclick=()=>openProduct(+b.dataset.id))','$("products").querySelectorAll(".product").forEach(b=>b.onclick=()=>openProduct(b.dataset.id))')
    src = src.replace('current=window.PRODUCTS.find(x=>x.id===id); selections={}; const prof=profile(current);','current=window.PRODUCTS.find(x=>String(x.id)===String(id)); selections={}; const prof=profile(current);')
    src = src.replace('let ek=exactKey(current),ids=ek?WIX_GROUP_IDS[ek]:null;', 'let ek=null,ids=null;')
    src = src.replace('let opts=JSON.parse(JSON.stringify(selections)),txt=optionText(opts),u=price(current.price)+optionExtra(),ek=exactKey(current);','let opts=JSON.parse(JSON.stringify(selections)),txt=optionText(opts),u=price(current.price)+optionExtra(),ek=null;')
    src = src.replace('line.wixModifierGroupIds=ek?(WIX_GROUP_IDS[ek]||[]):[]','line.wixModifierGroupIds=[]')
    src = src.replace('wixModifierGroupIds:ek?(WIX_GROUP_IDS[ek]||[]):[]','wixModifierGroupIds:[]')
    src = src.replace('/* V0.5.10 : rendu initial du catalogue restauré */\nrc();\nrp();','/* Catalogue V2 : PostgreSQL uniquement */\nloadCentralCatalogMaster();')

    APP_JS.write_text(src, encoding="utf-8")
    print("BÉCHÉFAA V2 ONLY: Wix/V1 retiré du catalogue POS.")


try:
    strip_embedded_v1_catalog()
    patch_pos_catalog_v2()
except Exception as exc:
    print("BÉCHÉFAA V2 deep-clean error:", exc)
