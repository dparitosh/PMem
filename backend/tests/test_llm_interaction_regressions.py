"""Isolated lifecycle regressions; no live model or database is required."""
import ast
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock


def functions(path, names, scope):
    nodes = [n for n in ast.parse(Path(path).read_text(encoding='utf-8')).body
             if getattr(n, 'name', '') in names]
    for node in nodes:
        node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), path, 'exec'), scope)
    return scope


class InferenceDeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_emits_saved_result_reference_before_completion(self):
        async def io(fn, *args): return fn(*args)
        async def chat(*args, **kwargs):
            return {'response': 'answer', 'evidence': [], 'sources': [], 'answerable': True,
                    'run_id': 'run', 'retained_prompt_job_id': 'saved-result'}
        scope = functions('backend/agentic_service/router.py', {'companion_stream'}, {
            'ChatRequest': object, 'Request': object, 'asyncio': asyncio, 'json': json,
            'StreamingResponse': lambda events, **kw: events, '_agent_io': io, '_companion_chat': chat,
            'graph_read_identity': lambda request: 'owner',
            'sessions': SimpleNamespace(open_session=lambda *args: {'session_id':'session', 'expires_at':'future'})})
        payload = SimpleNamespace(session_id=None, model_copy=lambda **kw: object())
        stream = await scope['companion_stream'](payload, object())
        events = [json.loads(value.removeprefix('data: ').strip()) async for value in stream]
        self.assertEqual(events[-2]['retained_prompt_job_id'], 'saved-result')
        self.assertTrue(events[-1]['done'])

    async def test_proposal_snapshot_exists_when_inference_fails(self):
        class Client:
            def __init__(self, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
        async def post(*args): raise TimeoutError()
        scope = functions('backend/agentic_service/local_llm.py', {'suggest_tool'}, {
            '__package__': 'backend.agentic_service', 'os': os,
            'settings': lambda: ('ollama', 'fixture-model', 'http://host', 30, {}),
            'httpx': SimpleNamespace(AsyncClient=Client), '_post_json': post})
        snapshot = {}
        with patch.dict(os.environ, {'OLLAMA_CHAT_API_URL': 'http://host/api/chat', 'OLLAMA_PROPOSAL_MODE': 'structured'}):
            with self.assertRaises(TimeoutError):
                await scope['suggest_tool']({'id': 'fixture'}, [{'id': 'read', 'input_schema': {'type': 'object'}}],
                                            'Inspect terms', prompt_details=snapshot)
        self.assertEqual(snapshot['user_request'], 'Inspect terms')
        self.assertIn('Inspect terms', snapshot['user_prompt'])
        self.assertIn('Never reveal', snapshot['system_prompt'])

    async def test_timeouts_open_circuit_but_client_cancellation_does_not(self):
        from backend.core import ollama_limits as limits
        endpoint = 'http://isolated-test/api/chat'
        limits._states.pop(endpoint, None)
        with patch('backend.core.ollama_auth.ollama_timeout', return_value=.01), patch.dict(os.environ, {'OLLAMA_FAILURE_THRESHOLD': '3'}):
            for _ in range(3):
                with self.assertRaises(TimeoutError):
                    async with limits.request_slot(endpoint):
                        await asyncio.sleep(1)
            self.assertEqual(limits._states[endpoint]['failures'], 3)
            self.assertEqual(limits._states[endpoint]['active'], 0)
            with self.assertRaisesRegex(RuntimeError, 'circuit'):
                async with limits.request_slot(endpoint):
                    pass
        limits._states.pop(endpoint)
        with self.assertRaises(asyncio.CancelledError):
            async with limits.request_slot(endpoint):
                raise asyncio.CancelledError()
        self.assertEqual(limits._states[endpoint]['failures'], 0)
        self.assertEqual(limits._states[endpoint]['active'], 0)
        limits._states.pop(endpoint)


class RetainedResultTests(unittest.TestCase):
    def test_owned_result_survives_session_expiry_and_other_owner_is_denied(self):
        class HTTPError(Exception):
            def __init__(self, status_code, detail): self.status_code = status_code
        sessions = SimpleNamespace(owner=lambda *args: 'owner', open_session=MagicMock(side_effect=AssertionError('Must not renew expired session')))
        record = {'owner': 'owner', 'session_id': 'expired', 'status': 'completed', 'response': 'saved'}
        scope = functions('backend/agentic_service/router.py', {'companion_job_status'}, {
            'Request': object, 'HTTPException': HTTPError, 'sessions': sessions,
            'graph_read_identity': lambda request: 'actor', 'companion_job_store': SimpleNamespace(get=lambda key: record)})
        self.assertEqual(scope['companion_job_status']('job', object())['response'], 'saved')
        sessions.open_session.assert_not_called()
        record['owner'] = 'other'
        with self.assertRaises(HTTPError) as failure: scope['companion_job_status']('job', object())
        self.assertEqual(failure.exception.status_code, 403)

    def test_retention_is_scoped_to_completed_records(self):
        from backend.mesh_store import PostgresRegistry
        registry = PostgresRegistry('agentic_companion_jobs')
        connection = MagicMock()
        cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.rowcount = 2
        with patch.object(registry, '_connect', return_value=connection):
            self.assertEqual(registry.prune_completed(30), 2)
        sql, args = cursor.execute.call_args.args
        self.assertIn("value->>'status'='completed'", sql)
        self.assertIn('namespace=%s', sql)
        self.assertEqual(args, ('agentic_companion_jobs', 30))
        with self.assertRaises(ValueError): registry.prune_completed(0)

    def test_session_accepts_full_validated_thirty_day_lifetime(self):
        from datetime import datetime, timezone, timedelta
        from backend.depo_platform.network import bounded_timeout_seconds
        current = datetime.now(timezone.utc)
        store = MagicMock()
        store.get.return_value = None
        scope = functions('backend/agentic_service/sessions.py', {'open_session'}, {
            'now': lambda: current, 'owner': lambda *a: 'owner', 'uuid4': lambda: 'session',
            'store': store, 'timedelta': timedelta, 'bounded_timeout_seconds': bounded_timeout_seconds})
        with patch.dict(os.environ, {'AGENT_SESSION_MAX_SECONDS': '2592000'}):
            result = scope['open_session'](object(), 'actor')
        self.assertEqual(datetime.fromisoformat(result['expires_at']) - current, timedelta(days=30))


class EvidenceAndDiagnosticsTests(unittest.TestCase):
    def test_descriptions_preserved_without_forwarding_credentials(self):
        scope = functions('backend/agentic_service/companion.py', {'descriptive_properties'}, {})
        result = scope['descriptive_properties']({'definition': 'A physical component', 'range': ['Part'], 'password': 'secret', 'description': 'x'*2000})
        self.assertEqual(result['definition'], 'A physical component')
        self.assertEqual(result['range'], ['Part'])
        self.assertNotIn('password', result)
        self.assertEqual(len(result['description']), 1000)

    def test_failure_categories_do_not_expose_response_bodies(self):
        class HTTPError(Exception): pass
        class ConnectError(HTTPError): pass
        class ReadTimeout(HTTPError): pass
        scope = functions('backend/agentic_service/local_llm.py', {'failure_status'}, {
            'httpx': SimpleNamespace(HTTPError=HTTPError, ConnectError=ConnectError, TimeoutException=ReadTimeout)})
        classify = scope['failure_status']
        for exc, expected in [(TimeoutError(), 'timeout'), (ConnectError(), 'connection_failed'),
                              (json.JSONDecodeError('invalid', '', 0), 'invalid_json'), (ValueError(), 'invalid_response')]:
            self.assertEqual(classify(exc), expected)
        exc = HTTPError('upstream-secret')
        exc.response = SimpleNamespace(status_code=429)
        self.assertEqual(classify(exc), 'rate_limited')
