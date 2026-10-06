import ast
import os
import unittest
from pathlib import Path
from unittest.mock import patch


class ServiceEnvironmentBoundaryTests(unittest.TestCase):
    def test_legacy_loaders_respect_deployment_boundary(self):
        files = ('backend/core/graph.py', 'backend/Services/graph_embeddings.py',
                 'backend/Services/neo4j_schema_cleaner.py',
                 'backend/Services/owl_xmi_engine.py', 'backend/Services/owl_plmxml_engine.py')
        for filename in files:
            tree = ast.parse(Path(filename).read_text(encoding='utf-8'))
            guard = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                         and 'DEPO_ENV_INJECTED' in ast.unparse(node.test))
            code = compile(ast.Module(body=[guard], type_ignores=[]), filename, 'exec')
            calls = []
            scope = {'os': os, 'Path': Path, '__file__': filename, 'env_path': 'unused',
                     'load_dotenv': lambda *args, **kwargs: calls.append(kwargs)}
            for environment in ({'DEPO_ENV_INJECTED': 'true'},
                                *({name: 'production'} for name in
                                  ('DEPO_ENV', 'ENVIRONMENT', 'APP_ENV', 'DEPLOYMENT_ENV'))):
                with self.subTest(file=filename, environment=environment):
                    with patch.dict(os.environ, environment, clear=True):
                        exec(code, scope)
                    self.assertEqual(calls, [])
            with patch.dict(os.environ, {}, clear=True):
                exec(code, scope)
            self.assertEqual(calls, [{'override': False}], filename)


if __name__ == '__main__':
    unittest.main()
