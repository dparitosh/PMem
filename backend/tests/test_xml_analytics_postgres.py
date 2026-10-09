"""Opt-in PostgreSQL verification; all test objects roll back on completion."""
import os
import unittest
import uuid
from contextlib import contextmanager
from unittest.mock import patch

from backend.data_pipeline_service.xml_analytics import materialize_xml


@unittest.skipUnless(os.getenv('DEPO_TEST_DATABASE_URL'), 'Set DEPO_TEST_DATABASE_URL to an isolated PostgreSQL test database')
class XMLAnalyticsPostgres(unittest.TestCase):
    def test_load_retry_and_failed_write_are_transactional(self):
        import psycopg
        from psycopg import sql
        from backend.tests.test_xml_analytics_materialization import XMLAnalyticsMaterialization

        prepared = XMLAnalyticsMaterialization().prepare(
            b'<Root xmlns="urn:test" id="7"><tag>A</tag><tag>B</tag></Root>')
        prepared['schema'] = 'depo_test_xml_' + uuid.uuid4().hex[:16]
        from backend.Services.xsd_analytics_plan import build_analytics_schema_plan
        prepared['plan'] = build_analytics_schema_plan(prepared['model'], schema=prepared['schema'])
        control = 'depo_test_control_' + uuid.uuid4().hex[:16]

        class RollbackTest(Exception):
            pass

        with psycopg.connect(os.environ['DEPO_TEST_DATABASE_URL'], autocommit=True, connect_timeout=10) as db:
            try:
                with db.transaction():
                    db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(control)))
                    db.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(control)))
                    db.execute('CREATE TABLE depo_registry(namespace TEXT NOT NULL, key TEXT NOT NULL, value JSONB NOT NULL, PRIMARY KEY(namespace,key))')

                    class Registry:
                        namespace = 'xml_analytics_loads'

                        def __init__(self, *args):
                            pass

                        @contextmanager
                        def _connect(self):
                            yield db

                    with patch('backend.data_pipeline_service.xml_analytics.prepare_xml_load', return_value=prepared), patch('backend.data_pipeline_service.xml_analytics.PostgresRegistry', Registry):
                        receipt = materialize_xml({'execution_actor': 'integration-test'}, correlation_id='test-load')
                        replay = materialize_xml({}, correlation_id='retry')
                        self.assertEqual(replay, receipt)
                        source = db.execute(sql.SQL('SELECT original_bytes, document::text FROM {}.source_documents').format(sql.Identifier(prepared['schema']))).fetchall()
                        self.assertEqual(len(source), 1)
                        self.assertEqual(bytes(source[0][0]), prepared['original_bytes'])
                        for table in prepared['model']['tables']:
                            count = db.execute(sql.SQL('SELECT count(*) FROM {}.{}').format(sql.Identifier(prepared['schema']), sql.Identifier(table['sql_name']))).fetchone()[0]
                            self.assertEqual(count, sum(entity == table['entity_id'] for entity, _ in prepared['rows']))

                        failed = {**prepared, 'schema': prepared['schema'] + '_fail'}
                        failed['plan'] = build_analytics_schema_plan(failed['model'], schema=failed['schema'])
                        with patch('backend.data_pipeline_service.xml_analytics.prepare_xml_load', return_value=failed), patch('backend.data_pipeline_service.xml_analytics.ensure_execution_allowed', side_effect=[None, None, RuntimeError('Lease lost')]):
                            with self.assertRaisesRegex(RuntimeError, 'Lease lost'):
                                materialize_xml({}, correlation_id='failed-load')
                        self.assertFalse(db.execute('SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=%s)', (failed['schema'],)).fetchone()[0])
                        self.assertEqual(db.execute('SELECT count(*) FROM depo_registry WHERE namespace=%s', ('xml_analytics_loads',)).fetchone()[0], 1)
                    raise RollbackTest()
            except RollbackTest:
                pass
            self.assertFalse(db.execute('SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname IN (%s,%s))', (control, prepared['schema'])).fetchone()[0])
