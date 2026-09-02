"""PostgreSQL-backed durable state for the legacy compatibility host."""
from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from typing import Any

from backend.postgres_migrations import apply_migrations


@contextmanager
def _connection():
    import psycopg
    url = os.getenv("DEPO_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DEPO_DATABASE_URL must configure PostgreSQL persistence")
    schema = os.getenv("DEPO_DATABASE_SCHEMA", "semantic")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", schema):
        raise RuntimeError("DEPO_DATABASE_SCHEMA must be a valid PostgreSQL identifier")
    with psycopg.connect(url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            cursor.execute(f'SET search_path TO "{schema}", public')
        apply_migrations(connection)
        yield connection


def _ensure_schema() -> None:
    with _connection():
        return None


def _get(kind: str, key: str) -> dict[str, Any] | None:
    _ensure_schema()
    with _connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT value FROM depo_runtime_state WHERE kind=%s AND key=%s", (kind, key))
        row = cursor.fetchone()
        return row[0] if row else None


def _put(kind: str, key: str, value: dict[str, Any]) -> None:
    _ensure_schema()
    with _connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO depo_runtime_state(kind, key, value, updated_at)
            VALUES(%s, %s, %s::jsonb, %s)
            ON CONFLICT(kind, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (kind, key, json.dumps(value), time.time()),
        )


def _delete(kind: str, key: str) -> None:
    _ensure_schema()
    with _connection() as connection, connection.cursor() as cursor:
        cursor.execute("DELETE FROM depo_runtime_state WHERE kind=%s AND key=%s", (kind, key))


def allow_request(client_key: str, now: float, window: float, maximum: int) -> bool:
    _ensure_schema()
    with _connection() as connection, connection.transaction(), connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (client_key,))
        cursor.execute("DELETE FROM depo_rate_limits WHERE created_at < %s", (now - window,))
        cursor.execute("SELECT COUNT(*) FROM depo_rate_limits WHERE client_key=%s", (client_key,))
        if cursor.fetchone()[0] >= maximum:
            return False
        cursor.execute("INSERT INTO depo_rate_limits(client_key, created_at) VALUES(%s, %s)", (client_key, now))
        return True


def get_session(session_id: str) -> dict[str, Any] | None:
    return _get("session", session_id)


def save_session(session_id: str, created_at: float, last_accessed_at: float, ips: list[str]) -> None:
    _put("session", session_id, {"session_id": session_id, "created_at": created_at, "last_accessed_at": last_accessed_at, "ips": ips})


def delete_session(session_id: str) -> None:
    _delete("session", session_id)


def save_chat_job(job_id: str, payload: dict[str, Any]) -> None:
    _put("chat_job", job_id, payload)


def get_chat_job(job_id: str) -> dict[str, Any] | None:
    return _get("chat_job", job_id)


def list_chat_jobs() -> list[dict[str, Any]]:
    _ensure_schema()
    with _connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT value FROM depo_runtime_state WHERE kind='chat_job'")
        return [row[0] for row in cursor.fetchall()]


def delete_chat_job(job_id: str) -> None:
    _delete("chat_job", job_id)


def load_chat_messages(session_id: str, limit: int) -> list[dict[str, str]]:
    _ensure_schema()
    with _connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT role, content FROM depo_chat_messages WHERE session_id=%s ORDER BY message_id DESC LIMIT %s", (session_id, max(1, int(limit))))
        return [{"role": row[0], "content": row[1]} for row in reversed(cursor.fetchall())]


def replace_chat_messages(session_id: str, messages: list[dict[str, str]], limit: int) -> None:
    _ensure_schema()
    with _connection() as connection, connection.transaction(), connection.cursor() as cursor:
        cursor.execute("DELETE FROM depo_chat_messages WHERE session_id=%s", (session_id,))
        cursor.executemany(
            "INSERT INTO depo_chat_messages(session_id, role, content, created_at) VALUES(%s, %s, %s, %s)",
            [(session_id, item.get("role", "user"), item.get("content", ""), time.time()) for item in messages[-max(1, int(limit)):]],
        )


def clear_chat_messages(session_id: str) -> None:
    _ensure_schema()
    with _connection() as connection, connection.cursor() as cursor:
        cursor.execute("DELETE FROM depo_chat_messages WHERE session_id=%s", (session_id,))


def acquire_session_lease(session_id: str, owner: str, ttl_seconds: float) -> bool:
    _ensure_schema()
    now = time.time()
    payload = json.dumps({"owner": owner, "expires_at": now + max(1.0, ttl_seconds)})
    with _connection() as connection, connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO depo_runtime_state(kind, key, value, updated_at)
            VALUES('lease', %s, %s::jsonb, %s)
            ON CONFLICT(kind, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            WHERE (depo_runtime_state.value->>'expires_at')::double precision <= %s
               OR depo_runtime_state.value->>'owner' = %s
            RETURNING key
            """,
            (session_id, payload, now, now, owner),
        )
        return cursor.fetchone() is not None


def release_session_lease(session_id: str, owner: str) -> None:
    _ensure_schema()
    with _connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM depo_runtime_state WHERE kind='lease' AND key=%s AND value->>'owner'=%s",
            (session_id, owner),
        )
