# BÉCHÉFAA POS — correctifs de démarrage autonomes
# V0.5.41 : Catalogue central = source unique POS + site

from pathlib import Path

BASE = Path(__file__).resolve().parent
APP_JS = BASE / "static" / "app.js"
APP_PY = BASE / "app.py"


def patch_database_backend():
    try:
        src = APP_PY.read_text(encoding="utf-8")
        if "import dbcompat as sqlite3" in src:
            return
        needle = "import sqlite3, json, os, time"
        if needle not in src:
            print("BÉCHÉFAA DB: point d'injection introuvable.")
            return
        src = src.replace(needle, "import dbcompat as sqlite3, json, os, time", 1)
        APP_PY.write_text(src, encoding="utf-8")
        print("BÉCHÉFAA DB: backend PostgreSQL/SQLite compatible activé.")
    except Exception as exc:
        print("BÉCHÉFAA DB: correctif ignoré:", exc)


def patch_pos_catalog():
    try:
        src = APP_JS.read_text(encoding="utf-8")
        if "V0.5.41 CENTRAL CATALOG MASTER" in src:
            return

        needle = "function profile(p){\n let ek=exactKey(p);"
        if needle not in src:
            print("BÉCHÉFAA POS catalogue: point d'injection introuvable.")
            return

        replacement = r'''/* === V0.5.41 CENTRAL CATALOG MASTER === */
const CENTRAL_PROFILE_BY_ID=Object.create(null), CENTRAL_PROFILE_BY_NAME=Object.create(null);
let CENTRAL_CATALOG_READY=false;

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
  const j=await r.json(), data=j?.data, products=data?.products, categories=data?.categories;
  if(!Array.isArray(products)||!Array.isArray(categories))return;

  const posProducts=[];
  products.forEach((p,i)=>{
   const enabled=p?.active!==false && (p?.channels?.caisse!==false);
   if(!enabled)return;
   const keys=[];
   (Array.isArray(p.options)?p.options:[]).forEach((g,gi)=>{
    const safeId=String(p.id??p.name??("product"+i)).replace(/[^a-zA-Z0-9_-]/g,"_");
    const key=`central_${safeId}_${gi}`;
    const choices=(Array.isArray(g?.choices)?g.choices:[]).map(c=>{
     if(Array.isArray(c))return [String(c[0]??"Option"),Number(c[1]||0)];
     return [String(c?.name??c?.label??"Option"),Number(c?.price??c?.extra??0)];
    });
    GROUPS[key]={title:String(g?.title||g?.key||"Options"),required:!!g?.required,max:Math.max(0,Number(g?.max??1)),choices};
    keys.push(key);
   });
   CENTRAL_PROFILE_BY_ID[String(p.id??"")]=keys;
   CENTRAL_PROFILE_BY_NAME[norm(p.name)]=keys;

   const legacy=(window.PRODUCTS||[]).find(x=>String(x.id)===String(p.id)) ||
                (window.PRODUCTS||[]).find(x=>norm(x.name)===norm(p.name));
   posProducts.push({
    id:p.id??legacy?.id??("central-"+i),
    cat:String(p.category||legacy?.cat||"Sans catégorie"),
    name:String(p.name||legacy?.name||"Produit"),
    price:Number(p.price??legacy?.price??0),
    image:String(p.photo||legacy?.image||""),
    desc:String(p.ingredients||legacy?.desc||"")
   });
  });

  const activeCats=categories.filter(c=>c?.active!==false).map(c=>String(c.name||"")).filter(Boolean);
  const usedCats=[...new Set(posProducts.map(p=>p.cat).filter(Boolean))];
  window.CATEGORIES=[...new Set([...activeCats,...usedCats])];
  window.PRODUCTS=posProducts;
  if(!window.CATEGORIES.includes(cat))cat=window.CATEGORIES[0]||"";
  CENTRAL_CATALOG_READY=true;
  if(typeof rc==="function")rc();
  if(typeof rp==="function")rp();
  console.log(`BÉCHÉFAA: Catalogue central chargé dans le POS (${posProducts.length} produits).`);
 }catch(e){
  console.error("BÉCHÉFAA Catalogue central -> POS:",e);
 }
}
setTimeout(loadCentralCatalogMaster,0);

function profile(p){
 const central=centralProductFor(p);
 if(central!==null)return central;
 let ek=exactKey(p);'''

        APP_JS.write_text(src.replace(needle, replacement, 1), encoding="utf-8")
        print("BÉCHÉFAA POS: Catalogue central source unique activé V0.5.41.")
    except Exception as exc:
        print("BÉCHÉFAA POS catalogue: correctif ignoré:", exc)


def patch_public_catalog_fallback():
    try:
        src = APP_PY.read_text(encoding="utf-8")
        if "BECHEFAA_PUBLIC_CATALOG_FALLBACK_V0541" in src or "BECHEFAA_PUBLIC_CATALOG_FALLBACK_V0540" in src:
            return

        needle = '''        if not row:\n            return jsonify({\n                "categories": [],\n                "products": [],\n                "updatedAt": 0\n            })'''

        replacement = '''        if not row:\n            # BECHEFAA_PUBLIC_CATALOG_FALLBACK_V0541\n            try:\n                index_path = BASE / "static" / "index.html"\n                html = index_path.read_text(encoding="utf-8")\n                pmark = "window.PRODUCTS="\n                pstart = html.find(pmark)\n                pend = html.find("];window.CATEGORIES=", pstart)\n                cmark = "window.CATEGORIES="\n                cstart = html.find(cmark, pend)\n                cend = html.find(";</script>", cstart)\n                if pstart >= 0 and pend >= 0 and cstart >= 0 and cend >= 0:\n                    legacy_products = json.loads(html[pstart + len(pmark):pend + 1])\n                    legacy_categories = json.loads(html[cstart + len(cmark):cend])\n                    categories = [{"id":"legacy-"+str(i), "name":name, "active":True} for i,name in enumerate(legacy_categories)]\n                    products = []\n                    for p in legacy_products:\n                        products.append({"id":str(p.get("id","")),"name":p.get("name","Produit"),"category":p.get("cat",""),"price":float(p.get("price") or 0),"active":True,"photo":p.get("image", ""),"ingredients":p.get("desc", ""),"options":[],"channels":{"caisse":True,"site":True,"ubereats":False,"deliveroo":False},"schedule":"toujours"})\n                    return jsonify({"categories":categories,"products":products,"updatedAt":0,"fallback":True})\n            except Exception as e:\n                print("Catalogue public de secours:", e)\n            return jsonify({"categories": [], "products": [], "updatedAt": 0})'''

        if needle not in src:
            print("BÉCHÉFAA site fallback: point d'injection introuvable.")
            return
        APP_PY.write_text(src.replace(needle, replacement, 1), encoding="utf-8")
        print("BÉCHÉFAA site fallback: carte de secours activée V0.5.41.")
    except Exception as exc:
        print("BÉCHÉFAA site fallback: correctif ignoré:", exc)


patch_database_backend()
patch_pos_catalog()
patch_public_catalog_fallback()
