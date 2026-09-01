"""Small transactional registry for control-plane state.

This replaces the process-local JSON read/modify/write implementation with
SQLite transactions.  It is safe across multiple workers sharing one volume;
a managed database can later implement the same API for clustered deployment.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class SqliteRegistry:
    def __init__(self, path: Path) -> None:
        self.path = path.with_suffix(".sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS registry (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=30, isolation_level="IMMEDIATE")
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=30000")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def all(self) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute("SELECT key, value FROM registry").fetchall()
        return {key: json.loads(value) for key, value in rows}

    def get(self, key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT value FROM registry WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        return self.put_many({key: value})[key]

    def put_many(self, values: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        with self._connect() as connection:
            connection.executemany(
                "INSERT INTO registry(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                [(key, json.dumps(value, sort_keys=True)) for key, value in values.items()],
            )
        return values


# Compatibility name retained for existing callers while they migrate.
JsonRegistry = SqliteRegistry
