import sys
from unittest.mock import MagicMock

import pytest

from backend.depo_platform import database_setup as setup


def connection(rows=None, history=None):
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchall.side_effect = [
        rows if rows is not None else [(t, c, d) for t, cols in setup.EXPECTED_COLUMNS.items() for c, d in cols.items()],
        history if history is not None else [(v, n) for v, n, _ in setup.MIGRATIONS],
    ]
    return conn


def test_schema_contract(monkeypatch):
    monkeypatch.setenv('DEPO_DATABASE_SCHEMA', 'customer')
    result = setup.verify_schema(connection())
    assert result['schema'] == 'customer'
    assert result['columns_checked'] == 40
    assert result['migration_versions'] == [1, 2, 3, 4]


@pytest.mark.parametrize('rows', [[], [('depo_registry', 'value', 'text')]])
def test_missing_or_incompatible_columns_rejected(rows):
    with pytest.raises(RuntimeError, match='incompatible database columns'):
        setup.verify_schema(connection(rows=rows))


def test_incorrect_history_rejected():
    with pytest.raises(RuntimeError, match='migration history'):
        setup.verify_schema(connection(history=[(1, 'wrong')]))


@pytest.mark.parametrize('check_only', [True, False])
def test_check_only_never_migrates(monkeypatch, check_only):
    conn = connection()
    driver = MagicMock()
    driver.connect.return_value.__enter__.return_value = conn
    monkeypatch.setitem(sys.modules, 'psycopg', driver)
    monkeypatch.setenv('DEPO_DATABASE_URL', 'postgresql://fixture')
    initialize, migrate = MagicMock(), MagicMock()
    monkeypatch.setattr(setup, 'initialise_schema', initialize)
    monkeypatch.setattr(setup, 'apply_migrations', migrate)
    assert setup.setup_database(check_only=check_only)['status'] == 'ok'
    assert initialize.call_count == migrate.call_count == (0 if check_only else 1)


def test_invalid_schema_rejected(monkeypatch):
    monkeypatch.setenv('DEPO_DATABASE_SCHEMA', 'unsafe"schema')
    with pytest.raises(RuntimeError, match='valid PostgreSQL identifier'):
        setup.verify_schema(connection())
