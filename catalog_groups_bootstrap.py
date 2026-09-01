# BÉCHÉFAA V0.5.49 — HOTFIX sécurité : désactive l'espace Options expérimental
# Objectif : ne plus toucher au moteur POS ni charger de JavaScript expérimental.
from pathlib import Path

BASE = Path(__file__).resolve().parent
INDEX = BASE / "static" / "index.html"

try:
    src = INDEX.read_text(encoding="utf-8")

    # Nettoyage des scripts expérimentaux éventuellement injectés au démarrage.
    for tag in (
        '<script src="catalog-groups.js?v=0546"></script>\n',
        '<script src="catalog-options-workspace.js?v=0547"></script>\n',
        '<script src="catalog-options-workspace.js?v=0548"></script>\n',
    ):
        src = src.replace(tag, '')

    # Nettoyage du bouton expérimental éventuellement injecté.
    src = src.replace('      <button id="catalogOptionsTab" type="button">⚙ Options / Groupes</button>\n', '')

    INDEX.write_text(src, encoding="utf-8")
    print("BÉCHÉFAA V0.5.49: espace Options expérimental désactivé, POS stable conservé.")
except Exception as exc:
    print("BÉCHÉFAA V0.5.49 hotfix ignoré:", exc)
