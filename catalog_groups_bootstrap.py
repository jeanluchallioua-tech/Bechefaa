# BÉCHÉFAA — point d'entrée Catalogue V2
# Le POS ne doit plus embarquer ni démarrer depuis la carte Wix/V1.
# PostgreSQL V2 est préchargé avant l'exécution du moteur de caisse.

from pathlib import Path
import re

BASE = Path(__file__).resolve().parent
INDEX = BASE / "static" / "index.html"
APP_JS = BASE / "static" / "app.js"

try:
    src = INDEX.read_text(encoding="utf-8")

    # 1) Retire physiquement la carte Wix/V1 embarquée de la page servie.
    embedded_pattern = r'<script>window\.PRODUCTS=.*?;window\.CATEGORIES=.*?</script>'
    src, removed = re.subn(
        embedded_pattern,
        '<script>window.PRODUCTS=[];window.CATEGORIES=[];</script>',
        src,
        count=1,
        flags=re.S,
    )

    # 2) Identité V2 visible dans le POS.
    src = src.replace('POS V0.5.38 CLEAN · TABLETTE STABLE', 'POS V2 · POSTGRESQL')
    src = src.replace('● 85 produits Wix<br><small>After work exclu</small>', '● Catalogue V2<br><small>PostgreSQL central</small>')
    src = src.replace('Carte Wix · groupes exacts + cache hors connexion', 'Catalogue central V2 · PostgreSQL')

    # 3) Supprime les anciens scripts expérimentaux du Catalogue central.
    for tag in (
        '<script src="catalog-groups.js?v=0546"></script>\n',
        '<script src="catalog-options-workspace.js?v=0547"></script>\n',
        '<script src="catalog-options-workspace.js?v=0548"></script>\n',
    ):
        src = src.replace(tag, '')

    src = src.replace('      <button id="catalogOptionsTab" type="button">⚙ Options / Groupes</button>\n', '')
    src = src.replace('      <a id="catalogOptionsManager" href="/options.html">⚙ Listes d\'options</a>\n', '')

    anchor = '      <button id="catNewProduct">+ Produit</button>\n'
    link = anchor + '      <a id="catalogOptionsManager" href="/options.html" style="display:inline-block;padding:9px 12px;border:1px solid #bbb;border-radius:8px;text-decoration:none;color:#111;background:#fff;font-weight:700">⚙ Listes d\'options</a>\n'
    if 'id="catalogOptionsManager"' not in src and anchor in src:
        src = src.replace(anchor, link, 1)

    # 4) Le moteur démarre seulement après préchargement PostgreSQL V2.
    preload_tag = '<script src="v2-preload-v2.js?v=0611"></script>'
    src = re.sub(
        r'<script type="module" src="v2-preload\.js\?v=[^"]+"></script>',
        preload_tag,
        src,
        count=1,
    )
    src = re.sub(
        r'<script src="v2-preload-v2\.js\?v=[^"]+"></script>',
        preload_tag,
        src,
        count=1,
    )
    src = re.sub(
        r'<script src="app\.js\?v=[^"]+"></script><script src="cloud\.js\?v=[^"]+"></script>',
        preload_tag,
        src,
        count=1,
    )

    INDEX.write_text(src, encoding="utf-8")
    print(f"BÉCHÉFAA V2: Wix retiré={removed}, préchargeur PostgreSQL robuste actif.")
except Exception as exc:
    print("BÉCHÉFAA V2 bootstrap ignoré:", exc)

# 5) app.js est chargé dynamiquement APRES le préchargement PostgreSQL.
try:
    js = APP_JS.read_text(encoding="utf-8")
    marker = "BECHEFAA_V2_DOM_READY_INIT"
    if marker not in js:
        old_start = 'document.addEventListener("DOMContentLoaded",()=>{\n'
        new_start = 'const __BECHEFAA_MAIN_INIT=()=>{ /* BECHEFAA_V2_DOM_READY_INIT */\n'
        old_end = 'boards();\n\n});\n\n/* V0.5.2 : navigation tablette toujours disponible */'
        new_end = 'boards();\n\n};\nif(document.readyState==="loading") document.addEventListener("DOMContentLoaded",__BECHEFAA_MAIN_INIT,{once:true}); else __BECHEFAA_MAIN_INIT();\n\n/* V0.5.2 : navigation tablette toujours disponible */'
        if old_start in js and old_end in js:
            js = js.replace(old_start, new_start, 1)
            js = js.replace(old_end, new_end, 1)
            APP_JS.write_text(js, encoding="utf-8")
            print("BÉCHÉFAA V2: initialisation POS compatible précharge PostgreSQL.")
except Exception as exc:
    print("BÉCHÉFAA V2 init patch ignoré:", exc)

