import json
import ast
import os
import re
import asyncio
import logging
import threading
import signal
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch
from backend.artifact_store import ArtifactStore
from backend.mesh_store import PostgresRegistry

class PersistenceSafety(unittest.TestCase):
    def test_concurrent_same_artifact_is_complete(self):
        with tempfile.TemporaryDirectory() as root:
            store = ArtifactStore(Path(root))
            with ThreadPoolExecutor(max_workers=8) as pool:
                records = list(pool.map(lambda _: store.ingest_bytes(b'evidence', filename='input.json'), range(32)))
            self.assertEqual(len({r['artifact_id'] for r in records}), 1)
            self.assertEqual(store.resolve(records[0]['artifact_id'])[1].read_bytes(), b'evidence')

    def test_interrupted_pair_is_repaired(self):
        with tempfile.TemporaryDirectory() as root:
            store = ArtifactStore(Path(root))
            metadata = store.ingest_bytes(b'evidence', filename='input.json')
            path = store.resolve(metadata['artifact_id'])[1]
            (path.parent / 'metadata.json').unlink()
            repaired = store.ingest_bytes(b'evidence', filename='input.json')
            self.assertEqual(repaired['artifact_id'], metadata['artifact_id'])

    def test_non_digest_path_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            store = ArtifactStore(Path(root))
            with self.assertRaises(ValueError):
                store.resolve('sha256:' + '../' + 'a'*61)

    def test_metadata_identity_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            store = ArtifactStore(Path(root))
            metadata = store.ingest_bytes(b'evidence', filename='input.json')
            path = store.resolve(metadata['artifact_id'])[1]
            metadata['artifact_id'] = 'wrong'
            (path.parent/'metadata.json').write_text(json.dumps(metadata))
            with self.assertRaises(ValueError): store.resolve('sha256:'+metadata['sha256'])

    def test_worker_transition_requires_ownership_attempt_and_live_lease(self):
        registry = PostgresRegistry('data_job_runs')
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        @contextmanager
        def connect(): yield connection
        registry._connect = connect
        cursor.fetchone.return_value = None
        with self.assertRaises(ValueError):
            registry.transition_owned('run', {'worker_id':'old','attempt':1}, {'status':'completed'})
        sql, args = cursor.execute.call_args.args
        self.assertIn("value->>'status'='running'", sql)
        self.assertIn("value->>'worker_id'=%s", sql)
        self.assertIn("attempt", sql)
        self.assertIn('timestamptz > now()', sql)
        self.assertEqual(args[-2:], ('old',1))
        cursor.fetchone.return_value = ({'status':'completed'},)
        self.assertEqual(registry.transition_owned('run', {'worker_id':'new','attempt':2}, {'status':'completed'})['status'],'completed')

class ServiceRecovery(unittest.TestCase):
    def test_pipeline_survives_failed_claim(self):
        source = ast.parse(Path('backend/data_pipeline_service/worker.py').read_text())
        fn = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
        records, status, runner = MagicMock(), MagicMock(), MagicMock()
        event = threading.Event()
        calls = [0]
        def claim(**kwargs):
            calls[0] += 1
            if calls[0] == 1: raise ConnectionError('test outage')
            event.set()
            return None
        records.claim_next.side_effect = claim
        # Eliminate polling delay while retaining the real stop condition.
        fake_threading = MagicMock()
        fake_threading.Event.return_value = event
        event.wait = lambda seconds: event.is_set()
        namespace = dict(os=os, logging=logging, threading=fake_threading, signal=MagicMock(),
                         run_records=records, worker_status=status, runner=runner, job_definitions=MagicMock())
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'worker.py','exec'), namespace)
        namespace['run']()
        self.assertEqual(calls[0],2)
        runner.shutdown.assert_called_once()

    def test_catalog_worker_survives_failed_reconcile(self):
        source = ast.parse(Path('backend/data_product_service/worker.py').read_text())
        fn = next(n for n in source.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'run')
        calls = []
        async def reconcile():
            calls.append('attempt')
            raise ConnectionError('test outage')
        async def sleep(interval): raise asyncio.CancelledError()
        fake_asyncio = MagicMock(); fake_asyncio.sleep = sleep
        namespace = dict(os=os, logging=logging, asyncio=fake_asyncio, reconcile_pending=reconcile)
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'worker.py','exec'), namespace)
        with self.assertRaises(asyncio.CancelledError): asyncio.run(namespace['run']())
        self.assertEqual(calls,['attempt'])

    def test_sparql_rejects_external_dataset(self):
        source = ast.parse(Path('backend/graph_service/sparql_service.py').read_text())
        assignment = next(n for n in source.body if isinstance(n, ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_BLOCKED' for t in n.targets))
        namespace = {'re':re}
        exec(compile(ast.Module(body=[assignment],type_ignores=[]),'sparql.py','exec'),namespace)
        self.assertTrue(namespace['_BLOCKED'].search('SELECT * FROM <http://remote/data> WHERE {?s ?p ?o}'))
        self.assertFalse(namespace['_BLOCKED'].search('SELECT * WHERE {?s ?p ?o}'))

    def test_graph_no_auth_and_aliases(self):
        source = ast.parse(Path('backend/graph_service/neo4j_publisher.py').read_text())
        cls = next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='Neo4jPublisher')
        factory = MagicMock()
        namespace = {'os':os,'GraphDatabase':factory, 'Query':lambda text,timeout:(text,timeout), 'Any':object}
        # Postpone annotations: only configuration/health methods execute here.
        module = ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),cls],type_ignores=[])
        exec(compile(ast.fix_missing_locations(module),'publisher.py','exec'),namespace)
        with patch.dict(os.environ,{'NEO4J_URL':'bolt://host:7687','NEO4J_AUTH_MODE':'none'},clear=True):
            publisher = namespace['Neo4jPublisher']()
            self.assertEqual(publisher.health()['status'],'ok')
            self.assertEqual(factory.driver.call_args.kwargs['auth'],None)
            self.assertEqual(factory.driver.call_args.args[0],'bolt://host:7687')
        with patch.dict(os.environ,{'NEO4J_USERNAME':'alias','NEO4J_PASSWORD':'test-only'},clear=True):
            publisher = namespace['Neo4jPublisher']()
            publisher._driver()
            self.assertEqual(factory.driver.call_args.kwargs['auth'],('alias','test-only'))

if __name__ == '__main__': unittest.main()
