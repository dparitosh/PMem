import os
import random
import uuid

import pytest

from scripts.synthetic_analytics import generate, order_tables, value


def test_cycles_and_external_keys_rejected():
    with pytest.raises(ValueError):
        order_tables({'a': {'foreign_keys': [{'parent_schema': 's', 'parent': 'a'}]}}, 's')
    with pytest.raises(ValueError):
        order_tables({'a': {'foreign_keys': [{'parent_schema': 'foreign', 'parent': 'a'}]}}, 's')


def test_value_is_reproducible_and_unsupported_types_explicit():
    column = dict(kind='numeric', precision=8, scale=2)
    assert value(column, 1, random.Random(42)) == value(column, 1, random.Random(42))
    with pytest.raises(ValueError):
        value({'kind': 'ARRAY'}, 0, random.Random(1))


@pytest.mark.skipif(not os.getenv('DEPO_TEST_DATABASE_URL'), reason='Needs PostgreSQL test connection')
def test_real_schema_rows_foreign_keys_kpis_and_rollback():
    import psycopg
    from psycopg import sql
    source = 'nexus_test_source_' + uuid.uuid4().hex[:10]
    target = 'nexus_test_generated_' + uuid.uuid4().hex[:10]
    class Rollback(Exception):
        pass
    with psycopg.connect(os.environ['DEPO_TEST_DATABASE_URL'], autocommit=True) as db:
        with pytest.raises(Rollback):
            with db.transaction():
                db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(source)))
                db.execute(sql.SQL('CREATE TABLE {}.parts(part_id int PRIMARY KEY,classification text NOT NULL,mass_kg numeric(8,2) NOT NULL)').format(sql.Identifier(source)))
                db.execute(sql.SQL('CREATE TABLE {}.uses(use_id int PRIMARY KEY,part_id int REFERENCES {}.parts)').format(sql.Identifier(source), sql.Identifier(source)))
                result = generate(db, source, target, 12, 42, [{'name': 'Mean part mass', 'table': 'parts', 'measure': 'mass_kg', 'aggregate': 'avg', 'unit': 'kg', 'dimensions': ['classification']}])
                assert result['tables']['parts']['rows'] == 12
                assert result['tables']['uses']['rows'] == 12
                assert result['kpis'][0]['formula'] == 'avg(mass_kg)'
                assert len(result['kpis'][0]['values']) == 12
                assert db.execute(sql.SQL('SELECT count(*) FROM {}.parts').format(sql.Identifier(source))).fetchone()[0] == 0
                with pytest.raises(psycopg.errors.DuplicateSchema):
                    with db.transaction():
                        generate(db, source, target, 12, 42, [])
                raise Rollback()
        assert db.execute('SELECT count(*) FROM pg_namespace WHERE nspname IN (%s,%s)', (source,target)).fetchone()[0] == 0
