import sys
from unittest.mock import MagicMock

import pytest

from backend.depo_platform import database_setup as setup
from backend.depo_platform import postgres_schema
from backend import postgres_migrations


def connection(rows=None, history=None, constraints=None, indexes=None):
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchall.side_effect = [
        rows if rows is not None else [(t, c, d) for t, cols in setup.EXPECTED_COLUMNS.items() for c, d in cols.items()],
        [(value,) for value in (constraints if constraints is not None else setup.EXPECTED_CONSTRAINTS)],
        [(value,) for value in (indexes if indexes is not None else setup.EXPECTED_INDEXES)],
        history if history is not None else [(v, n) for v, n, _ in setup.MIGRATIONS],
    ]
    return conn


def test_schema_contract(monkeypatch):
    monkeypatch.setenv('DEPO_DATABASE_SCHEMA', 'customer')
    result = setup.verify_schema(connection())
    assert result['schema'] == 'customer'
    assert result['columns_checked'] == 40
    assert result['constraints_checked'] == 15
    assert result['indexes_checked'] == 4
    assert result['migration_versions'] == [1, 2, 3, 4, 5, 6]


@pytest.mark.parametrize('rows', [[], [('depo_registry', 'value', 'text')]])
def test_missing_or_incompatible_columns_rejected(rows):
    with pytest.raises(RuntimeError, match='incompatible database columns'):
        setup.verify_schema(connection(rows=rows))


def test_incorrect_history_rejected():
    with pytest.raises(RuntimeError, match='migration history'):
        setup.verify_schema(connection(history=[(1, 'wrong')]))


def test_database_newer_than_application_is_rejected():
    history = [(v, n) for v, n, _ in setup.MIGRATIONS] + [(999, 'future_release')]
    with pytest.raises(RuntimeError, match='migration history'):
        setup.verify_schema(connection(history=history))


def test_missing_constraint_rejected():
    with pytest.raises(RuntimeError, match='Missing PostgreSQL constraints'):
        setup.verify_schema(connection(constraints=[]))


def test_missing_index_rejected():
    with pytest.raises(RuntimeError, match='Missing PostgreSQL indexes'):
        setup.verify_schema(connection(indexes=[]))


@pytest.mark.parametrize('check_only', [True, False])
def test_check_only_never_migrates(monkeypatch, check_only):
    conn = connection()
    driver = MagicMock()
    driver.connect.return_value.__enter__.return_value = conn
    monkeypatch.setitem(sys.modules, 'psycopg', driver)
    monkeypatch.setenv('DEPO_DATABASE_URL', 'postgresql://fixture')
    initialize, migrate = MagicMock(), MagicMock()
    monkeypatch.setattr(setup, 'initialise_schema', initialize)
    privileges = MagicMock()
    monkeypatch.setattr(setup, 'verify_migration_privileges', privileges)
    monkeypatch.setattr(setup, 'apply_migrations', migrate)
    assert setup.setup_database(check_only=check_only)['status'] == 'ok'
    assert initialize.call_count == migrate.call_count == (0 if check_only else 1)
    assert privileges.call_count == (0 if check_only else 1)


def test_failure_action_classifies_postgres_errors_without_exception_text():
    class DatabaseError(Exception):
        sqlstate = '28P01'

    failure = setup._failure_action(DatabaseError('password=must-not-leak'))
    assert failure['sqlstate'] == '28P01'
    assert 'password' in failure['action'].lower()
    assert 'reason' not in failure


def test_failure_action_reports_safe_application_errors():
    failure = setup._failure_action(RuntimeError('migration history mismatch'))
    assert failure['reason'] == 'migration history mismatch'


def test_migration_privileges_rejected_with_schema_name(monkeypatch):
    monkeypatch.setenv('DEPO_DATABASE_SCHEMA', 'semantic')
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (True, False)
    with pytest.raises(RuntimeError, match="schema 'semantic'"):
        setup.verify_migration_privileges(conn)


def test_invalid_schema_rejected(monkeypatch):
    monkeypatch.setenv('DEPO_DATABASE_SCHEMA', 'unsafe"schema')
    with pytest.raises(RuntimeError, match='valid PostgreSQL identifier'):
        setup.verify_schema(connection())


def test_migration_versions_are_unique():
    versions = [version for version, _name, _statements in postgres_migrations.MIGRATIONS]
    assert len(versions) == len(set(versions))


@pytest.mark.parametrize(('configured', 'expected'), [('1', 1), ('60', 60), ('10', 10)])
def test_postgres_connect_timeout_is_bounded(monkeypatch, configured, expected):
    monkeypatch.setenv('DEPO_POSTGRES_CONNECT_TIMEOUT_SECONDS', configured)
    assert postgres_schema.connect_timeout_seconds() == expected


@pytest.mark.parametrize('configured', ['0', '61', 'not-a-number'])
def test_invalid_postgres_connect_timeout_rejected(monkeypatch, configured):
    monkeypatch.setenv('DEPO_POSTGRES_CONNECT_TIMEOUT_SECONDS', configured)
    with pytest.raises(RuntimeError, match='DEPO_POSTGRES_CONNECT_TIMEOUT_SECONDS'):
        postgres_schema.connect_timeout_seconds()


def test_runtime_schema_selection_rejects_missing_schema(monkeypatch):
    monkeypatch.setenv('DEPO_DATABASE_SCHEMA', 'semantic')
    cursor = MagicMock()
    cursor.fetchone.return_value = (False,)

    with pytest.raises(RuntimeError, match='initialize-depo-schema.ps1'):
        postgres_schema.select_schema(cursor)
