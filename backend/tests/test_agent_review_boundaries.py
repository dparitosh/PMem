"""Exercise actual agent boundary functions without optional service dependencies."""
import ast
import asyncio
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


def load(path, name, namespace):
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    node = next(n for n in tree.body if getattr(n, 'name', '') == name)
    class Imports(ast.NodeTransformer):
        def visit_ImportFrom(self, node): return None
    node = Imports().visit(node)
    node.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    exec(compile(module, path, 'exec'), namespace)
    return namespace[name]


class AgentReviewBoundaries(unittest.IsolatedAsyncioTestCase):
    def test_blank_roots_cannot_grant_repository_access(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'approved').mkdir()
            outside = root / 'outside.ttl'
            outside.write_text('retained data', encoding='utf-8')
            allowed = root / 'approved' / 'inside.ttl'
            allowed.write_text('retained data', encoding='utf-8')
            fn = load('backend/agentic_service/ontology_orchestrator.py', '_allowed_path',
                      {'Path': Path, 'ROOT': root, 'os': os})
            with patch.dict(os.environ, {'ONTOLOGY_AGENT_ALLOWED_ROOTS': 'approved; ;'}):
                with self.assertRaises(ValueError): fn(str(outside))
                self.assertEqual(fn(str(allowed)), allowed)
            with patch.dict(os.environ, {'ONTOLOGY_AGENT_ALLOWED_ROOTS': '; ;'}):
                with self.assertRaises(ValueError): fn(str(allowed))

    async def test_process_nonblocking_request_rejected_before_execution(self):
        class HTTPException(Exception):
            def __init__(self, code, detail): self.status_code = code
        execute = AsyncMock()
        fn = load('backend/agentic_service/single_tool.py', 'execute', {
            'HTTPException': HTTPException, 'execution_mode': lambda: 'process',
            'routes': SimpleNamespace(_execute_workflow=execute)})
        with self.assertRaises(HTTPException) as error:
            await fn({'agent_id': 'governor', 'tool_id': 'publish', 'wait_for_completion': False}, None)
        self.assertEqual(error.exception.status_code, 422)
        execute.assert_not_called()

    async def test_oslc_limit_validation_and_bounded_stream(self):
        reader = load('backend/agentic_service/response_limits.py', 'read_bounded_response',
                      {'response_byte_limit': lambda: 40})
        class Response:
            def raise_for_status(self): pass
            async def aiter_bytes(self):
                for chunk in chunks: yield chunk
        class Context:
            async def __aenter__(self): return self.value
            async def __aexit__(self, *args): closed.append(True)
        class Client(Context):
            def __init__(self, **kwargs): self.value = self
            def stream(self, *args, **kwargs):
                result = Context(); result.value = Response(); return result
        cls = load('backend/agentic_service/oslc_graph_rag.py', 'OSLCGraphRAG', {
            'os': os, 're': re, 'json': json, 'asyncio': asyncio, 'Any': object,
            'httpx': SimpleNamespace(AsyncClient=Client, HTTPError=type('HTTPError', (Exception,), {})),
            'read_bounded_response': reader, 'bounded_timeout_seconds': lambda *a, **k: 2})
        service = cls(); service._base = lambda: 'http://oslc.example'
        for limit in [[], {}, None, True, 0, 21, '10']:
            with self.assertRaises(ValueError): await service.retrieve('part', limit=limit)
        chunks, closed = [b'{"results":[]}'], []
        self.assertEqual((await service.retrieve('part'))['status'], 'no_evidence')
        self.assertEqual(len(closed), 2)
        chunks, closed = [b'x' * 41], []
        with self.assertRaises(RuntimeError): await service.retrieve('part')
        self.assertEqual(len(closed), 2)
