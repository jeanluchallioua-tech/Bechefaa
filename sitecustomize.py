# BÉCHÉFAA POS — correctifs de démarrage autonomes
# V0.5.44 : ne plus modifier app.js ici ; startup_patch.py est l'unique source POS.

from pathlib import Path

BASE = Path(__file__).resolve().parent
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


def patch_public_catalog_fallback():
    try:
        src = APP_PY.read_text(encoding="utf-8")
        if "BECHEFAA_PUBLIC_CATALOG_FALLBACK_V0541" in src or "BECHEFAA_PUBLIC_CATALOG_FALLBACK_V0540" in src:
            return
        needle = '''        if not row:\n            return jsonify({\n                "categories": [],\n                "products": [],\n                "updatedAt": 0\n            })'''
        replacement = '''        if not row:\n            # BECHEFAA_PUBLIC_CATALOG_FALLBACK_V0541\n            try:\n                index_path = BASE / "static" / "index.html"\n                html = index_path.read_text(encoding="utf-8")\n                pmark = "window.PRODUCTS="\n                pstart = html.find(pmark)\n                pend = html.find("];window.CATEGORIES=", pstart)\n                cmark = "window.CATEGORIES="\n                cstart = html.find(cmark, pend)\n                cend = html.find(";</script>", cstart)\n                if pstart >= 0 and pend >= 0 and cstart >= 0 and cend >= 0:\n                    legacy_products = json.loads(html[pstart + len(pmark):pend + 1])\n                    legacy_categories = json.loads(html[cstart + len(cmark):cend])\n                    categories = [{"id":"legacy-"+str(i), "name":name, "active":True} for i,name in enumerate(legacy_categories)]\n                    products = []\n                    for p in legacy_products:\n                        products.append({"id":str(p.get("id","")),"name":p.get("name","Produit"),"category":p.get("cat",""),"price":float(p.get("price") or 0),"active":True,"photo":p.get("image", ""),"ingredients":p.get("desc", ""),"options":[],"channels":{"caisse":True,"site":True,"ubereats":False,"deliveroo":False},"schedule":"toujours"})\n                    return jsonify({"categories":categories,"products":products,"updatedAt":0,"fallback":True})\n            except Exception as e:\n                print("Catalogue public de secours:", e)\n            return jsonify({"categories": [], "products": [], "updatedAt": 0})'''
        if needle in src:
            APP_PY.write_text(src.replace(needle, replacement, 1), encoding="utf-8")
            print("BÉCHÉFAA site fallback: carte de secours activée.")
    except Exception as exc:
        print("BÉCHÉFAA site fallback: correctif ignoré:", exc)


patch_database_backend()
patch_public_catalog_fallback()
