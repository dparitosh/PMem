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


class MigrationExecutionError(RuntimeError):
    """Retain migration identity and server codes without copying driver text."""
    def __init__(self, version, name, cause, statement, operation):
        filename = f'{version:03d}_{name}.sql'
        super().__init__(f'PostgreSQL migration {filename} failed during {operation}; schema update was not completed.')
        self.sqlstate = getattr(cause, 'sqlstate', None)
        self.database_error_type = type(cause).__name__
        self.migration_context = {'version': version, 'name': name, 'file': filename, 'operation': operation}
        self.database_object = {}
        diag = getattr(cause, 'diag', None)
        for key in ('schema_name', 'table_name', 'column_name', 'constraint_name', 'datatype_name'):
            value = getattr(diag, key, None)
            if isinstance(value, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_$]{0,127}', value):
                self.database_object[key] = value
        position = getattr(diag, 'statement_position', None)
        if operation == 'apply_sql' and isinstance(position, (str, int)) and str(position).isdigit():
            position = int(position)
            if 0 < position <= len(statement) + 1:
                self.migration_context['sql_line'] = statement[:position - 1].count('\n') + 1


def _execute_migration(cursor, statement, version, name, *, parameters=None, operation='apply_sql'):
    try:
        if parameters is None:
            cursor.execute(statement)
        else:
            cursor.execute(statement, parameters)
    except Exception as exc:
        # The exception escapes the transaction context, which performs rollback.
        # Do not retry SQL or advance history after a failed statement.
        raise MigrationExecutionError(version, name, exc, statement, operation) from exc

def apply_migrations(connection) -> None:
    """Apply each migration once and record its immutable version/name pair."""
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(current_schema() || ':depo-migrations', 0))")
        _execute_migration(cursor, SCHEMA_MIGRATIONS_SQL, 0, 'schema_migrations', operation='bootstrap_history')
        _execute_migration(cursor, "ALTER TABLE depo_schema_migrations ADD COLUMN IF NOT EXISTS checksum TEXT", 0, 'schema_migrations', operation='bootstrap_history')
        cursor.execute("SELECT version, name, checksum FROM depo_schema_migrations")
        applied = {int(version): (name, checksum) for version, name, checksum in cursor.fetchall()}
        known = {version: name for version, name, _ in MIGRATIONS}
        unknown = sorted(set(applied) - set(known))
        if unknown:
            raise RuntimeError(
                f"Database has migration versions newer than or unknown to this release: {unknown}. "
                "Install the matching application release before modifying the schema."
            )
        if applied and sorted(applied) != list(range(1, max(applied) + 1)):
            raise RuntimeError(
                'PostgreSQL migration history has missing earlier versions; '
                'restore or reconcile the deployed history with the DBA before upgrading. '
                'Do not run earlier migrations after later versions or fabricate history rows.'
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
                    _execute_migration(cursor, 'UPDATE depo_schema_migrations SET checksum=%s WHERE version=%s', version, name,
                                       parameters=(checksum, version), operation='adopt_checksum')
                elif existing[1] != checksum:
                    raise RuntimeError(f'PostgreSQL migration {version} checksum differs from this release; restore the matching immutable migration')
                continue
            for statement in statements:
                _execute_migration(cursor, statement, version, name)
            _execute_migration(cursor, "INSERT INTO depo_schema_migrations(version, name, checksum) VALUES (%s, %s, %s)", version, name,
                               parameters=(version, name, checksum), operation='record_history')
