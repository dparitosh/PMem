import ast
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class EmbeddingImportBoundaryTests(unittest.TestCase):
    def test_cli_bootstrap_supports_both_working_directories(self):
        filename = Path('backend/Services/graph_embeddings.py').resolve()
        tree = ast.parse(filename.read_text(encoding='utf-8'))
        nodes = [node for node in tree.body
                 if (isinstance(node, ast.Assign) and any(
                     isinstance(target, ast.Name) and target.id == 'project_root'
                     for target in node.targets))
                 or (isinstance(node, ast.If) and 'project_root' in ast.unparse(node.test))
                 or (isinstance(node, ast.ImportFrom) and node.module == 'backend.core.llm')]
        self.assertEqual(len(nodes), 3)
        code = compile(ast.Module(body=nodes, type_ignores=[]), str(filename), 'exec')
        marker = object()
        module = SimpleNamespace(embeddings=marker, EMBEDDER_AVAILABLE=True)
        for initial_path in ([str(filename.parents[1])], [str(filename.parents[2])]):
            with self.subTest(path=initial_path):
                with patch.object(sys, 'path', initial_path.copy()), patch.dict(
                        sys.modules, {'backend.core.llm': module}):
                    scope = {'Path': Path, 'sys': sys, '__file__': str(filename)}
                    exec(code, scope)
                    exec(code, scope)
                    self.assertIs(scope['embeddings'], marker)
                    self.assertEqual(sys.path.count(str(filename.parents[2])), 1)
        imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertIn('backend.core.db_config', imports)
        self.assertNotIn('core.db_config', imports)
        self.assertNotIn('core.llm', imports)


if __name__ == '__main__':
    unittest.main()
