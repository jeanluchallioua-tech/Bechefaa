# BÉCHÉFAA — navigation Catalogue V2
# Ce bootstrap ne touche plus aux données ni au moteur POS.
# Il maintient uniquement le lien vers la gestion indépendante des listes d'options.

from pathlib import Path
import re

BASE = Path(__file__).resolve().parent
INDEX = BASE / "static" / "index.html"

try:
    src = INDEX.read_text(encoding="utf-8")

    # Nettoyage des anciens scripts expérimentaux.
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

    # Cache bust uniquement. Aucun fallback V1, aucun patch de données.
    src = re.sub(r'app\.js\?v=\d+', 'app.js?v=0600', src, count=1)
    INDEX.write_text(src, encoding="utf-8")
    print("BÉCHÉFAA V2: navigation options active, aucun fallback catalogue V1.")
except Exception as exc:
    print("BÉCHÉFAA V2 bootstrap ignoré:", exc)
