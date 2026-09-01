# BÉCHÉFAA POS — correctifs de démarrage autonomes
# 1) Catalogue central -> options POS
# 2) Catalogue public de secours après redéploiement Clever Cloud

from pathlib import Path

BASE = Path(__file__).resolve().parent
APP_JS = BASE / "static" / "app.js"
APP_PY = BASE / "app.py"


def patch_pos_options():
    try:
        src = APP_JS.read_text(encoding="utf-8")
        if "async function loadCentralCatalogOptions()" in src and "CENTRAL_PROFILE_BY_ID" in src:
            return

        needle = "function profile(p){\n let ek=exactKey(p);"
        if needle not in src:
            print("BÉCHÉFAA POS options: point d'injection introuvable.")
            return

        replacement = r'''/* === V0.5.40 CENTRAL POS OPTIONS === */
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
     GROUPS[key]={title:String(g?.title||g?.key||"Options"),required:!!g?.required,max:Math.max(0,Number(g?.max??1)),choices};
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

        APP_JS.write_text(src.replace(needle, replacement, 1), encoding="utf-8")
        print("BÉCHÉFAA POS options: liaison Catalogue central activée V0.5.40.")
    except Exception as exc:
        print("BÉCHÉFAA POS options: correctif ignoré:", exc)


def patch_public_catalog_fallback():
    try:
        src = APP_PY.read_text(encoding="utf-8")
        if "BECHEFAA_PUBLIC_CATALOG_FALLBACK_V0540" in src:
            return

        needle = '''        if not row:\n            return jsonify({\n                "categories": [],\n                "products": [],\n                "updatedAt": 0\n            })'''

        replacement = '''        if not row:\n            # BECHEFAA_PUBLIC_CATALOG_FALLBACK_V0540\n            # Clever Cloud peut redémarrer avec une base locale vide.\n            # Le site public doit continuer à afficher la carte embarquée dans le POS.\n            try:\n                index_path = BASE / "static" / "index.html"\n                html = index_path.read_text(encoding="utf-8")\n                pmark = "window.PRODUCTS="\n                pstart = html.find(pmark)\n                pend = html.find("];window.CATEGORIES=", pstart)\n                cmark = "window.CATEGORIES="\n                cstart = html.find(cmark, pend)\n                cend = html.find(";</script>", cstart)\n                if pstart >= 0 and pend >= 0 and cstart >= 0 and cend >= 0:\n                    legacy_products = json.loads(html[pstart + len(pmark):pend + 1])\n                    legacy_categories = json.loads(html[cstart + len(cmark):cend])\n                    categories = [{"id":"legacy-"+str(i), "name":name, "active":True} for i,name in enumerate(legacy_categories)]\n                    products = []\n                    for p in legacy_products:\n                        products.append({\n                            "id": str(p.get("id","")),\n                            "name": p.get("name","Produit"),\n                            "category": p.get("cat",""),\n                            "price": float(p.get("price") or 0),\n                            "active": True,\n                            "photo": p.get("image", ""),\n                            "ingredients": p.get("desc", ""),\n                            "options": [],\n                            "channels": {"caisse":True,"site":True,"ubereats":False,"deliveroo":False},\n                            "schedule": "toujours"\n                        })\n                    return jsonify({"categories":categories,"products":products,"updatedAt":0,"fallback":True})\n            except Exception as e:\n                print("Catalogue public de secours:", e)\n            return jsonify({"categories": [], "products": [], "updatedAt": 0})'''

        if needle not in src:
            print("BÉCHÉFAA site fallback: point d'injection introuvable.")
            return

        APP_PY.write_text(src.replace(needle, replacement, 1), encoding="utf-8")
        print("BÉCHÉFAA site fallback: carte de secours activée V0.5.40.")
    except Exception as exc:
        print("BÉCHÉFAA site fallback: correctif ignoré:", exc)


patch_pos_options()
patch_public_catalog_fallback()
