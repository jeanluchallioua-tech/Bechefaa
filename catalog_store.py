"""Storage adapter for the BÉCHÉFAA central catalogue.

Only the catalogue uses this adapter during the refactor. Orders/clients remain untouched
until the catalogue path is validated. PostgreSQL is preferred when Clever Cloud exposes
its add-on URI; SQLite remains a deterministic fallback for local tests.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

try:
    import psycopg
except Exception:  # pragma: no cover
    psycopg = None

POSTGRES_ENV_KEYS = ("DATABASE_URL", "POSTGRESQL_ADDON_URI", "POSTGRES_URL")


def _postgres_url(explicit=None):
    url = explicit
    if not url:
        for key in POSTGRES_ENV_KEYS:
            if os.getenv(key):
                url = os.getenv(key)
                break
    if url and url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url if url and url.startswith("postgresql://") else None


class CatalogStore:
    def __init__(self, postgres_url=None, sqlite_path=None):
        self.postgres_url = _postgres_url(postgres_url)
        self.sqlite_path = Path(sqlite_path or os.getenv("BECHEFAA_DB", "bechefaa.db"))

    @property
    def backend(self):
        return "postgresql" if self.postgres_url else "sqlite"

    def _connect_pg(self):
        if psycopg is None:
            raise RuntimeError("psycopg indisponible alors qu'une URL PostgreSQL est configurée")
        return psycopg.connect(self.postgres_url)

    def _connect_sqlite(self):
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self):
        if self.postgres_url:
            with self._connect_pg() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS catalog_admin_v2 (
                            id SMALLINT PRIMARY KEY CHECK (id=1),
                            data_json JSONB NOT NULL,
                            updated_at BIGINT NOT NULL,
                            schema_version INTEGER NOT NULL DEFAULT 1
                        )
                    """)
                conn.commit()
            return
        with self._connect_sqlite() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS catalog_admin_v2 (
                    id INTEGER PRIMARY KEY CHECK (id=1),
                    data_json TEXT NOT NULL,
                    updated_at INTEGER NOT NULL,
                    schema_version INTEGER NOT NULL DEFAULT 1
                )
            """)
            conn.commit()

    def load(self):
        self.ensure_schema()
        if self.postgres_url:
            with self._connect_pg() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT data_json, updated_at, schema_version FROM catalog_admin_v2 WHERE id=1")
                    row = cur.fetchone()
            if not row:
                return None, 0, 1
            data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            return data, int(row[1] or 0), int(row[2] or 1)
        with self._connect_sqlite() as conn:
            row = conn.execute("SELECT data_json, updated_at, schema_version FROM catalog_admin_v2 WHERE id=1").fetchone()
        if not row:
            return None, 0, 1
        return json.loads(row["data_json"]), int(row["updated_at"] or 0), int(row["schema_version"] or 1)

    def save(self, data, schema_version=1):
        self.ensure_schema()
        now = int(time.time() * 1000)
        if self.postgres_url:
            payload = json.dumps(data, ensure_ascii=False)
            with self._connect_pg() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO catalog_admin_v2(id, data_json, updated_at, schema_version)
                        VALUES(1, %s::jsonb, %s, %s)
                        ON CONFLICT(id) DO UPDATE SET
                            data_json=EXCLUDED.data_json,
                            updated_at=EXCLUDED.updated_at,
                            schema_version=EXCLUDED.schema_version
                    """, (payload, now, int(schema_version or 1)))
                conn.commit()
            return now
        payload = json.dumps(data, ensure_ascii=False)
        with self._connect_sqlite() as conn:
            conn.execute("""
                INSERT INTO catalog_admin_v2(id, data_json, updated_at, schema_version)
                VALUES(1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    data_json=excluded.data_json,
                    updated_at=excluded.updated_at,
                    schema_version=excluded.schema_version
            """, (payload, now, int(schema_version or 1)))
            conn.commit()
        return now

    def load_legacy(self):
        """Read legacy catalog_admin from the SAME backend, without modifying it."""
        if self.postgres_url:
            try:
                with self._connect_pg() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT data_json, updated_at FROM catalog_admin WHERE id=1")
                        row = cur.fetchone()
            except Exception:
                return None, 0
            if not row:
                return None, 0
            data = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
            return data, int(row[1] or 0)
        if not self.sqlite_path.exists():
            return None, 0
        conn = self._connect_sqlite()
        try:
            row = conn.execute("SELECT data_json, updated_at FROM catalog_admin WHERE id=1").fetchone()
        except sqlite3.OperationalError:
            row = None
        finally:
            conn.close()
        if not row:
            return None, 0
        return json.loads(row["data_json"] or "{}"), int(row["updated_at"] or 0)

    def seed_from_legacy(self, force=False):
        """Copy legacy catalogue into V2 explicitly. Never deletes/changes legacy data."""
        current, _, _ = self.load()
        if current is not None and not force:
            return {"copied": False, "reason": "v2_not_empty"}
        data, legacy_updated_at = self.load_legacy()
        if not isinstance(data, dict):
            return {"copied": False, "reason": "legacy_missing"}
        new_updated_at = self.save(data, schema_version=int(data.get("schemaVersion") or 1))
        return {
            "copied": True,
            "legacyUpdatedAt": legacy_updated_at,
            "updatedAt": new_updated_at,
            "backend": self.backend,
        }
