"""Versioned PostgreSQL migrations loaded from DBA-reviewable SQL files."""
from __future__ import annotations

from pathlib import Path
from collections.abc import Sequence
import re

Migration = tuple[int, str, Sequence[str]]
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / 'infra' / 'postgres' / 'migrations'


_MIGRATION_FILE = re.compile(r'^(?P<version>\d{3})_(?P<name>[a-z][a-z0-9_]*)\.sql$')


def _discover_migrations() -> tuple[Migration, ...]:
    discovered: list[Migration] = []
    for path in sorted(MIGRATIONS_DIR.glob('*.sql')):
        match = _MIGRATION_FILE.fullmatch(path.name)
        if not match:
            raise RuntimeError(f'Invalid PostgreSQL migration filename: {path.name}')
        version = int(match.group('version'))
        if version == 0:
            continue
        discovered.append((version, match.group('name'), (path.read_text(encoding='utf-8'),)))
    versions = [version for version, _name, _statements in discovered]
    if not versions or versions != list(range(1, max(versions) + 1)):
        raise RuntimeError(f'PostgreSQL migration versions must be unique and contiguous from 001: {versions}')
    return tuple(discovered)


MIGRATIONS: tuple[Migration, ...] = _discover_migrations()
SCHEMA_MIGRATIONS_SQL = (MIGRATIONS_DIR / '000_schema_migrations.sql').read_text(encoding='utf-8')


def apply_migrations(connection) -> None:
    """Apply each migration once and record its immutable version/name pair."""
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(current_schema() || ':depo-migrations', 0))")
        cursor.execute(SCHEMA_MIGRATIONS_SQL)
        cursor.execute("SELECT version, name FROM depo_schema_migrations")
        applied = {int(version): name for version, name in cursor.fetchall()}
        known = {version: name for version, name, _ in MIGRATIONS}
        unknown = sorted(set(applied) - set(known))
        if unknown:
            raise RuntimeError(
                f"Database has migration versions newer than or unknown to this release: {unknown}. "
                "Install the matching application release before modifying the schema."
            )
        for version, name, statements in sorted(MIGRATIONS):
            existing = applied.get(version)
            if existing and existing != name:
                raise RuntimeError(f"PostgreSQL migration {version} was recorded as {existing!r}, not {name!r}")
            if existing:
                continue
            for statement in statements:
                cursor.execute(statement)
            cursor.execute("INSERT INTO depo_schema_migrations(version, name) VALUES (%s, %s)", (version, name))
