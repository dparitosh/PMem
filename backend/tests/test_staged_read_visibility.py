"""Exercise production read builders without requiring a running graph driver."""
import ast
import __future__
import re
import unittest
from pathlib import Path
from types import SimpleNamespace


def load_service(path, class_name, methods):
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    original = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    body = [node for node in original.body if isinstance(node, ast.Assign)
            or (isinstance(node, ast.FunctionDef) and node.name in methods)]
    cls = ast.ClassDef(name=class_name, bases=[], keywords=[], body=body, decorator_list=[])
    helpers = [node for node in tree.body if isinstance(node, ast.FunctionDef)
               and node.name in {'_first_text_value', '_node_payload', '_relationship_payload'}]
    scope = {'re': re}
    module = ast.fix_missing_locations(ast.Module(body=helpers + [cls], type_ignores=[]))
    exec(compile(module, '<production read builders>', 'exec', flags=__future__.annotations.compiler_flag), scope)
    return scope[class_name]


class StagedReadVisibilityTests(unittest.TestCase):
    def test_graph_serialization_cannot_return_staged_nodes_or_their_links(self):
        service = load_service('backend/Services/graph_view_service.py', 'GraphViewService', {'rows_to_graph'})
        result = service.rows_to_graph([{
            'n': {'elementId': 'public', 'labels': ['Requirement'], 'properties': {}},
            'm': {'elementId': 'staged', 'labels': ['StagedOntologyResource'], 'properties': {}},
            'r': {'elementId': 'edge', 'start': 'public', 'end': 'staged', 'type': 'RELATED'}}])
        self.assertEqual([node['elementId'] for node in result['nodes']], ['public'])
        self.assertEqual(result['relationships'], [])
        self.assertEqual(result['counts'], {'nodes': 1, 'relationships': 0})

    def test_publication_receipt_is_not_a_customer_graph_resource(self):
        service = load_service('backend/Services/graph_view_service.py', 'GraphViewService', {'rows_to_graph'})
        result = service.rows_to_graph([{'n': {'elementId': 'receipt',
            'labels': ['OntologyPublication'], 'properties': {'status': 'staging'}}}])
        self.assertEqual(result['nodes'], [])
        self.assertEqual(result['counts']['nodes'], 0)

    def test_graph_filter_removes_staged_nodes_and_incident_links(self):
        service = load_service('backend/Services/graph_view_service.py', 'GraphViewService',
            {'_filter_graph_nodes', '_is_metadata_like_node', '_is_schema_node'})
        graph = {'nodes': [
            {'elementId': 'public', 'labels': ['Requirement'], 'properties': {'semantic_role': 'entity'}},
            {'elementId': 'staged', 'labels': ['StagedOntologyResource'], 'properties': {'semantic_role': 'entity'}}],
            'relationships': [{'elementId': 'link', 'start': 'public', 'end': 'staged'}]}
        result = service._filter_graph_nodes(graph)
        self.assertEqual([node['elementId'] for node in result['nodes']], ['public'])
        self.assertEqual(result['relationships'], [])

    def test_ontology_counts_exclude_staging_before_aggregation(self):
        service = load_service('backend/Services/graph_view_service.py', 'GraphViewService', {'_ontology_total_counts'})
        calls = []
        service._run = staticmethod(lambda query, params: calls.append(query) or [])
        service._ontology_total_counts('demo', 'ontology')
        self.assertIn('AND NOT (n:StagedOntologyResource OR n:OntologyPublication)', calls[0])
        self.assertIn('AND NOT (a:StagedOntologyResource OR a:OntologyPublication)', calls[1])
        self.assertIn('AND NOT (b:StagedOntologyResource OR b:OntologyPublication)', calls[1])

    def test_oslc_page_and_total_apply_same_visibility_filter(self):
        service = load_service('backend/Services/oslc_service.py', 'OSLCService',
            {'_build_resource_query', '_build_count_query', '_resource_type_predicate',
             '_normalized_search_terms', '_build_order_by'})
        params = SimpleNamespace(where=[], search_terms=[], order_by=[], page_num=2, page_size=20)
        page, values = service._build_resource_query(params)
        count, _ = service._build_count_query(params)
        for query in (page, count):
            self.assertIn('NOT (n:DatasheetChunk OR n:GraphChunk OR n:StagedOntologyResource OR n:OntologyPublication)', query)
        self.assertLess(page.index('n:StagedOntologyResource'), page.index('SKIP'))
        self.assertEqual(values['skip'], 20)

    def test_oslc_lookup_filters_both_resource_and_link_target(self):
        service = load_service('backend/Services/oslc_service.py', 'OSLCService', {'get_resource'})
        calls = []
        graph = SimpleNamespace(_run=lambda query, params: calls.append(query) or [])
        service.get_resource.__func__.__globals__['GraphViewService'] = graph
        self.assertIsNone(service.get_resource('staged-id'))
        self.assertIn('n:StagedOntologyResource', calls[0])
        self.assertIn('m:StagedOntologyResource', calls[0])


if __name__ == '__main__':
    unittest.main()
