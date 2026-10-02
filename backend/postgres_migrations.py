"""Versioned PostgreSQL migrations loaded from DBA-reviewable SQL files."""
from __future__ import annotations

from pathlib import Path
from collections.abc import Sequence
import re
import hashlib
import os

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


def migration_checksum(statements):
    return hashlib.sha256('\n'.join(statement.replace('\r\n', '\n') for statement in statements).encode('utf-8')).hexdigest()

def apply_migrations(connection) -> None:
    """Apply each migration once and record its immutable version/name pair."""
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(current_schema() || ':depo-migrations', 0))")
        cursor.execute(SCHEMA_MIGRATIONS_SQL)
        cursor.execute("ALTER TABLE depo_schema_migrations ADD COLUMN IF NOT EXISTS checksum TEXT")
        cursor.execute("SELECT version, name, checksum FROM depo_schema_migrations")
        applied = {int(version): (name, checksum) for version, name, checksum in cursor.fetchall()}
        known = {version: name for version, name, _ in MIGRATIONS}
        unknown = sorted(set(applied) - set(known))
        if unknown:
            raise RuntimeError(
                f"Database has migration versions newer than or unknown to this release: {unknown}. "
                "Install the matching application release before modifying the schema."
            )
        for version, name, statements in sorted(MIGRATIONS):
            existing = applied.get(version)
            if existing and existing[0] != name:
                raise RuntimeError(f"PostgreSQL migration {version} was recorded as {existing!r}, not {name!r}")
            checksum = migration_checksum(statements)
            if existing:
                if existing[1] is None:
                    if os.getenv('DEPO_ACCEPT_LEGACY_MIGRATION_CHECKSUMS', 'false').lower() != 'true':
                        raise RuntimeError('Legacy migration checksums require explicit DEPO_ACCEPT_LEGACY_MIGRATION_CHECKSUMS=true after reviewing this release SQL against the deployed schema')
                    cursor.execute('UPDATE depo_schema_migrations SET checksum=%s WHERE version=%s', (checksum, version))
                elif existing[1] != checksum:
                    raise RuntimeError(f'PostgreSQL migration {version} checksum differs from this release; restore the matching immutable migration')
                continue
            for statement in statements:
                cursor.execute(statement)
            cursor.execute("INSERT INTO depo_schema_migrations(version, name, checksum) VALUES (%s, %s, %s)", (version, name, checksum))
