import ast
import json
from pathlib import Path
import sys
from types import ModuleType
from unittest import TestCase, main
from unittest.mock import Mock, patch


class CredentialCheckTests(TestCase):
    def test_checks_only_allowlisted_profiles_without_writes(self):
        path = Path(__file__).resolve().parents[1] / 'depo_platform/service_runtime.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        factory = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'create_service_app')
        node = next(n for n in factory.body if isinstance(n, ast.FunctionDef) and n.name == 'credential_check')
        node.decorator_list = []
        class Rejected(Exception):
            def __init__(self, status, detail): self.status = status
        fastapi = ModuleType('fastapi'); fastapi.HTTPException = Rejected
        auth = ModuleType('backend.depo_platform.authorization')
        auth.service_write_identity = Mock(return_value='actor')
        scope = {'Request': object, '__name__': 'backend.depo_platform.service_runtime', '__package__': 'backend.depo_platform'}
        with patch.dict(sys.modules, {'fastapi': fastapi, 'backend.depo_platform.authorization': auth}):
            exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), scope)
            request = object()
            profiles_path = path.parents[2] / 'frontend/src/services/credentialProfiles.js'
            profiles = json.loads(profiles_path.read_text(encoding='utf-8').split('=', 1)[1].strip().rstrip(';'))
            self.assertEqual(len(profiles), 17)
            for profile in set(profiles) - {'GRAPH_READ_TOKEN', 'ADMIN_API_KEY'}:
                self.assertEqual(scope['credential_check'](request, profile)['status'], 'authorized')
                auth.service_write_identity.assert_called_with(request, token_env=profile, default_actor='credential-check')
            auth.service_write_identity.reset_mock()
            with self.assertRaises(Rejected): scope['credential_check'](request, 'DATABASE_PASSWORD')
            auth.service_write_identity.assert_not_called()
            auth.service_write_identity.side_effect = Rejected(403, 'invalid key')
            with self.assertRaises(Rejected): scope['credential_check'](request, 'INGESTION_WRITE_TOKEN')


if __name__ == '__main__': main()
