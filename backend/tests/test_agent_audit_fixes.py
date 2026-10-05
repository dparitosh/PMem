import ast
import asyncio
import os
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from backend.agentic_service.response_limits import read_bounded_response
from backend.agentic_service.configuration import configuration_status, SERVICE_KEYS
from backend.tests.test_run_id_fixes import RunIds, HTTPException

class AgentAudit(unittest.TestCase):
    def test_response_limit_counts_chunked_decoded_bytes(self):
        class Response:
            async def aiter_bytes(self):
                yield b'123'
                yield b'456'
        with patch.dict(os.environ, {'AGENTIC_MAX_RESPONSE_BYTES': '5'}):
            with self.assertRaises(ValueError): asyncio.run(read_bounded_response(Response()))
        with patch.dict(os.environ, {'AGENTIC_MAX_RESPONSE_BYTES': '6'}):
            self.assertEqual(asyncio.run(read_bounded_response(Response())), b'123456')

    def test_configuration_rejects_all_malformed_service_ports(self):
        with patch.dict(os.environ, {key: 'http://service:invalid/api/v1' for key in SERVICE_KEYS}):
            invalid = configuration_status()['configuration']['invalid_settings']
            self.assertTrue(set(SERVICE_KEYS).issubset(invalid))

    def test_database_offload_does_not_block_event_loop(self):
        tree = ast.parse(Path('backend/agentic_service/router.py').read_text(encoding='utf-8'))
        fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == '_agent_io')
        namespace = {'asyncio': asyncio}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<actual offload>', 'exec'), namespace)
        async def check():
            ticks = []
            async def heartbeat():
                await asyncio.sleep(.01)
                ticks.append(True)
            task = asyncio.create_task(heartbeat())
            with self.assertRaises(TimeoutError):
                async with asyncio.timeout(.03):
                    await namespace['_agent_io'](time.sleep, .08)
            await task
            self.assertEqual(ticks, [True])
        asyncio.run(check())

    def test_dt_cancellation_persists_uncertain_state(self):
        helper = RunIds()
        namespace = helper.namespace()
        writes = []
        namespace.update(approval_identity=lambda *a, **kw: 'actor', dt_run_store=SimpleNamespace(put=lambda key, value: writes.append(dict(value))))
        async def cancelled(*a): raise asyncio.CancelledError()
        namespace['execute_current_plan'] = cancelled
        namespace['httpx'] = SimpleNamespace(HTTPError=type('HTTPError', (Exception,), {}))
        with patch.dict(os.environ, {'DT_AGENT_ENABLED': 'true'}):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(helper.load('dt_run', namespace)({'execution_scope': 'current_plan'}, SimpleNamespace()))
        self.assertEqual(writes[-1]['status'], 'dispatch_uncertain')
        self.assertTrue(writes[-1]['reconciliation_required'])
        self.assertIn('deadline_at', writes[-1])

    def test_workflow_owner_and_legacy_record_access(self):
        import sys
        tree = ast.parse(Path('backend/agentic_service/router.py').read_text(encoding='utf-8'))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'workflow_run')
        fn.decorator_list = []
        record = {'run_id': 'run-one', 'status': 'completed', 'owner': 'owner'}
        def denied(*a, **kw): raise HTTPException(403, 'Denied')
        namespace = RunIds().namespace()
        namespace['workflow_store'] = SimpleNamespace(get=lambda key: record)
        namespace['sessions'] = SimpleNamespace(owner=lambda *a: 'other')
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<actual workflow read>', 'exec'), namespace)
        module = SimpleNamespace(service_write_identity=denied)
        with patch.dict(sys.modules, {'backend.depo_platform.authorization': module}):
            with self.assertRaises(HTTPException): namespace['workflow_run']('run-one', SimpleNamespace())
            namespace['workflow_controls'] = SimpleNamespace(get=lambda key: None)
            namespace['sessions'] = SimpleNamespace(owner=lambda *a: 'owner')
            self.assertNotIn('owner', namespace['workflow_run']('run-one', SimpleNamespace()))
            record.pop('owner')
            with self.assertRaises(HTTPException): namespace['workflow_run']('run-one', SimpleNamespace())
            module.service_write_identity = lambda *a, **kw: 'supervisor'
            self.assertEqual(namespace['workflow_run']('run-one', SimpleNamespace())['run_id'], 'run-one')

if __name__ == '__main__': unittest.main()
