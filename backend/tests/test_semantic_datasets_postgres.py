"""Opt-in real PostgreSQL projection test; uses a disposable schema only."""
import os
import uuid
import tempfile
import unittest
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
from backend.artifact_store import ArtifactStore
from backend.data_pipeline_service import semantic_datasets, semantic_analysis, semantic_configuration
from backend.tests.test_semantic_datasets import DATA

@unittest.skipUnless(os.getenv('DEPO_TEST_DATABASE_URL'), 'Requires isolated PostgreSQL test database')
class SemanticPostgres(unittest.TestCase):
    def test_atomic_projection_idempotency_and_analysis(self):
        import psycopg
        from psycopg import sql
        dsn=os.environ['DEPO_TEST_DATABASE_URL']
        schema='depo_semantic_test_'+uuid.uuid4().hex[:12]
        with psycopg.connect(dsn,autocommit=True) as control, tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(control.info.dbname, 'depo_acceptance_test', 'Never target a customer application database')
            control.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            try:
                control.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                control.execute(Path('infra/postgres/migrations/015_semantic_datasets.sql').read_text(encoding='utf-8'))
                store=ArtifactStore(Path(temporary))
                artifact=store.ingest_bytes(DATA,filename='parts.ttl')
                from backend.mesh_store import PostgresRegistry
                control.execute('CREATE TABLE depo_registry(namespace TEXT NOT NULL,key TEXT NOT NULL,value JSONB NOT NULL,updated_at TIMESTAMPTZ DEFAULT now(),PRIMARY KEY(namespace,key))')
                class Registry(PostgresRegistry):
                    def __init__(self,namespace):self.namespace=namespace
                    @contextmanager
                    def _connect(self,**kwargs):
                        with psycopg.connect(dsn,autocommit=True) as db:
                            db.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                            yield db
                    _session_connect=_connect
                with patch.object(semantic_configuration,'PostgresRegistry',Registry), patch.object(semantic_configuration,'ArtifactStore',return_value=store), patch.object(semantic_datasets,'PostgresRegistry',Registry), patch.object(semantic_analysis,'PostgresRegistry',Registry), patch.object(semantic_datasets,'ArtifactStore',return_value=store), patch.object(semantic_datasets,'resolve_source',return_value={'name':'Parts','version':'1.0.0'}):
                    payload={'artifact_id':artifact['artifact_id'],'source_id':'catalog:parts:1.0.0'}
                    receipt=semantic_datasets.materialize(payload,'test')
                    self.assertEqual(semantic_datasets.materialize(payload,'retry'),receipt)
                    self.assertEqual(receipt['counts']['entities'],2)
                    baseline=semantic_configuration.get_configuration(receipt['configuration_id'])
                    self.assertEqual(baseline['approval_status'],'not_granted')
                    from backend.data_pipeline_service import run_records
                    definition={'job_id':'semantic-prepare','version':'1.0.0','job_type':'rdf-semantic-materialize',
                                'input_contract':'registered-rdf-source-v1'}
                    with patch.object(run_records,'store',Registry('data_job_runs')), patch.object(run_records,'ArtifactStore',return_value=store):
                        queued=run_records.start.__wrapped__(definition,payload,correlation_id='pinned-input',status='queued')
                        semantic_datasets.resolve_source.return_value={'name':'Parts','version':'1.0.0','revision':2}
                        replay=run_records.replay_payload(queued)
                        self.assertEqual(replay['configuration_id'],receipt['configuration_id'])
                        self.assertEqual(semantic_datasets.materialize(replay,'replay-after-change')['dataset_id'],receipt['dataset_id'])
                        semantic_datasets.resolve_source.return_value={'name':'Parts','version':'1.0.0'}
                    with patch('backend.Services.oslc_trs_service.OSLCTRSService.is_enabled',return_value=False), patch.object(semantic_configuration,'notify_configuration'):
                        assessed=semantic_configuration.review_dataset(receipt['dataset_id'])
                        reviewed=semantic_configuration.execute_review(None,{'dataset_id':receipt['dataset_id']},correlation_id='review')
                    self.assertEqual(assessed['status'],'review_required')
                    self.assertEqual(reviewed['status'],'completed')
                    self.assertEqual(reviewed['assessment_status'],'review_required')
                    self.assertEqual(Registry('semantic_refresh_reviews').get(receipt['dataset_id'])['trs_after'],0)
                    query={'dataset_id':receipt['dataset_id'],'class_iri':'urn:a:Part'}
                    result=semantic_analysis.analyse({**query,'algorithm':'numeric-summary','property_iris':['urn:a:mass']})
                    self.assertEqual(result['rows'][0]['average'],'2.5000000000000000')
                    dimension=semantic_analysis.analyse({**query,'algorithm':'dimension-preview','property_iris':['urn:a:name']})
                    self.assertEqual(len(dimension['rows'][0]['attributes']['urn:a:name']),2)
                    with self.assertRaisesRegex(ValueError,'non-numeric'):
                        semantic_analysis.analyse({**query,'class_iri':'urn:b:Part','algorithm':'numeric-summary','property_iris':['urn:a:mass']})
                    with patch.object(semantic_datasets,'VERSION','failure-test'), patch.object(semantic_datasets,'ensure_execution_allowed',side_effect=RuntimeError('Lease lost')):
                        with self.assertRaisesRegex(RuntimeError,'Lease lost'):semantic_datasets.materialize(payload,'failed')
                    self.assertEqual(control.execute('SELECT count(*) FROM depo_semantic_datasets').fetchone()[0],1)
            finally:
                control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
            self.assertFalse(control.execute('SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=%s)',(schema,)).fetchone()[0])
