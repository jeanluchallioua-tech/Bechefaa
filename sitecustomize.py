# BÉCHÉFAA POS — démarrage V2
# PostgreSQL est la source persistante. Aucun fallback catalogue Wix/V1.

import os
import sys
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
APP_PY = BASE / "app.py"
INDEX_HTML = BASE / "static" / "index.html"


def force_postgresql_runtime():
    """Fait en sorte que l'ancien `import sqlite3` de app.py reçoive dbcompat."""
    if not (os.getenv("POSTGRESQL_ADDON_URI") or os.getenv("DATABASE_URL")):
        print("BÉCHÉFAA DB: aucune URI PostgreSQL, mode local SQLite conservé.")
        return
    try:
        import dbcompat
        sys.modules["sqlite3"] = dbcompat
        print("BÉCHÉFAA DB: backend PostgreSQL forcé avant import de app.py.")
    except Exception as exc:
        print("BÉCHÉFAA DB: impossible de forcer PostgreSQL:", exc)


def purge_embedded_wix_catalog():
    """Retire physiquement la vieille carte Wix embarquée de la page servie.

    Le HTML ne fournit plus aucun produit, prix, photo ou catégorie. Le POS
    démarre avec des tableaux vides, puis v2-preload-v2.js remplit la carte
    exclusivement depuis /api/catalog-admin (PostgreSQL).
    """
    try:
        src = INDEX_HTML.read_text(encoding="utf-8")
        src, removed = re.subn(
            r'<script>window\.PRODUCTS=.*?;window\.CATEGORIES=.*?</script>',
            '<script>window.PRODUCTS=[];window.CATEGORIES=[];</script>',
            src,
            count=1,
            flags=re.S,
        )
        src = src.replace('POS V0.5.38 CLEAN · TABLETTE STABLE', 'POS V2 · POSTGRESQL')
        src = src.replace('● 85 produits Wix<br><small>After work exclu</small>', '● Catalogue V2<br><small>PostgreSQL central</small>')
        src = src.replace('Carte Wix · groupes exacts + cache hors connexion', 'Catalogue central V2 · PostgreSQL')
        INDEX_HTML.write_text(src, encoding="utf-8")
        print(f"BÉCHÉFAA CLEAN: catalogue Wix embarqué supprimé={removed}.")
    except Exception as exc:
        print("BÉCHÉFAA CLEAN: purge catalogue Wix ignorée:", exc)


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
purge_embedded_wix_catalog()
patch_public_catalog_v2()

# Dernière étape de démarrage : branchement direct du POS sur p.options de catalog_admin_v2.
# Ce module modifie uniquement static/app.js avant que Flask ne le serve.
try:
    import pos_v2_direct_options
    print("BÉCHÉFAA V2: branchement direct p.options activé.")
except Exception as exc:
    print("BÉCHÉFAA V2: branchement direct p.options ignoré:", exc)

# Audit commandes/clients : PostgreSQL devient l'unique source persistante.
# Le navigateur ne garde plus qu'un cache mémoire d'affichage.
try:
    import orders_single_source_bootstrap
    print("BÉCHÉFAA ORDERS: source unique PostgreSQL activée.")
except Exception as exc:
    print("BÉCHÉFAA ORDERS: bootstrap source unique ignoré:", exc)

# Intégrité UI Historique : fermeture Voir + édition rechargée depuis la base serveur.
try:
    import orders_ui_integrity_bootstrap
    print("BÉCHÉFAA ORDERS UI: correctifs Voir/Modifier activés.")
except Exception as exc:
    print("BÉCHÉFAA ORDERS UI: bootstrap ignoré:", exc)
