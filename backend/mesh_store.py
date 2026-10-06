"""PostgreSQL-backed control-plane registry; no SQLite runtime dependency."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from typing import Any

from backend.depo_platform.execution_guard import ensure_execution_allowed
from backend.depo_platform.postgres_schema import connect_timeout_seconds, select_schema, statement_options


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
            options=statement_options(),
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

    def page(self, *, limit=100, offset=0, field=None, value=None, exclude_latest=False, order_field=None):
        """Bounded, deterministic database pagination over JSON registry records."""
        if offset < 0 or not 1 <= limit <= 1000:
            raise ValueError('Invalid registry page')
        where = 'namespace=%s'
        args = [self.namespace]
        if field is not None:
            where += ' AND value->>%s=%s'
            args.extend([field, value])
        if exclude_latest:
            where += " AND right(key,7) <> ':latest'"
        with self._connect() as db, db.transaction(), db.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            cursor.execute('SELECT count(*) FROM depo_registry WHERE '+where, args)
            total = cursor.fetchone()[0]
            ordering = 'updated_at DESC, key DESC' if order_field is None else "COALESCE(value->>%s,'') DESC, key DESC"
            order_args = [] if order_field is None else [order_field]
            cursor.execute('SELECT value FROM depo_registry WHERE '+where+' ORDER BY '+ordering+' LIMIT %s OFFSET %s', [*args,*order_args,limit,offset])
            return total, [row[0] for row in cursor.fetchall()]

    def put_with_related(self, key, value, *, related_namespace, related_key, related_value):
        """Commit a product and its approval evidence as one database unit."""
        ensure_execution_allowed()
        with self._connect() as db, db.transaction(), db.cursor() as cursor:
            cursor.executemany('INSERT INTO depo_registry(namespace,key,value) VALUES (%s,%s,%s::jsonb) ON CONFLICT(namespace,key) DO UPDATE SET value=excluded.value,updated_at=now()',
                [(self.namespace,key,json.dumps(value)),(related_namespace,related_key,json.dumps(related_value))])
        return value

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return bounded newest values without loading the registry namespace."""
        bounded = max(1, min(int(limit), 1000))
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT value FROM depo_registry WHERE namespace = %s ORDER BY updated_at DESC, key LIMIT %s",
                (self.namespace, bounded),
            )
            return [row[0] for row in cursor.fetchall()]

    def latest_job_run(self, job_id: str, version: str) -> dict[str, Any] | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT value FROM depo_registry WHERE namespace=%s AND value->>'job_id'=%s AND value->>'job_version'=%s ORDER BY (value->>'started_at')::timestamptz DESC, key DESC LIMIT 1", (self.namespace, job_id, version))
            row = cursor.fetchone()
            return row[0] if row else None

    def page_keys(self, offset: int, limit: int) -> tuple[int, list[str]]:
        """Page identifiers without loading every manifest into process memory."""
        if offset < 0 or not 1 <= limit <= 200:
            raise ValueError("Invalid registry page")
        with self._connect() as connection, connection.transaction(), connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            cursor.execute("SELECT count(*) FROM depo_registry WHERE namespace = %s AND right(key, 7) <> ':latest'", (self.namespace,))
            total = cursor.fetchone()[0]
            cursor.execute("SELECT key FROM depo_registry WHERE namespace = %s AND right(key, 7) <> ':latest' ORDER BY key LIMIT %s OFFSET %s", (self.namespace, limit, offset))
            return total, [row[0] for row in cursor.fetchall()]

    def create(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        """Insert an immutable record atomically; never overwrite a conflict."""
        ensure_execution_allowed()
        if not isinstance(value, dict):
            raise ValueError("Registry values must be JSON objects")
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO depo_registry(namespace, key, value) VALUES (%s, %s, %s::jsonb) ON CONFLICT(namespace, key) DO NOTHING RETURNING value", (self.namespace, key, json.dumps(value)))
            row = cursor.fetchone()
            if row is None:
                raise FileExistsError("A record with this identity already exists")
            return row[0]

    def put(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        return self.put_many({key: value})[key]

    def put_many(self, values: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        ensure_execution_allowed()
        if any(not isinstance(value, dict) for value in values.values()):
            raise ValueError("Registry values must be JSON objects")
        if not values:
            return values
        # _connect() uses autocommit for single-statement operations. A bulk
        # write must commit or roll back as one unit if any item is invalid.
        with self._connect() as connection, connection.transaction(), connection.cursor() as cursor:
            cursor.executemany("INSERT INTO depo_registry(namespace, key, value) VALUES (%s, %s, %s::jsonb) ON CONFLICT(namespace, key) DO UPDATE SET value=excluded.value, updated_at=now()", [(self.namespace, key, json.dumps(value)) for key, value in values.items()])
        return values

    def due_pending(self, limit: int = 100) -> list[tuple[str, dict[str, Any]]]:
        bounded = max(1, min(int(limit), 1000))
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT key, value FROM depo_registry WHERE namespace=%s AND value->>'status'='pending_catalog_registration' AND (value->>'next_catalog_attempt_at' IS NULL OR (value->>'next_catalog_attempt_at')::timestamptz <= now()) ORDER BY updated_at, key LIMIT %s", (self.namespace, bounded))
            return cursor.fetchall()

    def compare_and_put(self, key: str, expected: dict[str, Any], value: dict[str, Any]) -> bool:
        ensure_execution_allowed()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE depo_registry SET value=%s::jsonb, updated_at=now() WHERE namespace=%s AND key=%s AND value=%s::jsonb RETURNING key", (json.dumps(value), self.namespace, key, json.dumps(expected)))
            return cursor.fetchone() is not None

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
                    (value->>'status' = 'running' AND (NULLIF(value->'lease'->>'expires_at','') IS NULL OR NULLIF(value->'lease'->>'expires_at','')::timestamptz <= CAST(%s AS timestamptz)))
                  ) AND (NULLIF(value->>'available_at','') IS NULL OR NULLIF(value->>'available_at','')::timestamptz <= CAST(%s AS timestamptz))
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

    def heartbeat(self, *, key: str, worker_id: str, attempt: int, lease: dict[str, Any]) -> dict[str, Any] | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE depo_registry SET value=jsonb_set(value,'{lease}',%s::jsonb), updated_at=now()
                   WHERE namespace=%s AND key=%s AND value->>'status'='running' AND value->>'worker_id'=%s
                     AND COALESCE((value->>'attempt')::int,0)=%s
                     AND (value->'lease'->>'expires_at')::timestamptz > now()
                   RETURNING value""",
                (json.dumps(lease), self.namespace, key, worker_id, attempt),
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
    def __init__(self, namespace: str = "test") -> None:
        self.namespace = namespace
        self.values: dict[str, dict[str, Any]] = {}
    def all(self) -> dict[str, Any]: return dict(self.values)
    def get(self, key: str) -> dict[str, Any] | None: return self.values.get(key)
    def page(self, *, limit=100, offset=0, field=None, value=None, exclude_latest=False, order_field=None):
        if offset < 0 or not 1 <= limit <= 1000:
            raise ValueError('Invalid registry page')
        rows = [(key, item) for key, item in self.values.items()
            if (not exclude_latest or not key.endswith(':latest')) and (field is None or item.get(field) == value)]
        rows.sort(key=lambda pair: (str(pair[1].get(order_field) or '') if order_field else '', pair[0]), reverse=True)
        return len(rows), [item for _, item in rows[offset:offset+limit]]
    def latest_job_run(self, job_id, version):
        matches = [v for v in self.values.values() if v.get('job_id') == job_id and v.get('job_version') == version]
        return max(matches, key=lambda v: v.get('started_at', ''), default=None)
    def recent(self, limit: int = 100) -> list[dict[str, Any]]: return list(reversed(list(self.values.values())))[:limit]
    def create(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        if key in self.values: raise FileExistsError("A record with this identity already exists")
        if not isinstance(value, dict): raise ValueError("Registry values must be JSON objects")
        self.values[key] = value
        return value
    def put(self, key: str, value: dict[str, Any]) -> dict[str, Any]: self.values[key] = value; return value
    def put_many(self, values: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]: self.values.update(values); return values
    def due_pending(self, limit=100):
        current = datetime.now(timezone.utc)
        return [(k,v) for k,v in self.values.items() if v.get('status') == 'pending_catalog_registration' and (not v.get('next_catalog_attempt_at') or datetime.fromisoformat(v['next_catalog_attempt_at']) <= current)][:max(1,min(int(limit),1000))]
    def compare_and_put(self, key, expected, value):
        if self.values.get(key) != expected: return False
        self.values[key] = value
        return True
    def heartbeat(self, *, key: str, worker_id: str, attempt: int, lease: dict[str, Any]) -> dict[str, Any] | None:
        value = self.values.get(key)
        if not value or value.get("status") != "running" or value.get("worker_id") != worker_id or value.get("attempt") != attempt: return None
        if datetime.fromisoformat(value["lease"]["expires_at"]) <= datetime.now(timezone.utc): return None
        return self.put(key, {**value, "lease": lease})
    @contextmanager
    def advisory_lock(self, key: str):
        yield True
