import ast
import asyncio
import os
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.agentic_service.recovery import execution_payload
from backend.core import ollama_limits as limits
from backend.tests import test_durable_workflow_worker as durable_tests


class ArchitectureFailureTests(unittest.TestCase):
    def test_process_and_worker_inputs_reject_nested_secrets(self):
        for field in ('headers', 'credentials', 'service_token', 'client_secret', 'token'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                execution_payload({'inputs': {'nested': [{field: 'private'}]}})
        self.assertEqual(execution_payload({'inputs': {'approval_token': 'private', 'id': 'public'}}),
                         {'inputs': {'id': 'public'}})

    def test_transient_authority_outage_retains_queue_grant_and_offloads_verification(self):
        case = durable_tests.DurableWorkerTests()
        with patch.dict(os.environ, {'GRAPH_READ_TOKEN': 'fixture-read'}, clear=True):
            record, store, routes, modules = case.fixture()
            credentials = modules['backend.depo_platform.credentials']
            credentials.uses_postgres = lambda: True
            loop_thread = threading.get_ident()
            seen = []
            class Unavailable(Exception):
                status_code = 503
            def verify(*args):
                seen.append(threading.get_ident())
                raise Unavailable()
            credentials.verify_key = verify
            async def io(callback, *args, **kwargs):
                return await asyncio.to_thread(callback, *args, **kwargs)
            routes._agent_io = io
            case.run_candidate(record, modules)
            self.assertEqual(store.record, record)
            self.assertTrue(seen)
            self.assertNotEqual(seen[0], loop_thread)
            routes._execute_workflow.assert_not_awaited()
            credentials.verify_key = lambda *args: None
            case.run_candidate(record, modules)
            routes._execute_workflow.assert_awaited_once()

    def test_candidate_query_excludes_compensation_before_limit(self):
        tree = ast.parse(Path('backend/mesh_store.py').read_text(encoding='utf-8'))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'PostgresRegistry')
        fn = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'execution_candidates')
        scope = {'Any': object}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<registry candidates>', 'exec'), scope)
        db = MagicMock()
        cursor = db.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = []
        store = SimpleNamespace(namespace='runs', _connect=lambda: db)
        scope['execution_candidates'](store, 4, '2026-01-01', 'heartbeats')
        query = cursor.execute.call_args.args[0]
        self.assertLess(query.index("value->'compensations'"), query.index('LIMIT'))

    def test_old_success_cannot_close_new_circuit_and_recovery_has_one_probe(self):
        endpoint = 'architecture-fixture'
        limits._states.pop(endpoint, None)
        with patch.dict(os.environ, {'OLLAMA_FAILURE_THRESHOLD': '1', 'OLLAMA_MAX_CONCURRENCY': '4'}, clear=True):
            old = limits._admit(endpoint)
            failing = limits._admit(endpoint)
            limits._failure(failing[0], failing[1], failing[2], OSError('down'), failing[3])
            until = old[0]['until']
            limits._success(old[0], old[3])
            self.assertEqual(old[0]['until'], until)
            with self.assertRaises(RuntimeError): limits._admit(endpoint)
            with patch.object(limits.time, 'monotonic', return_value=until + 1):
                probe = limits._admit(endpoint)
                self.assertTrue(probe[4])
                self.assertIsNone(limits._admit(endpoint))
                limits._success(probe[0], probe[3])
                self.assertEqual(probe[0]['until'], 0)
        limits._states.pop(endpoint, None)
