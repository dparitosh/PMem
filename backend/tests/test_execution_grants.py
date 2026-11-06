import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from backend.agentic_service.execution_grants import execution_identity, verify_grant


class HttpError(Exception):
    def __init__(self, status, detail):
        self.status_code = status
        super().__init__(detail)


class GrantTests(unittest.TestCase):
    def modules(self, checks):
        def request(scope):
            return SimpleNamespace(headers={k.decode(): v.decode() for k, v in scope['headers']}, state=SimpleNamespace())
        return patch.dict('sys.modules', {
            'fastapi': SimpleNamespace(HTTPException=HttpError),
            'starlette.requests': SimpleNamespace(Request=request),
            'backend.depo_platform.authorization': SimpleNamespace(require_active_token=lambda name: checks.append(('active', name))),
            'backend.depo_platform.credentials': SimpleNamespace(uses_postgres=lambda: True, verify_key=lambda name, key: checks.append((name, key))),
        })

    def test_browser_expiry_is_not_an_execution_dependency(self):
        checks = []
        original = SimpleNamespace(headers={'authorization': 'Bearer depo_session_expired'}, state=SimpleNamespace(request_id='request-1'))
        steps = [{'requires_approval': False, 'tool': {'id': 'read', 'mutates': False}}]
        with patch.dict(os.environ, {'AUTH_MODE': 'token', 'GRAPH_READ_TOKEN': 'server-read'}, clear=True), self.modules(checks):
            execution, _, grant = execution_identity(original, {}, steps)
            verify_grant(grant)  # A later step revalidates PostgreSQL server keys.
        self.assertEqual(execution.headers['authorization'], 'Bearer server-read')
        self.assertEqual(execution.state.request_id, 'request-1')
        self.assertNotIn('depo_session_expired', str(checks))
        self.assertNotIn('server-read', str(grant))
        self.assertEqual(set(grant), {'GRAPH_READ_TOKEN'})

    def test_server_rotation_still_blocks_later_steps(self):
        checks = []
        original = SimpleNamespace(state=SimpleNamespace())
        steps = [{'requires_approval': False, 'tool': {'id': 'read', 'mutates': False}}]
        with patch.dict(os.environ, {'GRAPH_READ_TOKEN': 'before'}, clear=True), self.modules(checks):
            _, _, grant = execution_identity(original, {}, steps)
            os.environ['GRAPH_READ_TOKEN'] = 'after'
            with self.assertRaises(HttpError) as caught:
                verify_grant(grant)
        self.assertEqual(caught.exception.status_code, 403)

    def test_missing_server_keys_reject_before_background_acceptance(self):
        with patch.dict(os.environ, {}, clear=True), self.modules([]):
            with self.assertRaises(HttpError) as caught:
                execution_identity(SimpleNamespace(state=SimpleNamespace()), {},
                    [{'requires_approval': False, 'tool': {'id': 'read', 'mutates': False}}])
        self.assertEqual(caught.exception.status_code, 503)
