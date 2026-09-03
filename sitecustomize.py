# BÉCHÉFAA POS — démarrage V2
# PostgreSQL est la source persistante. Aucun fallback catalogue V1 ne doit
# recréer des produits/photos/options depuis static/index.html.

from pathlib import Path

BASE = Path(__file__).resolve().parent
APP_PY = BASE / "app.py"


def patch_database_backend():
    """Conserve la compatibilité du code historique tout en utilisant PostgreSQL
    dès que l'add-on Clever Cloud est présent.
    """
    try:
        src = APP_PY.read_text(encoding="utf-8")
        if "import dbcompat as sqlite3" in src:
            return
        needle = "import sqlite3, json, os, time"
        if needle not in src:
            print("BÉCHÉFAA DB: point d'injection introuvable.")
            return
        src = src.replace(needle, "import dbcompat as sqlite3, json, os, time", 1)
        APP_PY.write_text(src, encoding="utf-8")
        print("BÉCHÉFAA DB: PostgreSQL activé.")
    except Exception as exc:
        print("BÉCHÉFAA DB: correctif ignoré:", exc)


# IMPORTANT V2 : ne plus injecter de catalogue de secours depuis window.PRODUCTS.
# Si catalog_admin est absent, l'API doit renvoyer un catalogue vide et signaler
# le problème au lieu de réactiver silencieusement la V1.
patch_database_backend()
