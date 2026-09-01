# BÉCHÉFAA V0.5.47 — espace Options / Groupes indépendant du moteur POS
from pathlib import Path

BASE = Path(__file__).resolve().parent
INDEX = BASE / "static" / "index.html"

try:
    src = INDEX.read_text(encoding="utf-8")
    # Retire l'ancien helper expérimental s'il a été injecté par un précédent démarrage.
    src = src.replace('<script src="catalog-groups.js?v=0546"></script>\n', '')
    tag = '<script src="catalog-options-workspace.js?v=0547"></script>'
    if tag not in src:
        src = src.replace("</body>", tag + "\n</body>")
        INDEX.write_text(src, encoding="utf-8")
        print("BÉCHÉFAA V0.5.47: espace Options / Groupes chargé.")
except Exception as exc:
    print("BÉCHÉFAA V0.5.47 bootstrap ignoré:", exc)
