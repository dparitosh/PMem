"""PostgreSQL-backed control-plane registry; no SQLite runtime dependency."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from typing import Any

from backend.postgres_migrations import apply_migrations
from backend.platform.postgres_schema import initialise_schema


class PostgresRegistry:
    def __init__(self, namespace: str) -> None:
        self.namespace = namespace

    @property
    def database_url(self) -> str:
        value = os.getenv("DEPO_DATABASE_URL") or os.getenv("DATABASE_URL")
        if not value:
            raise RuntimeError("DEPO_DATABASE_URL (or DATABASE_URL) must configure PostgreSQL persistence")
        return value

    @contextmanager
    def _connect(self):
        import psycopg
        with psycopg.connect(self.database_url, autocommit=True) as connection:
            with connection.cursor() as cursor:
                initialise_schema(cursor)
            apply_migrations(connection)
            yield connection

    def all(self) -> dict[str, Any]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT key, value FROM depo_registry WHERE namespace = %s", (self.namespace,))
            return {key: value for key, value in cursor.fetchall()}

    def get(self, key: str) -> dict[str, Any] | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT value FROM depo_registry WHERE namespace = %s AND key = %s", (self.namespace, key))
            row = cursor.fetchone()
            return row[0] if row else None

    def put(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        return self.put_many({key: value})[key]

    def put_many(self, values: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.executemany("INSERT INTO depo_registry(namespace, key, value) VALUES (%s, %s, %s::jsonb) ON CONFLICT(namespace, key) DO UPDATE SET value=excluded.value, updated_at=now()", [(self.namespace, key, json.dumps(value)) for key, value in values.items()])
        return values

    @contextmanager
    def advisory_lock(self, key: str):
        """Hold a PostgreSQL session lock for one cross-process operation."""
        lock_name = f"{self.namespace}:{key}"
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(hashtextextended(%s, 0))", (lock_name,))
            acquired = bool(cursor.fetchone()[0])
            try:
                yield acquired
            finally:
                if acquired:
                    cursor.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (lock_name,))


class InMemoryRegistry:
    """Test double only; never selected by service configuration."""
    def __init__(self, namespace: str = "test") -> None: self.values: dict[str, dict[str, Any]] = {}
    def all(self) -> dict[str, Any]: return dict(self.values)
    def get(self, key: str) -> dict[str, Any] | None: return self.values.get(key)
    def put(self, key: str, value: dict[str, Any]) -> dict[str, Any]: self.values[key] = value; return value
    def put_many(self, values: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]: self.values.update(values); return values
    @contextmanager
    def advisory_lock(self, key: str):
        yield True