# 6) Correctif impératif du chemin Produit -> Options -> Panier.
try:
    js = APP_JS.read_text(encoding="utf-8")
    js = js.replace(
        '$("products").querySelectorAll(".product").forEach(b=>b.onclick=()=>openProduct(+b.dataset.id))',
        '$("products").querySelectorAll(".product").forEach(b=>b.onclick=()=>openProduct(String(b.dataset.id)))'
    )
    js = js.replace(
        'current=window.PRODUCTS.find(x=>x.id===id); selections={}; const prof=profile(current);',
        'current=window.PRODUCTS.find(x=>String(x.id)===String(id)); selections={}; const prof=current?profile(current):[];'
    )
    js = re.sub(
        r'const price=p=>\["UBER EATS","DELIVEROO"\]\.includes\(ch\)\?\+\(p\*1\.15\)\.toFixed\(2\):p;',
        'const price=p=>{const n=Number(String(p??0).replace(",","."))||0;return ["UBER EATS","DELIVEROO"].includes(ch)?+(n*1.15).toFixed(2):n;}',
        js,
        count=1,
    )
    js = js.replace(
        'let u=price(current.price),x=cart.find(i=>i.id===current.id&&!i.optionsText&&i.unit===u);',
        'let u=Number(price(current.price))||0,x=cart.find(i=>String(i.id)===String(current.id)&&!i.optionsText&&Number(i.unit)===u);'
    )
    js = js.replace(
        'let opts=JSON.parse(JSON.stringify(selections)),txt=optionText(opts),u=price(current.price)+optionExtra(),ek=null;',
        'let opts=JSON.parse(JSON.stringify(selections)),txt=optionText(opts),u=(Number(price(current.price))||0)+(Number(optionExtra())||0),ek=null;'
    )
    APP_JS.write_text(js, encoding="utf-8")
    print("BÉCHÉFAA V2: ouverture options + prix panier corrigés.")
except Exception as exc:
    print("BÉCHÉFAA V2 product/cart patch ignoré:", exc)

# 7) Nettoyage définitif des cartes/options Wix historiques dans app.js.
# GROUPS reste comme conteneur technique vide : il est rempli uniquement par V2.
try:
    js = APP_JS.read_text(encoding="utf-8")
    marker = "BECHEFAA_V2_WIX_OPTIONS_REMOVED"
    if marker not in js:
        pattern = r'/\* Choix issus du catalogue Wix Restaurants BÉCHÉFAA \*/.*?function norm\(s\)\{'
        replacement = '/* BECHEFAA_V2_WIX_OPTIONS_REMOVED */\nconst GROUPS={};\nfunction norm(s){'
        js, count = re.subn(pattern, replacement, js, count=1, flags=re.S)
        if count:
            js = re.sub(r'function exactKey\(p\)\{.*?\n\}', '', js, count=1, flags=re.S)
            APP_JS.write_text(js, encoding="utf-8")
            print("BÉCHÉFAA V2: cartes d'options Wix/EXACT/WIX_GROUP_IDS supprimées.")
        else:
            print("BÉCHÉFAA V2: bloc Wix historique déjà absent ou introuvable.")
except Exception as exc:
    print("BÉCHÉFAA V2 Wix cleanup ignoré:", exc)

# 8) IMPORTANT : le chargeur interne du POS doit conserver p.options.
# Le préchargeur les possède déjà, mais loadCentralCatalogMaster() recréait ensuite
# window.PRODUCTS sans options, ce qui expliquait leur disparition après nettoyage Wix.
try:
    js = APP_JS.read_text(encoding="utf-8")
    marker = "BECHEFAA_V2_KEEP_DIRECT_OPTIONS_0611"
    if marker not in js and "BECHEFAA_CATALOGUE_V2_SOURCE_UNIQUE" in js:
        old = 'price:Number(p.price||0),image:String(p.photo||""),desc:String(p.ingredients||p.description||"")'
        new = 'price:Number(p.price||0),image:String(p.photo||""),desc:String(p.ingredients||p.description||""),options:Array.isArray(p.options)?p.options:[],optionSelections:p.optionSelections||{} /* BECHEFAA_V2_KEEP_DIRECT_OPTIONS_0611 */'
        if old in js:
            js = js.replace(old, new, 1)
        # compileCentralOptions doit lire p.options en premier, dans son ordre exact.
        pattern = r'function compileCentralOptions\(data,p\)\{.*?\n\}\n\nasync function loadCentralCatalogMaster'
        replacement = r'''function compileCentralOptions(data,p){
 const direct=Array.isArray(p?.options)?p.options:[];
 if(direct.length){
  return direct.map((g,gi)=>({
   key:String(g?.key||("v2_direct_"+gi)),
   title:String(g?.title||g?.label||g?.key||"Options"),
   required:!!g?.required,
   max:Math.max(0,Number(g?.max??1)),
   choices:(Array.isArray(g?.choices)?g.choices:[]).map(c=>Array.isArray(c)
     ?[String(c[0]??"Option"),Number(c[1]||0)]
     :[String(c?.name??c?.label??"Option"),Number(c?.price??c?.extra??0)])
  })).filter(g=>g.choices.length);
 }
 return [];
}

async function loadCentralCatalogMaster'''
        js, count = re.subn(pattern, replacement, js, count=1, flags=re.S)
        if count:
            APP_JS.write_text(js, encoding="utf-8")
            print("BÉCHÉFAA V2: p.options conservé et utilisé directement par le POS.")
        else:
            print("BÉCHÉFAA V2: compileCentralOptions introuvable pour raccord direct.")
except Exception as exc:
    print("BÉCHÉFAA V2 direct options raccord ignoré:", exc)
