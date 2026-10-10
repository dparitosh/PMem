import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class MetadataReadTests(unittest.TestCase):
    def load(self):
        tree = ast.parse(Path('backend/routes/metadata_registry_routes.py').read_text(encoding='utf-8-sig'))
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in {'_metadata_registry_identity', 'list_metadata_assets', '_row_asset'}]
        for node in nodes:
            node.decorator_list = []
        scope = {'Request': object, 'Optional': __import__('typing').Optional,
                 'Dict': dict, 'Any': object, 'Query': lambda **kwargs: kwargs.get('default'),
                 'HTTPException': RuntimeError, 'graph': SimpleNamespace(query=Mock()),
                 'graph_read_identity': Mock(return_value='reader'), 'service_write_identity': Mock(return_value='writer')}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<metadata>', 'exec'), scope)
        return scope

    def test_reads_require_shared_identity_and_writes_keep_approval(self):
        scope = self.load()
        read = SimpleNamespace(method='GET')
        self.assertEqual(scope['_metadata_registry_identity'](read), 'reader')
        scope['graph_read_identity'].assert_called_once_with(read)
        self.assertEqual(scope['_metadata_registry_identity'](SimpleNamespace(method='POST')), 'writer')
        scope['graph_read_identity'].side_effect = PermissionError('rejected')
        with self.assertRaises(PermissionError):
            scope['_metadata_registry_identity'](read)

    def test_extra_row_detects_next_page_without_returning_it(self):
        scope = self.load()
        scope['graph'].query.return_value = [{'asset': {'asset_id': str(i)}} for i in range(3)]
        body = scope['list_metadata_assets'](limit=2, offset=4)
        self.assertEqual(body['count'], 2)
        self.assertTrue(body['has_more'])
        self.assertEqual(scope['graph'].query.call_args.kwargs['params']['offset'], 4)
        self.assertEqual(scope['graph'].query.call_args.kwargs['params']['limit'], 3)
        scope['graph'].query.return_value = []
        self.assertFalse(scope['list_metadata_assets'](limit=2, offset=6)['has_more'])
