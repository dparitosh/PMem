"""Versioned PostgreSQL migrations loaded from DBA-reviewable SQL files."""
from __future__ import annotations

from pathlib import Path
from collections.abc import Sequence

Migration = tuple[int, str, Sequence[str]]
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / 'infra' / 'postgres' / 'migrations'


def _read_migration(version: int, name: str) -> tuple[str, ...]:
    path = MIGRATIONS_DIR / f'{version:03d}_{name}.sql'
    if not path.is_file():
        raise RuntimeError(f'Missing PostgreSQL migration file: {path}')
    return (path.read_text(encoding='utf-8'),)


MIGRATIONS: tuple[Migration, ...] = tuple(
    (version, name, _read_migration(version, name))
    for version, name in (
        (1, 'control_plane_registry'),
        (2, 'runtime_state'),
        (3, 'governance_metadata'),
        (4, 'ontology_analytics_view'),
    )
)
SCHEMA_MIGRATIONS_SQL = (MIGRATIONS_DIR / '000_schema_migrations.sql').read_text(encoding='utf-8')


def apply_migrations(connection) -> None:
    """Apply each migration once and record its immutable version/name pair."""
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(current_schema() || ':depo-migrations', 0))")
        cursor.execute(SCHEMA_MIGRATIONS_SQL)
        cursor.execute("SELECT version, name FROM depo_schema_migrations")
        applied = {int(version): name for version, name in cursor.fetchall()}
        for version, name, statements in sorted(MIGRATIONS):
            existing = applied.get(version)
            if existing and existing != name:
                raise RuntimeError(f"PostgreSQL migration {version} was recorded as {existing!r}, not {name!r}")
            if existing:
                continue
            for statement in statements:
                cursor.execute(statement)
            cursor.execute("INSERT INTO depo_schema_migrations(version, name) VALUES (%s, %s)", (version, name))
