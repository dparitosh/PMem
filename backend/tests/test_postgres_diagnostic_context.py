import ast
import ipaddress
import json
import os
import re
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
def failure_function(context):
    source = ast.parse((ROOT/'backend/depo_platform/database_setup.py').read_text(encoding='utf-8'))
    node = next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='_failure_action')
    scope={'re':re,'ipaddress':ipaddress,'_connection_context':lambda:context}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'database_setup.py','exec'),scope)
    return scope['_failure_action']

class DiagnosticTests(TestCase):
    def test_hba_reports_observed_client_and_safe_rule(self):
        failure=failure_function({'host':'10.0.2.22','port':'5432','dbname':'depo','user':'depo_app','sslmode':'disable'})
        class LoginError(Exception):sqlstate='28000'
        result=failure(LoginError('no pg_hba.conf entry for host "10.0.2.16", user "depo_app", database "depo", no encryption password=never-print'))
        self.assertEqual(result['connection']['host'],'10.0.2.22')
        self.assertEqual(result['rejected_client_address'],'10.0.2.16')
        self.assertIn('10.0.2.16/32',result['hba_rule_example'])
        self.assertNotIn('never-print',json.dumps(result))

    def test_unvalidated_driver_text_is_not_exposed(self):
        result=failure_function({})(Exception('no pg_hba.conf entry for host "password=secret"'))
        self.assertNotIn('secret',json.dumps(result));self.assertNotIn('rejected_client_address',result)

    def test_ipv6_and_unusual_role_names(self):
        result=failure_function({'user':'role name','dbname':'depo'})(Exception('no pg_hba.conf entry for host "::1"'))
        self.assertEqual(result['rejected_client_address'],'::1');self.assertNotIn('hba_rule_example',result)

    def test_config_parser_allowlists_nonsecret_fields(self):
        import sys
        from types import SimpleNamespace
        source=ast.parse((ROOT/'backend/depo_platform/database_setup.py').read_text(encoding='utf-8'))
        node=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='_connection_context')
        scope={'os':os};exec(compile(ast.Module(body=[node],type_ignores=[]),'database_setup.py','exec'),scope)
        parser=SimpleNamespace(conninfo_to_dict=lambda _: {'host':'database','user':'app','password':'secret','sslkey':'private-key','options':'secret-option'})
        with patch.dict(os.environ,{'DEPO_DATABASE_URL':'configured'},clear=True),patch.dict(sys.modules,{'psycopg.conninfo':parser}):
            self.assertEqual(scope['_connection_context'](),{'host':'database','user':'app'})
        parser.conninfo_to_dict=lambda _: (_ for _ in ()).throw(ValueError('secret DSN'))
        with patch.dict(os.environ,{'DEPO_DATABASE_URL':'configured'},clear=True),patch.dict(sys.modules,{'psycopg.conninfo':parser}):
            self.assertEqual(scope['_connection_context'](),{})

if __name__=='__main__':main()
