"""Explicit PostgreSQL migration and read-only schema verification entry point."""
import argparse
import json
import os
import sys
import re
import ipaddress

from backend.depo_platform.postgres_schema import configured_schema, connect_timeout_seconds, initialise_schema, statement_options
from backend.depo_platform.schema_contract import verify_structure
from backend.postgres_migrations import MIGRATIONS, apply_migrations, migration_checksum

# Column/type contract for the tables owned by migrations 1-4. JSON documents
# remain in value; there is no separate relational table for each job namespace.
EXPECTED_COLUMNS = {
    'depo_api_credentials': {'profile': 'text', 'salt': 'text', 'digest': 'text', 'actor': 'text', 'expires_at': 'timestamp with time zone', 'revoked': 'boolean', 'updated_at': 'timestamp with time zone'},
    'depo_api_credential_events': {'event_id': 'bigint', 'profile': 'text', 'action': 'text', 'actor': 'text', 'created_at': 'timestamp with time zone'},
    'depo_schema_migrations': {'version': 'integer', 'name': 'text', 'checksum': 'text', 'applied_at': 'timestamp with time zone'},
    'depo_registry': {'namespace': 'text', 'key': 'text', 'value': 'jsonb', 'updated_at': 'timestamp with time zone'},
    'depo_runtime_state': {'kind': 'text', 'key': 'text', 'value': 'jsonb', 'updated_at': 'double precision'},
    'depo_chat_messages': {'session_id': 'text', 'message_id': 'bigint', 'role': 'text', 'content': 'text', 'created_at': 'double precision'},
    'depo_rate_limits': {'client_key': 'text', 'created_at': 'double precision'},
    'depo_metadata_assets': {'asset_id': 'text', 'revision': 'integer', 'value': 'jsonb', 'updated_at': 'timestamp with time zone'},
    'depo_metadata_events': {'event_id': 'text', 'asset_id': 'text', 'revision': 'integer', 'value': 'jsonb', 'created_at': 'timestamp with time zone'},
    'depo_metadata_outbox': {'event_id': 'text', 'status': 'text', 'created_at': 'timestamp with time zone'},
    'depo_ontology_analytics': {
        **dict.fromkeys(('ontology_id', 'ontology_name', 'lifecycle_status', 'semantic_completeness', 'schema_set_digest', 'analytics_profile_artifact_id'), 'text'),
        **dict.fromkeys(('triples', 'classes', 'object_properties', 'datatype_properties'), 'numeric'),
    },
}

EXPECTED_CONSTRAINTS = {
    'depo_api_credentials_pkey', 'depo_api_credential_events_pkey',
    'depo_schema_migrations_pkey', 'depo_registry_pkey', 'depo_runtime_state_pkey',
    'depo_chat_messages_pkey', 'depo_metadata_assets_pkey', 'depo_metadata_events_pkey',
    'depo_metadata_assets_revision_check', 'depo_metadata_assets_value_check',
    'depo_metadata_events_value_check', 'depo_metadata_outbox_status_check',
    'depo_metadata_events_asset_id_revision_key', 'depo_metadata_events_asset_id_fkey',
    'depo_metadata_events_revision_positive', 'depo_metadata_outbox_pkey',
    'depo_metadata_outbox_event_id_fkey', 'depo_registry_value_object', 'depo_runtime_state_value_object',
}
EXPECTED_INDEXES = {
    'idx_depo_chat_messages', 'idx_depo_rate_limits', 'idx_metadata_pending',
    'idx_depo_pipeline_runnable', 'idx_depo_registry_recent',
    'idx_depo_product_published', 'idx_depo_job_started', 'idx_depo_catalog_updated',
}


