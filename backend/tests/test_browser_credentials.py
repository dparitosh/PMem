import json
import sys
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import ModuleType
import unittest
from unittest.mock import Mock, patch
from backend.depo_platform import browser_credentials as sessions, credentials


class Rejected(Exception):
    def __init__(self, status, detail):
        self.status_code, self.detail = status, detail


class BrowserCredentialTests(unittest.TestCase):
    def setUp(self):
        self.api = ModuleType('fastapi'); self.api.HTTPException = Rejected
        self.cursor = Mock(); self.cursor.__enter__ = Mock(return_value=self.cursor); self.cursor.__exit__ = Mock(return_value=False)
        self.db = Mock(); self.db.cursor.return_value = self.cursor; self.db.transaction.return_value = nullcontext()
        self.salt = 'a1' * 32
        self.admin_key = 'admin-fixture-' * 4
        self.admin_digest = credentials.key_digest(self.salt, self.admin_key)
        self.rows = [('ADMIN_API_KEY', self.salt, self.admin_digest, None, False),
                     ('GRAPH_READ_TOKEN', self.salt, 'read-digest', None, False),
                     ('INGESTION_WRITE_TOKEN', self.salt, 'upload-digest', None, False),
                     ('DATA_JOB_EXECUTION_TOKEN', self.salt, 'expired-digest', datetime.now(timezone.utc)-timedelta(seconds=1), False)]

    def create(self, writes=False):
        self.cursor.fetchall.return_value = self.rows
        with patch.dict(sys.modules, {'fastapi': self.api}), patch.object(credentials, 'verify_key', return_value='admin-actor'), patch.object(credentials, 'connection', return_value=nullcontext(self.db)):
            result = sessions.create_session(self.admin_key, writes)
        inserts = [call for call in self.cursor.execute.call_args_list if call.args[0].startswith('INSERT')]
        record = json.loads(inserts[-1].args[1][2])
        self.assertNotIn(self.admin_key, str(self.cursor.execute.call_args_list))
        self.assertNotIn(result['token'], str(self.cursor.execute.call_args_list))
        return result, record

    def verify(self, record, profile='GRAPH_READ_TOKEN', digest='read-digest', admin=None):
        self.cursor.fetchone.side_effect = [(record,), admin or (self.admin_digest, None, False)]
        with patch.dict(sys.modules, {'fastapi': self.api}), patch.object(credentials, 'connection', return_value=nullcontext(self.db)):
            return sessions.verify_session(profile, 'depo_session_fixture', digest)

    def test_read_only_default_and_no_plaintext_persistence(self):
        result, record = self.create()
        self.assertEqual(result['profiles'], ['GRAPH_READ_TOKEN'])
        self.assertEqual(self.verify(record), 'admin-actor')

    def test_workflow_scopes_require_explicit_opt_in(self):
        result, record = self.create(True)
        self.assertIn('INGESTION_WRITE_TOKEN', result['profiles'])
        self.assertNotIn('ADMIN_API_KEY', result['profiles'])
        self.assertNotIn('DATA_JOB_EXECUTION_TOKEN', result['profiles'])
        self.assertEqual(self.verify(record, 'INGESTION_WRITE_TOKEN', 'upload-digest'), 'admin-actor')

    def test_scope_escalation_and_rotation_are_rejected(self):
        _, record = self.create()
        for profile, digest in [('INGESTION_WRITE_TOKEN', 'upload-digest'), ('GRAPH_READ_TOKEN', 'rotated-digest'), ('ADMIN_API_KEY', self.admin_digest)]:
            with self.subTest(profile=profile), self.assertRaises(Rejected):
                self.verify(record, profile, digest)

    def test_expired_session_and_revoked_admin_are_rejected(self):
        _, record = self.create()
        with self.assertRaises(Rejected):
            self.verify(record, admin=(self.admin_digest, None, True))
        record['expires_at'] = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        with self.assertRaises(Rejected) as error:
            self.verify(record)
        self.assertEqual(error.exception.status_code, 401)

    def test_replaced_admin_invalidates_sessions(self):
        _, record = self.create()
        with self.assertRaises(Rejected):
            self.verify(record, admin=('new-admin-digest', None, False))

    def test_authority_outage_fails_closed(self):
        with patch.dict(sys.modules, {'fastapi': self.api}), patch.object(credentials, 'connection', side_effect=RuntimeError('private-dsn')):
            with self.assertRaises(Rejected) as error:
                sessions.verify_session('GRAPH_READ_TOKEN', 'depo_session_fixture', 'digest')
        self.assertEqual(error.exception.status_code, 503)
        self.assertNotIn('private-dsn', error.exception.detail)

    def test_service_verifier_accepts_session_and_enforces_scope_revocation(self):
        self.cursor.fetchone.side_effect = None
        self.cursor.fetchone.return_value = (self.salt, 'read-digest', 'reader', None, False)
        with patch.dict(sys.modules, {'fastapi': self.api}), patch.object(credentials, 'connection', return_value=nullcontext(self.db)), patch.object(sessions, 'verify_session', return_value='delegated-admin') as verify:
            self.assertEqual(credentials.verify_key('GRAPH_READ_TOKEN', 'depo_session_fixture'), 'delegated-admin')
            verify.assert_called_once_with('GRAPH_READ_TOKEN', 'depo_session_fixture', 'read-digest')
            self.cursor.fetchone.return_value = (self.salt, 'read-digest', 'reader', None, True)
            with self.assertRaises(Rejected):
                credentials.verify_key('GRAPH_READ_TOKEN', 'depo_session_fixture')

    def test_raw_api_keys_cannot_use_reserved_session_prefix(self):
        with self.assertRaises(ValueError):
            credentials.validate_registration('GRAPH_READ_TOKEN', 'depo_session_' + 'x' * 40, 'actor')


if __name__ == '__main__':
    unittest.main()
