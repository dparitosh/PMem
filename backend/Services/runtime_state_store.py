"""Small SQLite-backed store for state that must survive worker boundaries."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "uploads" / "runtime_state.sqlite3"
_DB_PATH = Path(os.getenv("RUNTIME_STATE_DB_PATH", str(_DEFAULT_PATH)))
_INIT_LOCK = threading.Lock()


def _connection() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(_DB_PATH), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def _ensure_schema() -> None:
    with _INIT_LOCK:
        with _connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS request_rate_limits (
                    client_key TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_rate_limits_key_time
                    ON request_rate_limits(client_key, created_at);
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    last_accessed_at REAL NOT NULL,
                    ip_addresses TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chat_jobs (
                    job_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session
                    ON chat_messages(session_id, message_id);
                CREATE TABLE IF NOT EXISTS session_leases (
                    session_id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    expires_at REAL NOT NULL
                );
                """
            )


def allow_request(client_key: str, now: float, window: float, maximum: int) -> bool:
    _ensure_schema()
    with _connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "DELETE FROM request_rate_limits WHERE created_at < ?",
            (now - window,),
        )
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM request_rate_limits WHERE client_key = ?",
            (client_key,),
        ).fetchone()
        if int(row["count"] or 0) >= maximum:
            return False
        connection.execute(
            "INSERT INTO request_rate_limits(client_key, created_at) VALUES (?, ?)",
            (client_key, now),
        )
        return True


def get_session(session_id: str) -> dict[str, Any] | None:
    _ensure_schema()
    with _connection() as connection:
        row = connection.execute(
            "SELECT session_id, created_at, last_accessed_at, ip_addresses FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if not row:
        return None
    try:
        ips = json.loads(row["ip_addresses"])
    except (TypeError, json.JSONDecodeError):
        ips = []
    return {
        "session_id": row["session_id"],
        "created_at": row["created_at"],
        "last_accessed_at": row["last_accessed_at"],
        "ips": ips if isinstance(ips, list) else [],
    }


def save_session(session_id: str, created_at: float, last_accessed_at: float, ips: list[str]) -> None:
    _ensure_schema()
    with _connection() as connection:
        connection.execute(
            """INSERT INTO sessions(session_id, created_at, last_accessed_at, ip_addresses)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                 last_accessed_at=excluded.last_accessed_at,
                 ip_addresses=excluded.ip_addresses""",
            (session_id, created_at, last_accessed_at, json.dumps(ips)),
        )


def delete_session(session_id: str) -> None:
    _ensure_schema()
    with _connection() as connection:
        connection.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))


def save_chat_job(job_id: str, payload: dict[str, Any]) -> None:
    _ensure_schema()
    updated_at = float(payload.get("updated_at") or time.time())
    with _connection() as connection:
        connection.execute(
            """INSERT INTO chat_jobs(job_id, payload, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(job_id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at""",
            (job_id, json.dumps(payload, ensure_ascii=True, default=str), updated_at),
        )


def get_chat_job(job_id: str) -> dict[str, Any] | None:
    _ensure_schema()
    with _connection() as connection:
        row = connection.execute("SELECT payload FROM chat_jobs WHERE job_id = ?", (job_id,)).fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row["payload"])
    except (TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def list_chat_jobs() -> list[dict[str, Any]]:
    _ensure_schema()
    with _connection() as connection:
        rows = connection.execute("SELECT payload FROM chat_jobs").fetchall()
    jobs = []
    for row in rows:
        try:
            payload = json.loads(row["payload"])
            if isinstance(payload, dict):
                jobs.append(payload)
        except (TypeError, json.JSONDecodeError):
            continue
    return jobs


def delete_chat_job(job_id: str) -> None:
    _ensure_schema()
    with _connection() as connection:
        connection.execute("DELETE FROM chat_jobs WHERE job_id = ?", (job_id,))


def load_chat_messages(session_id: str, limit: int) -> list[dict[str, str]]:
    _ensure_schema()
    with _connection() as connection:
        rows = connection.execute(
            "SELECT role, content FROM chat_messages WHERE session_id = ? ORDER BY message_id DESC LIMIT ?",
            (session_id, max(1, int(limit))),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def replace_chat_messages(session_id: str, messages: list[dict[str, str]], limit: int) -> None:
    _ensure_schema()
    bounded = messages[-max(1, int(limit)):]
    with _connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
        connection.executemany(
            "INSERT INTO chat_messages(session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            [(session_id, item.get("role", "user"), item.get("content", ""), time.time()) for item in bounded],
        )


def clear_chat_messages(session_id: str) -> None:
    _ensure_schema()
    with _connection() as connection:
        connection.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))


def acquire_session_lease(session_id: str, owner: str, ttl_seconds: float) -> bool:
    _ensure_schema()
    now = time.time()
    with _connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM session_leases WHERE expires_at <= ?", (now,))
        try:
            connection.execute(
                "INSERT INTO session_leases(session_id, owner, expires_at) VALUES (?, ?, ?)",
                (session_id, owner, now + max(1.0, ttl_seconds)),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def release_session_lease(session_id: str, owner: str) -> None:
    _ensure_schema()
    with _connection() as connection:
        connection.execute(
            "DELETE FROM session_leases WHERE session_id = ? AND owner = ?",
            (session_id, owner),
        )
