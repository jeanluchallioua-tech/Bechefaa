"""Point d'entrée WSGI dédié à BÉCHÉFAA-Caisse.

Cette branche démarre exclusivement le nouveau backend clean_caisse.
Aucun import de l'ancien app.py / Wix / V1.
"""
import os
from pathlib import Path

import psycopg

DATABASE_URL = os.getenv("POSTGRESQL_ADDON_URI") or os.getenv("DATABASE_URL")


def ensure_clean_schema():
    if not DATABASE_URL:
        return
    schema_path = Path(__file__).resolve().parent / "clean_caisse" / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(schema_sql)
        conn.commit()


ensure_clean_schema()

from clean_caisse.app import app
