# BÉCHÉFAA V0.5.48 — injecte directement le bouton Options / Groupes dans Catalogue
from pathlib import Path

BASE = Path(__file__).resolve().parent
INDEX = BASE / "static" / "index.html"

try:
    src = INDEX.read_text(encoding="utf-8")

    # Retire les anciens chargements expérimentaux.
    src = src.replace('<script src="catalog-groups.js?v=0546"></script>\n', '')
    src = src.replace('<script src="catalog-options-workspace.js?v=0547"></script>\n', '')

    # Bouton visible injecté directement dans la barre Catalogue.
    old = '''    <div class="catalog-admin-actions">\n      <button id="catNewCategory">+ Catégorie</button>\n      <button id="catNewProduct">+ Produit</button>\n    </div>'''
    new = '''    <div class="catalog-admin-actions">\n      <button id="catNewCategory">+ Catégorie</button>\n      <button id="catNewProduct">+ Produit</button>\n      <button id="catalogOptionsTab" type="button">⚙ Options / Groupes</button>\n    </div>'''
    if 'id="catalogOptionsTab"' not in src and old in src:
        src = src.replace(old, new, 1)

    # Charge l'espace de travail après le HTML du catalogue.
    tag = '<script src="catalog-options-workspace.js?v=0548"></script>'
    if tag not in src:
        src = src.replace("</body>", tag + "\n</body>")

    INDEX.write_text(src, encoding="utf-8")
    print("BÉCHÉFAA V0.5.48: bouton Options / Groupes injecté directement.")
except Exception as exc:
    print("BÉCHÉFAA V0.5.48 bootstrap ignoré:", exc)
