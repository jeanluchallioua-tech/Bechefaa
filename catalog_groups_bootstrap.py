# BÉCHÉFAA V0.5.50 — lien sûr vers le gestionnaire de listes d'options isolé
# Aucun JavaScript expérimental n'est chargé dans le POS.
from pathlib import Path

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

    # Supprime les anciens boutons expérimentaux s'ils existent.
    src = src.replace('      <button id="catalogOptionsTab" type="button">⚙ Options / Groupes</button>\n', '')
    src = src.replace('      <a id="catalogOptionsManager" href="/options.html">⚙ Listes d\'options</a>\n', '')

    # Ajoute uniquement un lien HTML vers une page indépendante.
    anchor = '      <button id="catNewProduct">+ Produit</button>\n'
    link = anchor + '      <a id="catalogOptionsManager" href="/options.html" style="display:inline-block;padding:9px 12px;border:1px solid #bbb;border-radius:8px;text-decoration:none;color:#111;background:#fff;font-weight:700">⚙ Listes d\'options</a>\n'
    if 'id="catalogOptionsManager"' not in src and anchor in src:
        src = src.replace(anchor, link, 1)

    INDEX.write_text(src, encoding="utf-8")
    print("BÉCHÉFAA V0.5.50: gestionnaire de listes d'options isolé disponible.")
except Exception as exc:
    print("BÉCHÉFAA V0.5.50 bootstrap ignoré:", exc)
