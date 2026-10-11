import unittest
from unittest.mock import patch
from types import SimpleNamespace
from backend.graph_service.ontology_reports import ontology_report


class OntologyReportTests(unittest.TestCase):
    def test_unknown_registry_scope_does_not_query_graph(self):
        service = SimpleNamespace(_ontology_domain_scope=lambda value: None)
        graph = SimpleNamespace(_run=lambda *args: self.fail('Unregistered scope queried'))
        with patch.dict('sys.modules', {
            'backend.Services.oslc_service': SimpleNamespace(OSLCService=service),
            'backend.Services.graph_view_service': SimpleNamespace(GraphViewService=graph),
        }), self.assertRaises(ValueError):
            ontology_report('unknown')

    def test_scope_is_bound_and_all_categories_come_from_aggregation(self):
        calls = []
        service = SimpleNamespace(_ontology_domain_scope=lambda value: {'ontology_id': "qif'", 'prefix': 'qif'},
                                  _resource_type_predicate=lambda kind: 'n:Mapped')
        def run(query, params):
            calls.append((query, params))
            return [{'resources': 12, 'unmapped': 7, 'outgoing_links': 9,
                     **{f'c{i}': i for i in range(6)}}]
        with patch.dict('sys.modules', {
            'backend.Services.oslc_service': SimpleNamespace(OSLCService=service),
            'backend.Services.graph_view_service': SimpleNamespace(GraphViewService=SimpleNamespace(_run=run)),
        }):
            report = ontology_report("qif'")
        self.assertNotIn("qif'", calls[0][0])
        self.assertIn("$ontology_prefix <> ''", calls[0][0])
        self.assertEqual(calls[0][1]['ontology_id'], "qif'")
        self.assertEqual([row['count'] for row in report['categories']], list(range(6)))
        self.assertEqual(report['unmapped'], 7)
        self.assertFalse(report['sampled'])


if __name__ == '__main__':
    unittest.main()