def _connection_context() -> dict[str, str]:
    """Expose only explicit non-secret connection fields, never the DSN."""
    url = os.getenv('DEPO_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not url:
        return {}
    try:
        from psycopg.conninfo import conninfo_to_dict
        values = conninfo_to_dict(url)
        return {key: str(values[key]) for key in ('host', 'port', 'dbname', 'user', 'sslmode') if values.get(key)}
    except Exception:
        return {}  # Invalid DSNs must not be echoed even when parsing fails.


def _failure_action(exc: Exception) -> dict:
    """Return useful diagnostics without echoing a DSN or credentials."""
    sqlstate = getattr(exc, 'sqlstate', None)
    actions = {
        '28P01': 'PostgreSQL rejected the user/password. Correct DEPO_DATABASE_URL and test the same credentials in pgAdmin.',
        '28000': 'PostgreSQL rejected this login. Check the role, database access, and pg_hba.conf rule for the application VM.',
        '3D000': 'The configured PostgreSQL database does not exist. Create it on the database VM or correct DEPO_DATABASE_URL.',
        '42501': 'The application role lacks privileges. Grant CONNECT on the database and USAGE, CREATE on the configured schema.',
        '23514': 'Existing data violates a new schema constraint. Correct the reported rows before rerunning the migration.',
        '23503': 'Existing data violates a foreign-key constraint. Correct the referenced records before rerunning the migration.',
        '42P07': 'An untracked relation already exists. Do not delete it; compare it with the versioned migration and reconcile migration history.',
        '42710': 'An untracked constraint or index already exists. Do not delete it; reconcile it with the versioned migration.',
    }
    diagnostic = str(exc).lower()
    if sqlstate and sqlstate.startswith('08'):
        action = 'PostgreSQL is unreachable. Verify host, port 5432, Windows firewall, listen_addresses and pg_hba.conf from the application VM.'
    elif 'no pg_hba.conf entry' in diagnostic:
        action = 'PostgreSQL has no pg_hba.conf rule for this application VM, user, database and SSL mode. Add the matching rule on the database VM, reload PostgreSQL, and retry.'
    elif not sqlstate and ('timeout' in diagnostic or 'timed out' in diagnostic or 'connection refused' in diagnostic):
        action = 'The application VM cannot reach PostgreSQL. Verify the configured host and port, firewall, listen_addresses and server status.'
    elif not sqlstate and ('certificate verify failed' in diagnostic or 'root certificate' in diagnostic):
        action = 'PostgreSQL TLS certificate validation failed. Check sslmode, the trusted CA and the hostname in DEPO_DATABASE_URL.'
    else:
        action = actions.get(sqlstate, 'Check PostgreSQL connectivity, schema privileges, migration history and existing object compatibility.')
    result = {'status': 'failed', 'error_type': type(exc).__name__, 'action': action}
    context = _connection_context()
    if context:
        result['connection'] = context
    if 'no pg_hba.conf entry' in diagnostic:
        # PostgreSQL reports the client address it actually sees (possibly NAT).
        # Extract only a validated IP address; never include driver error text.
        match = re.search(r'no pg_hba\.conf entry for host "([^"]+)"', str(exc), re.IGNORECASE)
        if match:
            try:
                address = ipaddress.ip_address(match.group(1))
                result['rejected_client_address'] = str(address)
                user, database = context.get('user', ''), context.get('dbname', '')
                if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*', user) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*', database):
                    result['hba_rule_example'] = f'host    {database}    {user}    {address}/{address.max_prefixlen}    scram-sha-256'
            except ValueError:
                pass
    if sqlstate:
        result['sqlstate'] = sqlstate
    # RuntimeError text is authored by DEPO and cannot contain driver connection details.
    if isinstance(exc, RuntimeError):
        result['reason'] = str(exc)
    return result


def verify_migration_privileges(connection) -> None:
    """Fail before DDL with a precise privilege error for customer-managed roles."""
    schema = configured_schema()
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT has_database_privilege(current_user, current_database(), %s), '
            'has_schema_privilege(current_user, %s, %s)',
            ('CONNECT', schema, 'USAGE, CREATE'),
        )
        row = cursor.fetchone()
        if not row or not all(row):
            raise RuntimeError(
                f"PostgreSQL application role requires CONNECT and USAGE, CREATE privileges on schema '{schema}'"
            )


