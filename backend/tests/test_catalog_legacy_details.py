"""Exercise the catalog detail handler without optional service dependencies."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


class CatalogLegacyDetailsTests(unittest.TestCase):
    def test_legacy_timestamps_and_latest_pointer(self):
        path = Path(__file__).resolve().parents[1] / 'data_catalog_service/router.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'product')
        function.decorator_list = []
        records = {
            'demo:1.0.0': {'version': '1.0.0'},
            'demo:2.0.0': {'version': '2.0.0', 'updated_at': None},
            'demo:3.0.0': {'version': '3.0.0', 'updated_at': '2026-10-06'},
            'demo:latest': {'latest_version': '3.0.0'},
            'other:1.0.0': {'version': '1.0.0'},
        }
        scope = {'store': SimpleNamespace(all=lambda: records, get=records.get), 'HTTPException': RuntimeError}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), scope)
        result = scope['product']('demo')
        self.assertEqual(result['latest_version'], '3.0.0')
        self.assertEqual([row['version'] for row in result['versions']], ['3.0.0', '2.0.0', '1.0.0'])


if __name__ == '__main__':
    unittest.main()
