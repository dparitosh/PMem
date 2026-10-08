import ast
import asyncio
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


class Failure(Exception):
    def __init__(self, status, detail): self.status_code, self.detail = status, detail


class ChildJobCompletionTests(unittest.IsolatedAsyncioTestCase):
    def operation(self, replies):
        calls = []
        iterator = iter(replies)
        class Client:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
        async def request(client, method, endpoint, **kw):
            calls.append((method, endpoint))
            value = next(iterator)
            if isinstance(value, Exception): raise value
            return SimpleNamespace(json=lambda: value)
        async def sleep(seconds): await asyncio.sleep(0)
        scope = {'httpx': SimpleNamespace(AsyncClient=Client, HTTPError=OSError), 'HTTPException': Failure,
                 '_bounded_tool_request': request, '_base': lambda service: 'http://pipeline/api/v1', 'asyncio': SimpleNamespace(sleep=sleep)}
        node = next(node for node in ast.parse(Path('backend/agentic_service/router.py').read_text(encoding='utf-8')).body if getattr(node, 'name', '') == '_await_pipeline_run')
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<child-job>', 'exec'), scope)
        return scope['_await_pipeline_run'], calls

    async def call(self, replies):
        operation, calls = self.operation(replies)
        network = ModuleType('backend.depo_platform.network')
        network.service_bearer_headers = lambda *args, **kwargs: {'Authorization': 'verified-service-profile'}
        with patch.dict(sys.modules, {'backend.depo_platform.network': network}):
            result = await operation('child-1')
        return result, calls

    async def test_accepted_job_is_polled_until_completed(self):
        result, calls = await self.call([{'run_id':'child-1','status':state} for state in ('queued','running','completed')])
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(method == 'GET' for method, endpoint in calls))

    async def test_transient_read_failure_does_not_resubmit_job(self):
        result, calls = await self.call([OSError('offline'), {'run_id':'child-1','status':'completed'}])
        self.assertEqual(len(calls), 2)
        self.assertEqual(result['run_manifest']['run_id'], 'child-1')

    async def test_failed_and_wrong_job_receipts_are_rejected(self):
        for response in ({'run_id':'child-1','status':'failed'}, {'run_id':'wrong','status':'completed'}):
            with self.assertRaises(Failure): await self.call([response])
