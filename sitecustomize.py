# BÉCHÉFAA POS — démarrage V2
# PostgreSQL est la source persistante. Aucun fallback catalogue V1 ne doit
# recréer des produits/photos/options depuis static/index.html.

from pathlib import Path

BASE = Path(__file__).resolve().parent
APP_PY = BASE / "app.py"


def patch_database_backend():
    """Utilise PostgreSQL dès que l'add-on Clever Cloud est présent."""
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


# IMPORTANT V2 : ne plus injecter de catalogue de secours depuis window.PRODUCTS.
# Si catalog_admin est absent, l'API doit renvoyer un catalogue vide au lieu de
# réactiver silencieusement la V1.
patch_database_backend()
patch_public_catalog_v2()
