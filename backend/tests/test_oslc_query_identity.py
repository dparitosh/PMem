import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from backend.Services.oslc_query_service import OSLCQueryService as Query, OSLCQueryValidationError
from backend.oslc_service.identity import resource_uri


class OslcCorrectness(unittest.TestCase):
    def test_relative_pagination_keeps_query_endpoint_and_blocks_other_hosts(self):
        from urllib.parse import urlsplit, urljoin, unquote, parse_qsl
        tree = ast.parse(Path('backend/oslc_service/client.py').read_text())
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        fn = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'next_page')
        namespace = dict(urlsplit=urlsplit, urljoin=urljoin, unquote=unquote, parse_qsl=parse_qsl, Any=object)
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<actual pagination>', 'exec'), namespace)
        client = SimpleNamespace(base_url='https://provider.test/api', _request=lambda path, params: (path, params))
        result = namespace['next_page'](client, '?oslc.pageNum=2', 'https://provider.test/api/oslc/query/resources')
        self.assertEqual(result, ('oslc/query/resources', {'oslc.pageNum': '2'}))
        with self.assertRaises(ValueError):
            namespace['next_page'](client, 'https://other.test/api/oslc/query/resources', 'https://provider.test/api/oslc/query/resources')

    def test_openapi_exposes_query_parameters_and_representations(self):
        tree = ast.parse(Path('backend/routes/oslc_routes.py').read_text())
        fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'query_resources')
        aliases = {keyword.value.value for default in fn.args.defaults if isinstance(default, ast.Call)
                   for keyword in default.keywords if keyword.arg == 'alias'}
        self.assertEqual(aliases, {'oslc.where', 'oslc.select', 'oslc.orderBy', 'oslc.searchTerms', 'oslc.paging', 'oslc.pageSize', 'oslc.pageNum'})
        self.assertIn('responses=REPRESENTATION_RESPONSES', ast.unparse(fn.decorator_list[0]))

    def test_boolean_filters_keep_types(self):
        values = Query.parse({'oslc.where': 'enabled=true and revoked=false'}).where
        self.assertIs(values[0].value, True)
        self.assertIs(values[1].value, False)

    def test_invalid_boolean_expression_rejected(self):
        for expression in ['count=1 and ', 'count=1 and and count=2', ' and count=2']:
            with self.subTest(expression=expression), self.assertRaises(OSLCQueryValidationError):
                Query.parse({'oslc.where': expression})

    def test_signed_order(self):
        self.assertEqual(Query.parse({'oslc.orderBy': '+dcterms:title,-id'}).order_by,
                         [('dcterms:title', 'asc'), ('id', 'desc')])

    def test_rdf_identity_survives_node_recreation(self):
        properties = {'uri': 'urn:customer:part:1'}
        self.assertEqual(resource_uri('http://oslc', properties, 'old'),
                         resource_uri('http://oslc', properties, 'new'))
        self.assertEqual(resource_uri('http://oslc', {}, 'old'), 'http://oslc/oslc/resources/old')

    def test_shape_grant_checked_before_metadata_resolution(self):
        tree = ast.parse(Path('backend/routes/oslc_routes.py').read_text())
        fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'get_resource_shape')
        fn.decorator_list = []
        class Denied(Exception):
            pass
        calls = []
        def authorize(*args):
            raise Denied()
        service = SimpleNamespace(is_enabled=lambda: True, DEFAULT_RESOURCE_TYPE='resources', DOMAIN_SHAPES={},
                                  resource_shape=lambda value: calls.append(value))
        namespace = {'Request': object, 'OSLCService': service, 'graph_read_identity': lambda request: 'actor',
                     'HTTPException': Denied}
        with patch.dict('sys.modules', {'backend.oslc_service.access': SimpleNamespace(authorize=authorize)}):
            exec(compile(ast.Module(body=[fn], type_ignores=[]), '<actual OSLC route>', 'exec'), namespace)
            with self.assertRaises(Denied):
                namespace['get_resource_shape']('private', object())
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
