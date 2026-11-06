"""Dependency-light behavioral regressions for shutdown and object ownership."""
import ast
import hashlib
import os
from pathlib import Path
import threading
from datetime import datetime, timedelta, timezone
from contextlib import nullcontext
from uuid import uuid4
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load_definition(path, name, namespace):
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8-sig'))
    node = next(item for item in tree.body if getattr(item, 'name', '') == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, 'exec'), namespace)
    return namespace[name]


class LifecycleMemoryRegressionTests(unittest.TestCase):
    def test_idle_conversation_resumes_without_extending_absolute_expiry(self):
        values = {}
        clock = [datetime.now(timezone.utc)]
        class Rejected(Exception):
            def __init__(self, status, detail): self.status_code = status
        store = SimpleNamespace(advisory_lock=lambda _: nullcontext(True), get=values.get,
                                put=lambda key, value: values.update({key: value}))
        namespace = {'now': lambda: clock[0], 'owner': lambda request, actor: actor,
                     'store': store, 'HTTPException': Rejected, 'uuid4': uuid4,
                     'datetime': datetime, 'timedelta': timedelta,
                     'bounded_timeout_seconds': lambda name, **kwargs: kwargs['default']}
        open_session = load_definition('backend/agentic_service/sessions.py', 'open_session', namespace)
        request = SimpleNamespace(headers={})
        record = open_session(request, 'alice')
        absolute = record['expires_at']
        clock[0] += timedelta(hours=1)
        self.assertEqual(open_session(request, 'alice', record['session_id'])['expires_at'], absolute)
        clock[0] += timedelta(days=1)
        with self.assertRaises(Rejected) as expired:
            open_session(request, 'alice', record['session_id'])
        self.assertEqual(expired.exception.status_code, 410)

    def test_history_filters_other_owners_and_incomplete_turns(self):
        page = lambda **kwargs: (3, [
            {'owner': 'alice', 'status': 'completed', 'response': 'retained'},
            {'owner': 'bob', 'status': 'completed', 'response': 'private'},
            {'owner': 'alice', 'status': 'running', 'response': 'partial'},
        ])
        turns = load_definition('backend/agentic_service/router.py', '_session_turns',
                                {'companion_job_store': SimpleNamespace(page=page)})
        self.assertEqual(turns({'session_id': 'one', 'owner': 'alice'}),
                         [{'owner': 'alice', 'status': 'completed', 'response': 'retained'}])

    def test_windows_runtime_delivers_stop_and_cleans_request(self):
        from backend.depo_platform import windows_runtime as runtime
        called = threading.Event()
        request = ROOT / 'logs' / 'windows-services' / f'stop-{os.getpid()}.request'
        request.parent.mkdir(parents=True, exist_ok=True)
        def target(*args, **kwargs):
            request.write_text('stop')
            self.assertTrue(called.wait(3), 'cooperative stop was not delivered')
        with patch.object(runtime.sys, 'argv', ['runtime', 'fake_worker']), patch.object(
                runtime.runpy, 'run_module', target), patch.object(runtime._thread, 'interrupt_main', called.set):
            runtime.main()
        self.assertFalse(request.exists())

    def test_browser_renewal_preserves_owner_but_other_actor_isolated(self):
        owner = load_definition('backend/agentic_service/sessions.py', 'owner',
                                {'hashlib': hashlib, 'os': os})
        request = lambda key: SimpleNamespace(headers={'authorization': 'Bearer ' + key})
        with patch.dict(os.environ, {'AUTH_MODE': 'token'}):
            self.assertEqual(owner(request('depo_session_first'), 'alice'),
                             owner(request('depo_session_second'), 'alice'))
            self.assertNotEqual(owner(request('depo_session_first'), 'alice'),
                                owner(request('depo_session_first'), 'bob'))
            self.assertNotEqual(owner(request('raw-first'), 'alice'),
                                owner(request('raw-second'), 'alice'))

    def test_scheduler_retains_live_thread_and_does_not_retry_after_stop(self):
        cls = load_definition('backend/data_pipeline_service/scheduler.py', 'ScheduledJobSupervisor',
                              {'threading': threading, 'Callable': __import__('typing').Callable,
                               'Any': __import__('typing').Any,
                               'bounded_timeout_seconds': lambda *a, **k: 0.01})
        scheduler = cls(lambda *a: None)
        thread = SimpleNamespace(join=lambda **k: None, is_alive=lambda: True)
        scheduler._thread = thread
        with self.assertRaises(RuntimeError):
            scheduler.stop()
        self.assertIs(scheduler._thread, thread)
        self.assertTrue(scheduler._stop.is_set())

    def test_cache_generation_change_and_mutation_isolation(self):
        from backend.core import graphvis_cache as cache
        generation = ['one']
        with patch.object(cache, 'GRAPHVIS_CACHE_ENABLED', True), patch(
                'backend.depo_platform.maintenance.cache_generation', lambda: generation[0]):
            source = {'nodes': [1]}
            cache.store_cached_graph(source)
            source['nodes'].append(2)
            result = cache.get_cached_graph()
            result['nodes'].append(3)
            self.assertEqual(cache.get_cached_graph(), {'nodes': [1]})
            generation[0] = 'two'
            self.assertIsNone(cache.get_cached_graph())
            self.assertIsNone(cache.graphvis_cache['data'])


if __name__ == '__main__':
    unittest.main()
