"""Deadline composition, cancellation, and synchronous inference regressions."""
import asyncio
import os
import threading
import time
import unittest
import ast
from pathlib import Path
from types import SimpleNamespace
from contextlib import nullcontext
from contextlib import contextmanager
from unittest.mock import patch
from backend.depo_platform import network
from backend.depo_platform.ontology_maintenance import ontology_writer
from backend.core.sync_async import call_async, iterate_async
from backend.core.ollama_limits import request_slot, _states


class BudgetTests(unittest.TestCase):
    def test_agent_default_covers_merge(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertGreater(network.agent_run_timeout_seconds(), 210 + network.ontology_publication_timeout_seconds())

    def test_engineering_default_covers_stages(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertGreater(network.engineering_workflow_timeout_seconds(),
                180 + 4 * network.service_request_timeout_seconds() + network.ontology_publication_timeout_seconds())

    def test_explicit_deadlines_preserved(self):
        with patch.dict(os.environ, {'AGENTIC_RUN_TIMEOUT_SECONDS': '120', 'ENGINEERING_WORKFLOW_TIMEOUT_SECONDS': '240'}):
            self.assertEqual(network.agent_run_timeout_seconds(), 120)
            self.assertEqual(network.engineering_workflow_timeout_seconds(), 240)

    def test_preflight_rejects_invalid_and_clamped_values(self):
        for name, (_, maximum) in network.TIMEOUT_RANGES.items():
            for value in ('nan', 'inf', 'bad', '0', str(maximum + 1)):
                with self.subTest(name=name, value=value), patch.dict(os.environ, {name: value}, clear=True):
                    self.assertEqual(network.validate_timeout_settings(), [name])
            with patch.dict(os.environ, {name: str(maximum)}, clear=True):
                self.assertEqual(network.validate_timeout_settings(), [])

    def test_sync_inference_obeys_total_deadline(self):
        async def inference():
            async with request_slot('test-call-deadline'):
                await asyncio.sleep(10)
        _states.clear()
        with patch('backend.core.ollama_auth.ollama_timeout', return_value=.03):
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                call_async(inference)
            self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(_states['test-call-deadline']['active'], 0)

    def test_sync_stream_obeys_deadline(self):
        async def stream():
            async with request_slot('test-stream-deadline'):
                yield 'first'
                await asyncio.sleep(10)
        _states.clear()
        with patch('backend.core.ollama_auth.ollama_timeout', return_value=.03):
            iterator = iterate_async(stream)
            self.assertEqual(next(iterator), 'first')
            with self.assertRaises(TimeoutError):
                next(iterator)
        self.assertEqual(_states['test-stream-deadline']['active'], 0)

    def test_consumer_close_cancels_stream(self):
        closed = threading.Event()
        async def stream():
            try:
                yield 'first'
                await asyncio.sleep(10)
            finally:
                closed.set()
        iterator = iterate_async(stream)
        self.assertEqual(next(iterator), 'first')
        iterator.close()
        self.assertTrue(closed.wait(1))

    def test_guarded_sync_api_uses_cancellable_async_model(self):
        tree = ast.parse(Path('backend/core/guarded_ollama.py').read_text(encoding='utf-8'))
        classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
        scope = {'Runnable': object, 'Embeddings': object, 'request_slot': request_slot,
                 'call_async': call_async, 'iterate_async': iterate_async, 'ollama_headers': lambda endpoint: {}}
        exec(compile(ast.Module(body=classes, type_ignores=[]), '<guarded>', 'exec'), scope)
        async def answer(*args, **kwargs):
            return 'async answer'
        async def stream(*args, **kwargs):
            yield 'token'
        model = SimpleNamespace(ainvoke=answer, astream=stream, aembed_documents=answer, aembed_query=answer)
        with patch('backend.core.ollama_auth.ollama_timeout', return_value=1):
            self.assertEqual(scope['GuardedOllama'](model, 'test-guard').invoke('question'), 'async answer')
            self.assertEqual(list(scope['GuardedOllama'](model, 'test-guard').stream('question')), ['token'])
            self.assertEqual(scope['GuardedEmbeddings'](model, 'test-guard').embed_query('question'), 'async answer')

    def test_postgres_readiness_uses_probe_budget_not_registry_budget(self):
        tree = ast.parse(Path('backend/depo_platform/service_runtime.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'configured_dependency_status')
        options = {}
        cursor = SimpleNamespace(execute=lambda sql: None)
        def connect(dsn, **kwargs):
            options.update(kwargs)
            return nullcontext(SimpleNamespace(cursor=lambda: nullcontext(cursor)))
        scope = {'os': os, 'Collection': list, '__package__': 'backend.depo_platform'}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<readiness>', 'exec'), scope)
        with patch.dict(os.environ, {'DEPO_DATABASE_URL': 'test', 'DEPO_READINESS_TIMEOUT_SECONDS': '2',
                'DEPO_POSTGRES_CONNECT_TIMEOUT_SECONDS': '60', 'DEPO_REGISTRY_STATEMENT_TIMEOUT_SECONDS': '300'}, clear=True), \
                patch.dict('sys.modules', {'psycopg': SimpleNamespace(connect=connect)}):
            self.assertEqual(scope['configured_dependency_status'](('postgres',))['postgres']['status'], 'ready')
        self.assertEqual(options['connect_timeout'], 2)
        self.assertIn('statement_timeout=2000', options['options'])


class AsyncLockTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_acquisition_keeps_loop_responsive_and_releases_on_owner(self):
        threads = []
        @contextmanager
        def operation():
            threads.append(threading.get_ident())
            time.sleep(.08)
            try:
                yield
            finally:
                threads.append(threading.get_ident())
        @ontology_writer
        async def write():
            raise ValueError('failed write')
        with patch('backend.depo_platform.ontology_maintenance.ontology_operation', operation):
            task = asyncio.create_task(write())
            await asyncio.sleep(.01)
            self.assertFalse(task.done())
            with self.assertRaises(ValueError):
                await task
        self.assertEqual(threads[0], threads[1])
        self.assertNotEqual(threads[0], threading.get_ident())

    async def test_cancel_during_acquisition_releases_lock(self):
        released = threading.Event()
        @contextmanager
        def operation():
            time.sleep(.05)
            try:
                yield
            finally:
                released.set()
        @ontology_writer
        async def write():
            self.fail('Cancelled operation must not write')
        with patch('backend.depo_platform.ontology_maintenance.ontology_operation', operation):
            task = asyncio.create_task(write())
            await asyncio.sleep(.01)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(released.is_set())

    async def test_sync_call_inside_existing_loop(self):
        self.assertEqual(call_async(lambda: asyncio.sleep(0, result='ok')), 'ok')
