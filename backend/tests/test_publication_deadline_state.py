import ast
import pickle
import subprocess
import threading
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from backend.depo_platform.rdf_preparation import prepare_rdf
from backend.depo_platform.publication_state import missing_receipt_status

class DeadlineTests(unittest.TestCase):
    def test_preparation_timeout_terminates_subprocess_call(self):
        with patch('backend.depo_platform.rdf_preparation.subprocess.run', side_effect=subprocess.TimeoutExpired('worker',1)) as run:
            with self.assertRaises(TimeoutError): prepare_rdf(b'ttl','turtle')
        self.assertGreater(run.call_args.kwargs['timeout'],0)

    def test_serialization_result_is_returned(self):
        with patch('backend.depo_platform.rdf_preparation.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=pickle.dumps(b'ttl'))):
            self.assertEqual(prepare_rdf(b'rdf','xml'), b'ttl')

    def test_missing_receipt_preserves_active_attempt(self):
        record={'status':'publishing','active_until':(datetime.now(timezone.utc)+timedelta(seconds=30)).isoformat()}
        self.assertEqual(missing_receipt_status(record),'publishing')
        record['active_until']=(datetime.now(timezone.utc)-timedelta(seconds=30)).isoformat()
        self.assertEqual(missing_receipt_status(record),'unverified')
        self.assertEqual(missing_receipt_status({'status':'publishing'}),'unverified')

    def test_keyed_locks_allow_other_ontology_and_release_entries(self):
        from contextlib import contextmanager
        tree=ast.parse(Path('backend/ontology_service/catalog.py').read_text(encoding='utf-8'))
        fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_operation_lock')
        scope={'contextmanager':contextmanager,'threading':threading}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<locks>','exec'),scope)
        class Locks:
            _lock_guard=threading.Lock()
            _operation_locks={}
            _operation_lock=scope['_operation_lock']
        acquired=threading.Event()
        with Locks._operation_lock('a'):
            def other():
                with Locks._operation_lock('b'): acquired.set()
            thread=threading.Thread(target=other)
            thread.start()
            self.assertTrue(acquired.wait(1))
            thread.join(1)
        self.assertEqual(Locks._operation_locks,{})

    def test_idle_graph_releases_failed_attempt_but_not_active_preparation(self):
        self.assertEqual(missing_receipt_status({'status':'unverified'},graph_idle=True),'not_published')
        active={'status':'publishing','phase':'rdf_preparation','active_until':(datetime.now(timezone.utc)+timedelta(seconds=30)).isoformat()}
        self.assertEqual(missing_receipt_status(active,graph_idle=True),'publishing')
        active['active_until']=(datetime.now(timezone.utc)-timedelta(seconds=30)).isoformat()
        self.assertEqual(missing_receipt_status(active,graph_idle=True),'not_published')

    def test_graph_lock_activity_is_visible_and_released_after_failure(self):
        from backend.depo_platform.graph_publication_lock import publication_lock
        with patch.dict('os.environ',{'DEPO_DATABASE_URL':'','DATABASE_URL':''}):
            with self.assertRaises(RuntimeError):
                with publication_lock('demo') as acquired:
                    self.assertTrue(acquired)
                    with publication_lock('demo') as idle: self.assertFalse(idle)
                    with publication_lock('other') as idle: self.assertTrue(idle)
                    raise RuntimeError('write failed')
            with publication_lock('demo') as idle: self.assertTrue(idle)
