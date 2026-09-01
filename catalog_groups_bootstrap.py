# BÉCHÉFAA V0.5.46 — charge la bibliothèque de groupes sans toucher au moteur POS
from pathlib import Path

BASE = Path(__file__).resolve().parent
INDEX = BASE / "static" / "index.html"

try:
    src = INDEX.read_text(encoding="utf-8")
    tag = '<script src="catalog-groups.js?v=0546"></script>'
    if tag not in src:
        src = src.replace("</body>", tag + "\n</body>")
        INDEX.write_text(src, encoding="utf-8")
        print("BÉCHÉFAA V0.5.46: bibliothèque de groupes chargée.")
except Exception as exc:
    print("BÉCHÉFAA V0.5.46 bootstrap ignoré:", exc)
