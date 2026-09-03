# BÉCHÉFAA — point d'entrée Catalogue V2
# Le POS ne doit plus embarquer la carte Wix/V1 dans index.html.
# PostgreSQL V2 est chargé ensuite par startup_patch.py.

from pathlib import Path
import re

BASE = Path(__file__).resolve().parent
INDEX = BASE / "static" / "index.html"

try:
    src = INDEX.read_text(encoding="utf-8")

    # 1) Retire physiquement de la page servie la carte Wix/V1 embarquée.
    # On conserve seulement deux tableaux vides afin que le moteur POS puisse
    # démarrer, puis startup_patch.py les remplit depuis PostgreSQL V2.
    embedded_pattern = r'<script>window\.PRODUCTS=.*?;window\.CATEGORIES=.*?</script>'
    src, removed = re.subn(
        embedded_pattern,
        '<script>window.PRODUCTS=[];window.CATEGORIES=[];</script>',
        src,
        count=1,
        flags=re.S,
    )

    # 2) L'interface doit indiquer clairement la source réellement utilisée.
    src = src.replace('POS V0.5.38 CLEAN · TABLETTE STABLE', 'POS V2 · POSTGRESQL')
    src = src.replace('● 85 produits Wix<br><small>After work exclu</small>', '● Catalogue V2<br><small>PostgreSQL central</small>')
    src = src.replace('Carte Wix · groupes exacts + cache hors connexion', 'Catalogue central V2 · PostgreSQL')

    # 3) Nettoyage des anciens scripts expérimentaux uniquement.
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

    # Force le navigateur à reprendre le moteur POS V2.
    src = re.sub(r'app\.js\?v=\d+', 'app.js?v=0601', src, count=1)

    INDEX.write_text(src, encoding="utf-8")
    print(f"BÉCHÉFAA V2: carte Wix embarquée supprimée ({removed} bloc), PostgreSQL attendu.")
except Exception as exc:
    print("BÉCHÉFAA V2 bootstrap ignoré:", exc)
