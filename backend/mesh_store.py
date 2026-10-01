"""PostgreSQL-backed control-plane registry; no SQLite runtime dependency."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from typing import Any

from backend.depo_platform.postgres_schema import connect_timeout_seconds, select_schema


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
        with psycopg.connect(
            self.database_url,
            autocommit=True,
            connect_timeout=connect_timeout_seconds(),
            application_name="depo-control-plane",
        ) as connection:
            with connection.cursor() as cursor:
                select_schema(cursor)
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

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return bounded newest values without loading the registry namespace."""
        bounded = max(1, min(int(limit), 1000))
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT value FROM depo_registry WHERE namespace = %s ORDER BY updated_at DESC LIMIT %s",
                (self.namespace, bounded),
            )
            return [row[0] for row in cursor.fetchall()]

    def page_keys(self, offset: int, limit: int) -> tuple[int, list[str]]:
        """Page identifiers without loading every manifest into process memory."""
        if offset < 0 or not 1 <= limit <= 200:
            raise ValueError("Invalid registry page")
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM depo_registry WHERE namespace = %s AND right(key, 7) <> ':latest'", (self.namespace,))
            total = cursor.fetchone()[0]
            cursor.execute("SELECT key FROM depo_registry WHERE namespace = %s AND right(key, 7) <> ':latest' ORDER BY key LIMIT %s OFFSET %s", (self.namespace, limit, offset))
            return total, [row[0] for row in cursor.fetchall()]

    def put(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        return self.put_many({key: value})[key]

    def put_many(self, values: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        if not values:
            return values
        # _connect() uses autocommit for single-statement operations. A bulk
        # write must commit or roll back as one unit if any item is invalid.
        with self._connect() as connection, connection.transaction(), connection.cursor() as cursor:
            cursor.executemany("INSERT INTO depo_registry(namespace, key, value) VALUES (%s, %s, %s::jsonb) ON CONFLICT(namespace, key) DO UPDATE SET value=excluded.value, updated_at=now()", [(self.namespace, key, json.dumps(value)) for key, value in values.items()])
        return values

    def claim_next(self, *, worker_id: str, lease_seconds: int = 300) -> dict[str, Any] | None:
        """Atomically claim one data-job registry value using SKIP LOCKED."""
        if self.namespace != "data_job_runs":
            raise RuntimeError("claim_next is only valid for the data-job run registry")
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=max(30, min(int(lease_seconds), 3600)))
        lease = json.dumps({"claimed_at": now.isoformat(), "heartbeat_at": now.isoformat(), "expires_at": expires.isoformat()})
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                WITH candidate AS (
                  SELECT key FROM depo_registry
                  WHERE namespace = CAST(%s AS text) AND (
                    value->>'status' = 'queued' OR
                    (value->>'status' = 'running' AND COALESCE(value->'lease'->>'expires_at','') < CAST(%s AS text))
                  ) AND COALESCE(value->>'available_at','') <= CAST(%s AS text)
                  ORDER BY updated_at, key FOR UPDATE SKIP LOCKED LIMIT 1
                )
                UPDATE depo_registry AS r SET
                  value = r.value || jsonb_build_object(
                    'status','running','worker_id',CAST(%s AS text),'attempt',COALESCE((r.value->>'attempt')::int,0)+1,
                    'lease',CAST(%s AS jsonb)
                  ), updated_at = now()
                FROM candidate WHERE r.namespace = CAST(%s AS text) AND r.key = candidate.key
                RETURNING r.value
                """,
                (self.namespace, now.isoformat(), now.isoformat(), worker_id, lease, self.namespace),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def transition_owned(self, key: str, expected: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
        """Fence writes from workers whose claim has already been replaced."""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE depo_registry SET value=%s::jsonb, updated_at=now()
                   WHERE namespace=%s AND key=%s AND value->>'status'='running'
                     AND value->>'worker_id'=%s
                     AND COALESCE((value->>'attempt')::int,0)=%s
                     AND (value->'lease'->>'expires_at')::timestamptz > now()
                   RETURNING value""",
                (json.dumps(value), self.namespace, key, expected.get("worker_id"), int(expected.get("attempt") or 0)),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError("Worker no longer owns this run lease")
            return row[0]

    def heartbeat(self, *, key: str, worker_id: str, lease: dict[str, Any]) -> dict[str, Any] | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE depo_registry SET value=jsonb_set(value,'{lease}',%s::jsonb), updated_at=now()
                   WHERE namespace=%s AND key=%s AND value->>'status'='running' AND value->>'worker_id'=%s
                   RETURNING value""",
                (json.dumps(lease), self.namespace, key, worker_id),
            )
            row = cursor.fetchone()
            return row[0] if row else None

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
    def recent(self, limit: int = 100) -> list[dict[str, Any]]: return list(reversed(list(self.values.values())))[:limit]
    def put(self, key: str, value: dict[str, Any]) -> dict[str, Any]: self.values[key] = value; return value
    def put_many(self, values: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]: self.values.update(values); return values
    def heartbeat(self, *, key: str, worker_id: str, lease: dict[str, Any]) -> dict[str, Any] | None:
        value = self.values.get(key)
        if not value or value.get("status") != "running" or value.get("worker_id") != worker_id: return None
        return self.put(key, {**value, "lease": lease})
    @contextmanager
    def advisory_lock(self, key: str):
        yield True
