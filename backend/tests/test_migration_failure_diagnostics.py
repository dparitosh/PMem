"""Failure injection for rollback ownership and secret-free migration diagnostics."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend import postgres_migrations as migrations
from backend.depo_platform.database_setup import _failure_action


class DatabaseFailure(Exception):
    sqlstate = '42501'
    diag = SimpleNamespace(schema_name='semantic', table_name='depo_runtime_state',
                           column_name='value', constraint_name='depo_runtime_state_pkey',
                           datatype_name='jsonb', statement_position='12',
                           message_detail='password=private-row-content')


@pytest.mark.parametrize('operation', ['apply_sql', 'record_history', 'adopt_checksum', 'bootstrap_history'])
def test_migration_diagnostics_retain_identity_and_server_code_without_driver_contents(operation, monkeypatch):
    monkeypatch.delenv('DEPO_DATABASE_URL', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    cause = DatabaseFailure('postgresql://user:secret@private/db SQL includes private-row-content')
    try:
        raise migrations.MigrationExecutionError(2, 'runtime_state', cause, 'first line\nsecond line', operation) from cause
    except migrations.MigrationExecutionError as failure:
        report = _failure_action(failure)
    assert report['sqlstate'] == '42501'
    assert report['migration']['file'] == '002_runtime_state.sql'
    assert report['migration']['operation'] == operation
    assert report['database_object']['table_name'] == 'depo_runtime_state'
    assert report['database_error_type'] == 'DatabaseFailure'
    assert 'ownership' in report['action']
    assert ('sql_line' in report['migration']) == (operation == 'apply_sql')
    encoded = json.dumps(report)
    for forbidden in ('secret', 'private/db', 'private-row-content', 'first line', 'second line'):
        assert forbidden not in encoded


@pytest.mark.parametrize('fail_on_history', [False, True])
def test_statement_and_history_failures_escape_the_transaction_and_stop_pending_migrations(monkeypatch, fail_on_history):
    pending = migrations.MIGRATIONS[:3]
    monkeypatch.setattr(migrations, 'MIGRATIONS', pending)
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = []
    def execute(sql, parameters=None):
        if fail_on_history:
            failed = sql.startswith('INSERT INTO depo_schema_migrations') and parameters[0] == pending[1][0]
        else:
            failed = sql == pending[1][2][0]
        if failed:
            raise DatabaseFailure('private-row-content')
    cursor.execute.side_effect = execute
    with pytest.raises(migrations.MigrationExecutionError) as error:
        migrations.apply_migrations(conn)
    assert error.value.migration_context['version'] == pending[1][0]
    assert error.value.migration_context['operation'] == ('record_history' if fail_on_history else 'apply_sql')
    assert conn.transaction.return_value.__exit__.call_args.args[0] is migrations.MigrationExecutionError
    statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert pending[2][2][0] not in statements
    if not fail_on_history:
        assert not any(call.args[0].startswith('INSERT INTO depo_schema_migrations') and call.args[1][0] == pending[1][0]
                       for call in cursor.execute.call_args_list)
    conn.commit.assert_not_called()


def test_invalid_diagnostic_fields_are_omitted_and_network_classification_is_preserved():
    cause = DatabaseFailure('connection refused password=never-print')
    cause.sqlstate = None
    cause.diag = SimpleNamespace(table_name='password=never-print', statement_position='999999')
    try:
        raise migrations.MigrationExecutionError(2, 'runtime_state', cause, 'SQL', 'apply_sql') from cause
    except migrations.MigrationExecutionError as failure:
        report = _failure_action(failure)
    assert 'refused' in report['action']
    assert 'database_object' not in report
    assert 'sql_line' not in report['migration']
    assert 'never-print' not in json.dumps(report)
