import os
import sys
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import ModuleType
from unittest import TestCase, main
from unittest.mock import Mock, patch
from backend.depo_platform import credentials


class Rejected(Exception):
    def __init__(self, status, detail):
        self.status_code, self.detail = status, detail


class CentralCredentialTests(TestCase):
    def setUp(self):
        self.fastapi = ModuleType('fastapi'); self.fastapi.HTTPException = Rejected
        self.cursor = Mock(); self.cursor.__enter__ = Mock(return_value=self.cursor); self.cursor.__exit__ = Mock(return_value=False)
        self.db = Mock(); self.db.cursor.return_value = self.cursor; self.db.transaction.return_value = nullcontext()
        self.key = 'random-fixture-value-' * 3
        self.salt = 'a1' * 32

    def verify(self, row, key=None):
        self.cursor.fetchone.return_value = row
        with patch.dict(sys.modules, {'fastapi': self.fastapi}), patch.object(credentials, 'connection', return_value=nullcontext(self.db)):
            return credentials.verify_key('GRAPH_READ_TOKEN', self.key if key is None else key)

    def test_hash_and_actor_are_central(self):
        digest = credentials.key_digest(self.salt, self.key)
        self.assertNotIn(self.key, digest)
        self.assertEqual(self.verify((self.salt, digest, 'central-actor', None, False)), 'central-actor')
        with self.assertRaises(Rejected) as caught:
            self.verify((self.salt, digest, 'actor', None, False), 'other-key')
        self.assertEqual(caught.exception.status_code, 403)

    def test_expiry_revocation_and_missing_profile_fail_closed(self):
        digest = credentials.key_digest(self.salt, self.key)
        for row, status in [(None,503), ((self.salt,digest,'actor',None,True),403),
                            ((self.salt,digest,'actor',datetime.now(timezone.utc)-timedelta(seconds=1),False),401)]:
            with self.subTest(status=status), self.assertRaises(Rejected) as caught: self.verify(row)
            self.assertEqual(caught.exception.status_code,status)

    def test_database_outage_never_accepts_environment_key(self):
        with patch.dict(sys.modules, {'fastapi':self.fastapi}), patch.object(credentials,'connection',side_effect=RuntimeError('sensitive connection text')):
            with self.assertRaises(Rejected) as caught: credentials.verify_key('GRAPH_READ_TOKEN',self.key)
        self.assertEqual(caught.exception.status_code,503); self.assertNotIn('sensitive',caught.exception.detail)

    def test_registration_is_hashed_and_audited_in_one_transaction(self):
        self.cursor.rowcount=1
        credentials.register_key('GRAPH_READ_TOKEN',self.key,'reader',audit_actor='admin',db=self.db)
        self.db.transaction.assert_called_once()
        calls=self.cursor.execute.call_args_list
        self.assertNotIn(self.key,str(calls)); self.assertEqual(calls[-1].args[1],('GRAPH_READ_TOKEN','rotate','admin'))

    def test_bootstrap_never_overwrites_existing_records(self):
        self.cursor.fetchone.return_value=(1,)
        self.cursor.fetchall.return_value=[('ADMIN_API_KEY',),('GRAPH_READ_TOKEN',)]
        with patch.dict(os.environ,{'DEPO_CREDENTIAL_STORE':'postgres','GRAPH_READ_TOKEN':'old-key'}):
            credentials.bootstrap_environment(self.db)
        self.assertFalse(any('INSERT' in call.args[0] for call in self.cursor.execute.call_args_list))

    def test_registration_requires_strong_key_and_actor(self):
        with self.assertRaises(ValueError): credentials.validate_registration('GRAPH_READ_TOKEN','short','actor')
        with self.assertRaises(ValueError): credentials.validate_registration('GRAPH_READ_TOKEN',self.key,'')
        with self.assertRaises(ValueError): credentials.validate_registration('GRAPH_READ_TOKEN',self.key,'actor',datetime.now())
        with patch.dict(os.environ,{'DEPO_CREDENTIAL_STORE':'unknown'}):
            with self.assertRaises(RuntimeError): credentials.uses_postgres()


if __name__ == '__main__': main()
