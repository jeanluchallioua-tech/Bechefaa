# BÉCHÉFAA POS — démarrage V2
# PostgreSQL est la source persistante. Aucun fallback catalogue Wix/V1.

import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
APP_PY = BASE / "app.py"


def force_postgresql_runtime():
    """Fait en sorte que l'ancien `import sqlite3` de app.py reçoive dbcompat.

    sitecustomize est importé par Python avant l'application. Si Clever Cloud
    fournit POSTGRESQL_ADDON_URI (ou DATABASE_URL), on charge dbcompat puis on
    l'enregistre sous le nom de module `sqlite3` avant que app.py ne démarre.
    Cela évite tout backend SQLite local en production.
    """
    if not (os.getenv("POSTGRESQL_ADDON_URI") or os.getenv("DATABASE_URL")):
        print("BÉCHÉFAA DB: aucune URI PostgreSQL, mode local SQLite conservé.")
        return
    try:
        import dbcompat
        sys.modules["sqlite3"] = dbcompat
        print("BÉCHÉFAA DB: backend PostgreSQL forcé avant import de app.py.")
    except Exception as exc:
        print("BÉCHÉFAA DB: impossible de forcer PostgreSQL:", exc)


def patch_public_catalog_v2():
    """Empêche /api/public/catalog d'écraser les photos PostgreSQL V2 avec V1."""
    try:
        src = APP_PY.read_text(encoding="utf-8")
        start_marker = "        # Récupération automatique des photos déjà utilisées par la caisse\n"
        end_marker = "        return jsonify({\n            \"categories\": categories,\n            \"products\": products,\n            \"updatedAt\": row[\"updated_at\"]\n        })"
        start = src.find(start_marker)
        end = src.find(end_marker, start if start >= 0 else 0)
        if start >= 0 and end >= 0:
            src = src[:start] + "        # Catalogue V2 : photo/description/options proviennent exclusivement de PostgreSQL.\n\n" + src[end:]
            APP_PY.write_text(src, encoding="utf-8")
            print("BÉCHÉFAA V2: remplacement legacy des photos supprimé.")
    except Exception as exc:
        print("BÉCHÉFAA V2 public catalog: correctif ignoré:", exc)


force_postgresql_runtime()
patch_public_catalog_v2()
