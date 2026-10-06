"""Managed LLM startup must not fill missing values from stale dotenv files."""
import ast
import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch


class LlmEnvironmentBoundaryTests(TestCase):
    def load_defaults(self, values):
        path = Path(__file__).resolve().parents[1] / 'core/llm.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        nodes = [node for node in tree.body if
            (isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in {'env_path', 'managed_environment', 'production_environment'} for target in node.targets))
            or (isinstance(node, ast.If) and 'load_dotenv' in ast.unparse(node))]
        loader = Mock()
        with patch.dict(os.environ, values, clear=True):
            exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'),
                 {'os': os, 'Path': Path, '__file__': str(path), 'load_dotenv': loader})
        return loader

    def test_managed_and_production_do_not_read_legacy_files(self):
        self.load_defaults({'DEPO_ENV_INJECTED': 'true'}).assert_not_called()
        for variable in ('DEPO_ENV', 'ENVIRONMENT', 'APP_ENV', 'DEPLOYMENT_ENV'):
            self.load_defaults({variable: 'production'}).assert_not_called()

    def test_unmanaged_development_preserves_injected_values(self):
        loader = self.load_defaults({})
        loader.assert_called_once()
        self.assertFalse(loader.call_args.kwargs['override'])
