import ast
import logging
import os
import signal
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from backend.data_pipeline_service.schema_limits import read_schema_bytes


class DataJobAudit(unittest.TestCase):
    def test_schema_limit_checked_before_read(self):
        path = Mock()
        path.stat.return_value.st_size = 26 * 1024 * 1024
        with self.assertRaises(ValueError):
            read_schema_bytes(path)
        path.open.assert_not_called()

    def test_schema_read_detects_growth_and_remaining_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'schema.xsd'
            path.write_bytes(b'12345')
            self.assertEqual(read_schema_bytes(path, remaining_bytes=5), b'12345')
            with self.assertRaises(ValueError):
                read_schema_bytes(path, remaining_bytes=4)
        from io import BytesIO
        path = Mock()
        path.stat.return_value.st_size = 4
        path.open.return_value = BytesIO(b'123456')
        with self.assertRaises(ValueError):
            read_schema_bytes(path, remaining_bytes=5)

    def test_rdf_total_is_not_truncated_to_chart_limit(self):
        import re, time, uuid
        from collections import deque
        tree = ast.parse(Path('backend/data_pipeline_service/runner.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SparkJobRunner')
        node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'rdf_quality_statistics')
        class RDD:
            def __init__(self, rows): self.rows = rows
            def map(self, f): return RDD([f(row) for row in self.rows])
            def filter(self, f): return RDD([row for row in self.rows if f(row)])
            def count(self): return len(self.rows)
            def reduceByKey(self, f):
                values = {}
                for key, value in self.rows:
                    values[key] = f(values[key], value) if key in values else value
                return RDD(list(values.items()))
            def takeOrdered(self, limit, key): return sorted(self.rows, key=key)[:limit]
        lines = RDD([f'<urn:s> <urn:predicate:{i}> <urn:o> .' for i in range(75)])
        store = SimpleNamespace(resolve=lambda a:({'filename':'sample.nt'},Path('sample.nt').resolve()))
        ns = {'Any':object, 'ArtifactStore':lambda:store, 're':re, 'time':time, 'uuid':uuid}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual RDF runner>','exec'),ns)
        runner = SimpleNamespace(_lock=threading.Lock(), _spark_session=lambda:SimpleNamespace(sparkContext=SimpleNamespace(textFile=lambda p:lines)),
            _now=lambda:'2026-10-06', _runs=deque())
        result = ns['rdf_quality_statistics'](runner,{'artifact_id':'sha256:test'},correlation_id='test')
        self.assertEqual(result['counts']['distinct_predicates'],75)
        self.assertEqual(len(result['predicate_statistics']),50)

    def worker(self, attempt, telemetry_fails=False):
        tree = ast.parse(Path('backend/data_pipeline_service/worker.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
        stop = threading.Event()
        class Threads:
            calls = 0
            Thread = threading.Thread
            @classmethod
            def Event(cls):
                cls.calls += 1
                return stop if cls.calls == 1 else threading.Event()
        record = {'run_id':'run', 'job_id':'job', 'job_version':'1.0.0', 'worker_id':'worker', 'attempt':attempt}
        def claim(**kw):
            stop.set()  # finish the current iteration, then exit without waiting
            return record
        records = SimpleNamespace(worker_identity=lambda:'worker', claim_next=claim,
            failed=Mock(), replay_payload=Mock(return_value={}), heartbeat=Mock(), get=Mock())
        def telemetry(*args, **kw):
            if telemetry_fails and kw.get('status') == 'busy':
                raise RuntimeError('telemetry offline')
        execute = Mock()
        ns = {'os':os, 'logging':logging, 'signal':SimpleNamespace(SIGINT=signal.SIGINT, SIGTERM=signal.SIGTERM, signal=lambda *a:None),
              'threading':Threads, 'run_records':records, 'worker_status':SimpleNamespace(put=telemetry),
              'job_definitions':SimpleNamespace(get=lambda *a:{'enabled':True,'lifecycle_state':'approved','retry_policy':{'max_attempts':2}}),
              'runner':SimpleNamespace(health=lambda:{},shutdown=lambda:None), 'execute_claimed_job':execute}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual worker>','exec'),ns)
        ns['run']()
        return records, execute

    def test_abandoned_execution_stops_at_retry_limit(self):
        records, execute = self.worker(3)
        execute.assert_not_called()
        records.failed.assert_called_once()
        records.replay_payload.assert_not_called()

    def test_last_allowed_attempt_still_executes(self):
        records, execute = self.worker(2)
        execute.assert_called_once()
        records.failed.assert_not_called()

    def test_telemetry_failure_does_not_abandon_claim(self):
        records, execute = self.worker(1, telemetry_fails=True)
        execute.assert_called_once()
        records.failed.assert_not_called()


if __name__ == '__main__':
    unittest.main()
