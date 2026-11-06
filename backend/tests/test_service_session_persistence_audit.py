"""Regression coverage without requiring a live application VM or database."""
import ast
import asyncio
import os
import unittest
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from backend.mesh_store import PostgresRegistry, InMemoryRegistry


def function(path, name, namespace):
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, 'exec', flags=__import__('__future__').annotations.compiler_flag), namespace)
    return namespace[name]


class HTTPError(Exception): pass
class ConnectError(HTTPError): pass
class TimeoutException(HTTPError): pass
class HTTPStatusError(HTTPError): pass


class AuditRegressions(unittest.TestCase):
    def health(self, body=None, failure=None):
        observed = {}
        class Client:
            def __init__(self, **kwargs): observed.update(kwargs)
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            @asynccontextmanager
            async def stream(self, method, endpoint, **kwargs):
                observed['endpoint'] = endpoint
                if failure: raise failure
                async def chunks(): yield __import__('json').dumps(body).encode()
                yield SimpleNamespace(raise_for_status=lambda: None, aiter_bytes=chunks)
        ns = {'__name__': 'backend.agentic_service.local_llm', '__package__': 'backend.agentic_service', 'asyncio': asyncio, 'os': os,
              'settings': lambda: ('ollama', 'llama3', 'http://127.0.0.1:11434', 30, {'api-key': 'private-key'}),
              'httpx': SimpleNamespace(AsyncClient=Client, HTTPError=HTTPError, ConnectError=ConnectError, TimeoutException=TimeoutException, HTTPStatusError=HTTPStatusError)}
        result = asyncio.run(function('backend/agentic_service/local_llm.py', '_health', ns)())
        self.assertNotIn('private-key', str(result))
        self.assertEqual(observed['trust_env'], False)
        self.assertEqual(result['endpoint'], 'http://127.0.0.1:11434/api/tags')
        return result

    def test_ollama_model_alias_and_valid_empty_list(self):
        self.assertEqual(self.health({'models': [{'name': 'llama3:latest'}]})['status'], 'ready')
        self.assertEqual(self.health({'models': []})['status'], 'model_missing')

    def test_ollama_reports_network_failure_categories(self):
        for error, status in [(ConnectError(), 'connection_failed'), (TimeoutException(), 'timeout'), (TimeoutError(), 'timeout'), (HTTPError(), 'transport_error')]:
            with self.subTest(status=status): self.assertEqual(self.health(failure=error)['status'], status)

    def test_ollama_malformed_responses_are_not_model_missing(self):
        for body in [None, {}, {'models': None}, {'models': [None]}, {'models': [{'name': []}]}]:
            with self.subTest(body=body): self.assertEqual(self.health(body)['status'], 'invalid_response')

    def registry(self):
        registry = PostgresRegistry('data_job_runs')
        db = MagicMock()
        cursor = db.cursor.return_value.__enter__.return_value
        @contextmanager
        def connect(): yield db
        registry._connect = connect
        return registry, db, cursor

    def test_identifier_count_and_page_share_one_snapshot(self):
        registry, db, cursor = self.registry()
        cursor.fetchone.return_value = (2,)
        cursor.fetchall.return_value = [('a',), ('b',)]
        self.assertEqual(registry.page_keys(0, 2), (2, ['a', 'b']))
        db.transaction.assert_called_once()
        self.assertEqual(cursor.execute.call_args_list[0].args[0], 'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')

    def test_job_claim_compares_instants_instead_of_timestamp_strings(self):
        registry, _, cursor = self.registry()
        cursor.fetchone.return_value = None
        registry.claim_next(worker_id='w')
        sql = cursor.execute.call_args.args[0]
        self.assertIn('::timestamptz', sql)
        self.assertNotIn('CAST(%s AS text))', sql)
        # These representations sort oppositely as text and as actual instants.
        older, newer = '2026-10-06T10:00:00+05:30', '2026-10-06T05:00:00+00:00'
        self.assertGreater(older, newer)
        self.assertLess(datetime.fromisoformat(older), datetime.fromisoformat(newer))

    def test_missing_catalog_configuration_schedules_backoff(self):
        ns = {'os': os, 'datetime': datetime, 'timezone': timezone, 'timedelta': timedelta, '_now': lambda: datetime.now(timezone.utc).isoformat()}
        register = function('backend/data_product_service/router.py', '_register_catalog', ns)
        for env in [{'DATA_CATALOG_URL': '', 'CATALOG_SERVICE_TOKEN': ''}, {'DATA_CATALOG_URL': 'http://catalog/api/v1', 'CATALOG_SERVICE_TOKEN': ''}]:
            with patch.dict(os.environ, env):
                result = asyncio.run(register({'catalog_attempts': 2}))
            self.assertEqual(result['status'], 'pending_catalog_registration')
            self.assertEqual(result['catalog_attempts'], 3)
            self.assertGreater(datetime.fromisoformat(result['next_catalog_attempt_at']), datetime.now(timezone.utc))

    def test_revocation_remains_durable_when_remote_delivery_is_interrupted(self):
        store = InMemoryRegistry()
        store.put('p:1.0.0', {'status': 'published', 'lifecycle_state': 'published'})
        async def interrupted(record):
            self.assertEqual(store.get('p:1.0.0')['lifecycle_state'], 'revoked')
            raise asyncio.CancelledError()
        @asynccontextmanager
        async def product_lock(key): yield True
        async def product_io(function, *args): return function(*args)
        ns = {'_product_lock': product_lock, '_product_io': product_io, 'store': store, '_register_catalog': interrupted, 'Request': object,
              'approval_identity': lambda *a, **k: 'approver', '_now': lambda: '2026-10-06T00:00:00Z'}
        function('backend/data_product_service/router.py', '_public_product', ns)
        revoke = function('backend/data_product_service/router.py', 'revoke', ns)
        with self.assertRaises(asyncio.CancelledError): asyncio.run(revoke('p:1.0.0', {}, object()))
        saved = store.get('p:1.0.0')
        self.assertEqual(saved['lifecycle_state'], 'revoked')
        self.assertEqual(saved['status'], 'pending_catalog_registration')

    def test_diagnostic_tool_uses_shared_api_url_and_auth_header(self):
        from backend.core.ollama_auth import ollama_base_url, ollama_headers
        ns = {'ollama_base_url': ollama_base_url, 'ollama_headers': ollama_headers}
        headers = function('tools/diagnostics/ollama_diagnostics.py', '_headers', ns)
        normalize = function('tools/diagnostics/ollama_diagnostics.py', '_base_url', ns)
        with patch.dict(os.environ, {'OLLAMA_API_KEY_HEADER': 'Authorization'}):
            self.assertEqual(headers('fixture'), {'Authorization': 'Bearer fixture'})
        self.assertEqual(normalize('http://server/native/api/chat'), 'http://server/native')

    def test_real_http_probe_ignores_ambient_proxy_and_classifies_malformed_json(self):
        try: import httpx
        except ImportError: self.skipTest('Install HTTPX to run the local HTTP integration check')
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        class Handler(BaseHTTPRequestHandler):
            body = b'{"models":[{"name":"llama3:latest"}]}'
            def do_GET(self):
                self.send_response(200); self.end_headers(); self.wfile.write(self.body)
            def log_message(self, *args): pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            ns = {'__name__': 'backend.agentic_service.local_llm', '__package__': 'backend.agentic_service', 'asyncio': asyncio, 'os': os, 'httpx': httpx, 'settings': lambda: ('ollama', 'llama3', base, 5, {})}
            health = function('backend/agentic_service/local_llm.py', '_health', ns)
            with patch.dict(os.environ, {'HTTP_PROXY': 'http://127.0.0.1:1', 'ALL_PROXY': 'http://127.0.0.1:1', 'NO_PROXY': ''}):
                self.assertEqual(asyncio.run(health())['status'], 'ready')
                Handler.body = b'<html>wrong backend</html>'
                self.assertEqual(asyncio.run(health())['status'], 'invalid_response')
        finally: server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == '__main__': unittest.main()
