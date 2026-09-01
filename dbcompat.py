"""BÉCHÉFAA database compatibility layer.

Uses Clever Cloud PostgreSQL when POSTGRESQL_ADDON_URI (or DATABASE_URL) is
available. Falls back to the historical SQLite file for local development.
The wrapper keeps the existing app.py SQL API working while translating
SQLite-style ? placeholders to psycopg %s placeholders.
"""

import os
import re
import sqlite3 as _sqlite3

POSTGRES_URL = os.getenv("POSTGRESQL_ADDON_URI") or os.getenv("DATABASE_URL")

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.errors import DuplicateColumn
except Exception:  # psycopg is optional for local SQLite use
    psycopg = None
    dict_row = None
    DuplicateColumn = Exception

Row = _sqlite3.Row
OperationalError = (_sqlite3.OperationalError, DuplicateColumn)


def _pg_sql(sql: str) -> str:
    # PostgreSQL supports most of our SQL as-is. Two compatibility fixes are
    # required: qmark parameters and safe repeated ALTER TABLE migrations.
    out = sql.replace("?", "%s")
    out = re.sub(
        r"(?i)ALTER\s+TABLE\s+([A-Za-z_][A-Za-z0-9_]*)\s+ADD\s+COLUMN\s+(?!IF\s+NOT\s+EXISTS)",
        r"ALTER TABLE \1 ADD COLUMN IF NOT EXISTS ",
        out,
    )
    return out


class _PostgresConnection:
    def __init__(self, raw):
        self._raw = raw
        self.row_factory = Row  # retained for app.py compatibility

    def execute(self, sql, params=()):
        return self._raw.execute(_pg_sql(sql), params or ())

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._raw.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self._raw.commit()
            else:
                self._raw.rollback()
        finally:
            self._raw.close()
        return False


def connect(path=None):
    if POSTGRES_URL:
        if psycopg is None:
            raise RuntimeError(
                "POSTGRESQL_ADDON_URI est défini mais psycopg n'est pas installé"
            )
        raw = psycopg.connect(POSTGRES_URL, row_factory=dict_row)
        return _PostgresConnection(raw)
    return _sqlite3.connect(path)


def backend_name():
    return "postgresql" if POSTGRES_URL else "sqlite"
