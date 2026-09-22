"""Explicit PostgreSQL migration and read-only schema verification entry point."""
import argparse
import json
import os

from backend.depo_platform.postgres_schema import configured_schema, initialise_schema
from backend.postgres_migrations import MIGRATIONS, apply_migrations

# Column/type contract for the tables owned by migrations 1-4. JSON documents
# remain in value; there is no separate relational table for each job namespace.
EXPECTED_COLUMNS = {
    'depo_schema_migrations': {'version': 'integer', 'name': 'text', 'applied_at': 'timestamp with time zone'},
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
        cursor.execute(f'SELECT version, name FROM "{schema}".depo_schema_migrations')
        applied = dict(cursor.fetchall())
        if any(applied.get(version) != name for version, name, _ in MIGRATIONS):
            raise RuntimeError('Database migration history does not match this release')
    return {'status': 'ok', 'schema': schema, 'relations_checked': len(EXPECTED_COLUMNS),
            'columns_checked': sum(map(len, EXPECTED_COLUMNS.values())),
            'migration_versions': sorted(version for version, _, _ in MIGRATIONS)}


def setup_database(*, check_only=False):
    import psycopg
    url = os.getenv('DEPO_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not url:
        raise RuntimeError('DEPO_DATABASE_URL is required')
    with psycopg.connect(url, connect_timeout=10, autocommit=True) as connection:
        if not check_only:
            with connection.cursor() as cursor:
                initialise_schema(cursor)
            apply_migrations(connection)
        return verify_schema(connection)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true', help='Verify existing columns and migration versions without DDL or data writes')
    args = parser.parse_args()
    try:
        print(json.dumps(setup_database(check_only=args.check_only)))
    except Exception as exc:
        # Driver exceptions can contain connection details. Do not print them.
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__,
                          'action': 'Check database connectivity, schema privileges and migration/column compatibility.'}))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
