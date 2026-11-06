import ast
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

class ManagedEnvironmentTests(unittest.TestCase):
    def test_managed_and_production_skip_legacy_files(self):
        tree = ast.parse(Path('backend/core/db_config.py').read_text(encoding='utf-8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_load_environment')
        calls = []
        scope = {'os': os, 'Path': lambda value: calls.append(value), '__file__': 'unused', 'load_dotenv': lambda *a, **k: calls.append(a)}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'config', 'exec'), scope)
        for env in [{'DEPO_ENV_INJECTED':'true'}, {'DEPO_ENV':'production'}, {'APP_ENV':'prod'}]:
            with patch.dict(os.environ, env, clear=True): scope['_load_environment']()
        self.assertEqual(calls, [])

if __name__ == '__main__': unittest.main()
