"""Real v11 -> current upgrade with retained records in a disposable test schema."""
import os
import uuid
from unittest.mock import patch

import psycopg
from psycopg import sql
import pytest

from backend import postgres_migrations as migrations
from backend.depo_platform import database_setup


@pytest.mark.skipif(not os.getenv('DEPO_TEST_DATABASE_URL'), reason='Requires isolated depo_acceptance_test')
def test_existing_customer_schema_upgrade_preserves_records_and_is_idempotent(monkeypatch):
    schema = 'upgrade_acceptance_' + uuid.uuid4().hex[:12]
    with psycopg.connect(os.environ['DEPO_TEST_DATABASE_URL'], autocommit=True) as db:
        assert db.info.dbname == 'depo_acceptance_test', 'Never target a customer application database'
        db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        try:
            db.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
            monkeypatch.setenv('DEPO_DATABASE_SCHEMA', schema)
            with patch.object(migrations, 'MIGRATIONS', [m for m in migrations.MIGRATIONS if m[0] <= 11]):
                migrations.apply_migrations(db)
            db.execute("INSERT INTO depo_registry(namespace,key,value) VALUES ('upgrade_fixture','retained','{\"status\":\"approved\"}')")
            db.execute("INSERT INTO depo_api_credentials(profile,salt,digest,actor) VALUES (%s,%s,%s,%s)",
                       ('upgrade-fixture', 'a' * 64, 'b' * 64, 'fixture-owner'))
            old_history = db.execute('SELECT version,name,checksum,applied_at FROM depo_schema_migrations ORDER BY version').fetchall()
            old_credentials = db.execute('SELECT * FROM depo_api_credentials').fetchall()
            migrations.apply_migrations(db)
            first_history = db.execute('SELECT version,name,checksum,applied_at FROM depo_schema_migrations ORDER BY version').fetchall()
            assert first_history[:len(old_history)] == old_history
            assert [row[0] for row in first_history] == [m[0] for m in migrations.MIGRATIONS]
            assert db.execute('SELECT * FROM depo_api_credentials').fetchall() == old_credentials
            assert db.execute("SELECT value FROM depo_registry WHERE namespace='upgrade_fixture'").fetchone()[0] == {'status': 'approved'}
            for table in ('depo_semantic_datasets', 'depo_semantic_values', 'depo_analytics_models', 'depo_analytics_fact_kpi'):
                assert db.execute('SELECT to_regclass(%s)', (schema + '.' + table,)).fetchone()[0]
            database_setup.verify_schema(db)
            migrations.apply_migrations(db)
            assert db.execute('SELECT version,name,checksum,applied_at FROM depo_schema_migrations ORDER BY version').fetchall() == first_history
            # A failing future additive step must roll back its DDL and history.
            future_version = max(version for version, _, _ in migrations.MIGRATIONS) + 1
            broken = (future_version, 'fixture_rollback', ('CREATE TABLE fixture_partial(id integer)', 'SELECT missing_upgrade_column FROM fixture_partial'))
            with patch.object(migrations, 'MIGRATIONS', [*migrations.MIGRATIONS, broken]):
                with pytest.raises(migrations.MigrationExecutionError):
                    migrations.apply_migrations(db)
            assert db.execute("SELECT to_regclass('fixture_partial')").fetchone()[0] is None
            assert db.execute('SELECT count(*) FROM depo_schema_migrations WHERE version=%s', (future_version,)).fetchone()[0] == 0
        finally:
            db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
