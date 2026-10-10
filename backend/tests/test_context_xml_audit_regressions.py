"""Focused regressions runnable without the service dependency stack."""
import ast
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from lxml import etree
from backend.Services.xsd_relational_report import build_xsd_relational_report


class AuditRegressions(unittest.TestCase):
    def test_numeric_nillable_accepts_valid_nil_instance(self):
        schema = '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:element name="Root"><xs:complexType><xs:sequence><xs:element name="value" type="xs:string" nillable="1"/></xs:sequence></xs:complexType></xs:element></xs:schema>'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.xsd'
            path.write_text(schema)
            validator = etree.XMLSchema(etree.parse(str(path)))
            validator.assertValid(etree.fromstring(b'<Root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><value xsi:nil="true"/></Root>'))
            column = build_xsd_relational_report(path)['tables'][0]['columns'][0]
            self.assertTrue(column['nullable'])
            self.assertTrue(column['nillable'])

    def test_requirement_filter_precedes_limit_and_retains_counts(self):
        tree = ast.parse(Path('backend/graph_service/context_router.py').read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'list_requirements')
        function.decorator_list = []
        publisher = SimpleNamespace(_session_rows=Mock(return_value=[{'relationship_count': 3}]))
        scope = {'publisher': publisher, 'Query': lambda **kw: kw['default']}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<context>', 'exec'), scope)
        result = scope['list_requirements'](' QIF ', 2)
        query = publisher._session_rows.call_args.args[0]
        self.assertLess(query.index('$source'), query.index('LIMIT'))
        self.assertIn('count(DISTINCT r)', query)
        self.assertEqual(publisher._session_rows.call_args.kwargs['source'], 'qif')
        self.assertEqual(result['requirements'][0]['relationship_count'], 3)
        self.assertEqual(publisher._session_rows.call_args.kwargs['limit'], 3)
        self.assertEqual(publisher._session_rows.call_args.kwargs['offset'], 0)

    def test_loaded_reader_refreshes_and_clears_removed_state(self):
        tree = ast.parse(Path('backend/ontology_service/business_context.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        function = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_load_persisted_state')
        scope = {'json': json, 'ContextGraph': lambda **kw: 'empty'}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<business-context>', 'exec'), scope)
        with tempfile.TemporaryDirectory() as directory:
            service = SimpleNamespace(_loaded=True, _STATE_KEY='context_graph', root=Path(directory),
                                      registry=SimpleNamespace(get=Mock(side_effect=[{'nodes': [1]}, {'nodes': [1, 2]}, None])),
                                      _load=Mock(), _persistence_error='previous failure')
            for _ in range(3):
                scope['_load_persisted_state'](service)
            self.assertEqual(service._load.call_args_list[1].args[0]['nodes'], [1, 2])
            self.assertEqual(service.graph, 'empty')
            self.assertEqual(service._persistence_error, '')


if __name__ == '__main__':
    unittest.main()
