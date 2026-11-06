import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

class ProductListPaginationTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / 'data_product_service/router.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'list_products')
        function.decorator_list = []
        self.records = {str(i): {'product_id': str(i), 'version': '1', 'published_at': '2026-01-01', 'api_key': 'never-expose'} for i in range(110)}
        class Rejected(Exception):
            def __init__(self, code, detail): self.status_code = code
        def page(*, limit, offset, order_field):
            rows = sorted(self.records.values(), key=lambda row: (row.get(order_field, ''), row['product_id']), reverse=True)
            return len(rows), rows[offset:offset+limit]
        scope = {'store': SimpleNamespace(page=page), 'HTTPException': Rejected}
        public = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_public_product')
        exec(compile(ast.Module(body=[public, function], type_ignores=[]), 'products', 'exec'), scope)
        self.list_products = scope['list_products']

    def test_pages_include_all_versions_without_exposing_keys(self):
        first = self.list_products(limit=100)
        second = self.list_products(limit=100, offset=first['next_offset'])
        rows = first['products'] + second['products']
        self.assertEqual(len(rows), 110)
        self.assertEqual(len({row['product_id'] for row in rows}), 110)
        self.assertEqual(first['total'], 110)
        self.assertIsNone(second['next_offset'])
        self.assertTrue(all('api_key' not in row for row in rows))

    def test_negative_offset_rejected_and_empty_store_complete(self):
        with self.assertRaises(Exception) as failure: self.list_products(offset=-1)
        self.assertEqual(failure.exception.status_code, 422)
        self.records.clear()
        result = self.list_products()
        self.assertEqual(result['total'], 0)
        self.assertIsNone(result['next_offset'])

if __name__ == '__main__': unittest.main()
