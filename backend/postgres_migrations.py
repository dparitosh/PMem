"""Versioned PostgreSQL schema migrations shared by DEPO services."""
from __future__ import annotations

from collections.abc import Sequence


Migration = tuple[int, str, Sequence[str]]

MIGRATIONS: tuple[Migration, ...] = (
    (
        1,
        "control_plane_registry",
        (
            """
            CREATE TABLE IF NOT EXISTS depo_registry (
                namespace TEXT NOT NULL,
                key TEXT NOT NULL,
                value JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY(namespace, key)
            )
            """,
        ),
    ),
    (
        2,
        "runtime_state",
        (
            """
            CREATE TABLE IF NOT EXISTS depo_runtime_state (
                kind TEXT NOT NULL,
                key TEXT NOT NULL,
                value JSONB NOT NULL,
                updated_at DOUBLE PRECISION NOT NULL,
                PRIMARY KEY(kind, key)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS depo_chat_messages (
                session_id TEXT NOT NULL,
                message_id BIGSERIAL PRIMARY KEY,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at DOUBLE PRECISION NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_depo_chat_messages ON depo_chat_messages(session_id, message_id)",
            """
            CREATE TABLE IF NOT EXISTS depo_rate_limits (
                client_key TEXT NOT NULL,
                created_at DOUBLE PRECISION NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_depo_rate_limits ON depo_rate_limits(client_key, created_at)",
        ),
    ),
)


def apply_migrations(connection) -> None:
    """Apply each migration once and record its immutable version/name pair."""
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS depo_schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cursor.execute("SELECT version, name FROM depo_schema_migrations")
        applied = {int(version): name for version, name in cursor.fetchall()}
        for version, name, statements in MIGRATIONS:
            existing = applied.get(version)
            if existing and existing != name:
                raise RuntimeError(f"PostgreSQL migration {version} was recorded as {existing!r}, not {name!r}")
            if existing:
                continue
            for statement in statements:
                cursor.execute(statement)
            cursor.execute(
                "INSERT INTO depo_schema_migrations(version, name) VALUES (%s, %s)",
                (version, name),
            )
