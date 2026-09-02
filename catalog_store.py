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
except Exception:  # pragma: no cover - local fallback can work without psycopg
    psycopg = None


POSTGRES_ENV_KEYS = (
    "DATABASE_URL",
    "POSTGRESQL_ADDON_URI",
    "POSTGRES_URL",
)


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
            row = conn.execute(
                "SELECT data_json, updated_at, schema_version FROM catalog_admin_v2 WHERE id=1"
            ).fetchone()
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

    def seed_from_legacy_sqlite(self, legacy_path=None):
        """Copy the legacy catalog_admin row once, without modifying the legacy table.

        This is deliberately explicit and idempotent: if V2 already has data, no copy occurs.
        It will be called only by a controlled migration step, never as an import side effect.
        """
        current, _, _ = self.load()
        if current is not None:
            return False

        path = Path(legacy_path or self.sqlite_path)
        if not path.exists():
            return False
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT data_json FROM catalog_admin WHERE id=1"
            ).fetchone()
        except sqlite3.OperationalError:
            row = None
        finally:
            conn.close()
        if not row:
            return False
        data = json.loads(row["data_json"] or "{}")
        self.save(data, schema_version=int(data.get("schemaVersion") or 1))
        return True
