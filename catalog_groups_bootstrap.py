# BÉCHÉFAA — point d'entrée Catalogue V2
# Le POS ne doit plus embarquer ni démarrer depuis la carte Wix/V1.
# PostgreSQL V2 est préchargé avant l'exécution du moteur de caisse.

from pathlib import Path
import re

BASE = Path(__file__).resolve().parent
INDEX = BASE / "static" / "index.html"

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
    # Compatible avec un index encore ancien (app.js + cloud.js) OU avec
    # le préchargeur V2 précédent déjà installé.
    preload_tag = '<script src="v2-preload-v2.js?v=0605"></script>'
    src = re.sub(
        r'<script type="module" src="v2-preload\.js\?v=[^"]+"></script>',
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
