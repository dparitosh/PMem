import os
import sys
from contextlib import nullcontext
from types import SimpleNamespace
import socket
import unittest
from unittest.mock import patch
from backend.depo_platform.postgres_connectivity import network_check


class NetworkChecks(unittest.TestCase):
    def test_transport_failures_are_distinct_and_secrets_hidden(self):
        parser=SimpleNamespace(conninfo_to_dict=lambda _: {'host':'database','port':'5432','password':'hidden'})
        for error,status in [(socket.gaierror('hidden'),'dns_failed'),(TimeoutError('hidden'),'timeout'),(ConnectionRefusedError('hidden'),'refused')]:
            with self.subTest(status=status), patch.dict(os.environ,{'DEPO_DATABASE_URL':'secret'}), patch.dict(sys.modules,{'psycopg.conninfo':parser}), patch('socket.create_connection',side_effect=error):
                result=network_check()
                self.assertEqual(result['endpoints'][0]['status'],status)
                self.assertNotIn('hidden',str(result))
                self.assertNotIn('secret',str(result))

    def test_hostaddr_is_actual_transport_target_and_tcp_is_not_login(self):
        parser=SimpleNamespace(conninfo_to_dict=lambda _: {'host':'certificate-name','hostaddr':'10.0.2.22','port':'5432'})
        with patch.dict(os.environ,{'DEPO_DATABASE_URL':'configured'}), patch.dict(sys.modules,{'psycopg.conninfo':parser}), patch('socket.create_connection',return_value=nullcontext()) as connect:
            result=network_check()
            connect.assert_called_once_with(('10.0.2.22',5432),timeout=3)
            self.assertEqual(result['check'],'tcp_only')
            self.assertEqual(result['status'],'ok')