def verify_schema(connection):
    schema = configured_schema()
    with connection.cursor() as cursor:
        cursor.execute('SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_schema = %s', (schema,))
        actual = {(table, column): datatype for table, column, datatype in cursor.fetchall()}
        mismatches = [f'{table}.{column} (expected {datatype})'
                      for table, columns in EXPECTED_COLUMNS.items() for column, datatype in columns.items()
                      if actual.get((table, column)) != datatype]
        if mismatches:
            raise RuntimeError('Missing or incompatible database columns: ' + ', '.join(mismatches))
        cursor.execute(
            'SELECT constraint_name FROM information_schema.table_constraints WHERE constraint_schema = %s',
            (schema,),
        )
        constraints = {row[0] for row in cursor.fetchall()}
        missing_constraints = sorted(EXPECTED_CONSTRAINTS - constraints)
        if missing_constraints:
            raise RuntimeError('Missing PostgreSQL constraints: ' + ', '.join(missing_constraints))
        cursor.execute('SELECT indexname FROM pg_indexes WHERE schemaname = %s', (schema,))
        indexes = {row[0] for row in cursor.fetchall()}
        missing_indexes = sorted(EXPECTED_INDEXES - indexes)
        if missing_indexes:
            raise RuntimeError('Missing PostgreSQL indexes: ' + ', '.join(missing_indexes))
        verify_structure(cursor, schema, EXPECTED_COLUMNS)
        cursor.execute(f'SELECT version, name, checksum FROM "{schema}".depo_schema_migrations')
        applied = {version: (name, checksum) for version, name, checksum in cursor.fetchall()}
        expected_history = {version: (name, migration_checksum(statements)) for version, name, statements in MIGRATIONS}
        if applied != expected_history:
            raise RuntimeError('Database migration history does not match this release')
    return {'status': 'ok', 'schema': schema, 'relations_checked': len(EXPECTED_COLUMNS),
            'columns_checked': sum(map(len, EXPECTED_COLUMNS.values())),
            'constraints_checked': len(EXPECTED_CONSTRAINTS),
            'indexes_checked': len(EXPECTED_INDEXES),
            'migration_versions': sorted(version for version, _, _ in MIGRATIONS)}


def setup_database(*, check_only=False, connection_only=False):
    import psycopg
    url = os.getenv('DEPO_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not url:
        raise RuntimeError('DEPO_DATABASE_URL is required')
    with psycopg.connect(url, connect_timeout=connect_timeout_seconds(), autocommit=True, application_name='depo-database-setup', options=statement_options(migration=not check_only)) as connection:
        if connection_only:
            with connection.cursor() as cursor:
                cursor.execute('SELECT current_database(), current_user')
                database, user = cursor.fetchone()
            return {'status': 'ok', 'database': database, 'user': user, 'schema': configured_schema(), 'check': 'connectivity'}
        if not check_only:
            with connection.transaction():
                with connection.cursor() as cursor:
                    initialise_schema(cursor)
                verify_migration_privileges(connection)
                apply_migrations(connection)
                from .credentials import bootstrap_environment
                bootstrap_environment(connection)
                return verify_schema(connection)
        return verify_schema(connection)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true', help='Verify existing columns and migration versions without DDL or data writes')
    parser.add_argument('--connection-only', action='store_true', help='Verify PostgreSQL login without requiring or modifying the application schema')
    args = parser.parse_args()
    if args.check_only and args.connection_only:
        parser.error('--check-only and --connection-only cannot be combined')
    try:
        print(json.dumps(setup_database(check_only=args.check_only, connection_only=args.connection_only)))
    except Exception as exc:
        # Driver exception strings can contain connection details. Emit only a
        # SQLSTATE-based action and DEPO-authored RuntimeError messages.
        print(json.dumps(_failure_action(exc)), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
