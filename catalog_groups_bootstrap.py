# BÉCHÉFAA V0.5.54 — lien sûr options + garde-fou produits POS
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent
INDEX = BASE / "static" / "index.html"
APP_JS = BASE / "static" / "app.js"

try:
    src = INDEX.read_text(encoding="utf-8")

    # Nettoyage des anciens scripts expérimentaux.
    for tag in (
        '<script src="catalog-groups.js?v=0546"></script>\n',
        '<script src="catalog-options-workspace.js?v=0547"></script>\n',
        '<script src="catalog-options-workspace.js?v=0548"></script>\n',
    ):
        src = src.replace(tag, '')

    # Supprime les anciens boutons expérimentaux s'ils existent.
    src = src.replace('      <button id="catalogOptionsTab" type="button">⚙ Options / Groupes</button>\n', '')
    src = src.replace('      <a id="catalogOptionsManager" href="/options.html">⚙ Listes d\'options</a>\n', '')

    # Ajoute uniquement un lien HTML vers une page indépendante.
    anchor = '      <button id="catNewProduct">+ Produit</button>\n'
    link = anchor + '      <a id="catalogOptionsManager" href="/options.html" style="display:inline-block;padding:9px 12px;border:1px solid #bbb;border-radius:8px;text-decoration:none;color:#111;background:#fff;font-weight:700">⚙ Listes d\'options</a>\n'
    if 'id="catalogOptionsManager"' not in src and anchor in src:
        src = src.replace(anchor, link, 1)

    # Garde-fou : si le Catalogue central renvoie 0 produit, ne jamais écraser
    # les 85 produits embarqués dans index.html. Cela évite un POS vide.
    js = APP_JS.read_text(encoding="utf-8")
    guard_marker = 'V0.5.54 EMPTY CENTRAL CATALOG SAFETY'
    target = 'if(!data||!Array.isArray(data.products)||!Array.isArray(data.categories))return;'
    if guard_marker not in js and target in js:
        guard = target + '\n  /* V0.5.54 EMPTY CENTRAL CATALOG SAFETY */\n  if(data.products.length===0){\n   console.warn("BÉCHÉFAA: catalogue central vide, conservation de la carte embarquée.");\n   rc();rp();\n   return;\n  }'
        js = js.replace(target, guard, 1)
        APP_JS.write_text(js, encoding="utf-8")

    # Force le navigateur à reprendre le JS corrigé après déploiement.
    src = re.sub(r'app\.js\?v=\d+', 'app.js?v=0554', src, count=1)

    INDEX.write_text(src, encoding="utf-8")
    print("BÉCHÉFAA V0.5.54: garde-fou catalogue vide actif, POS protégé.")
except Exception as exc:
    print("BÉCHÉFAA V0.5.54 bootstrap ignoré:", exc)
