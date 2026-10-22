"""Exercise real search/adapter methods without requiring a running graph."""
import ast
import re
from pathlib import Path
from typing import Any
import unittest
from backend.graph_service import query_repository as cypher


class ExistingSearchTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / 'graph_service/neo4j_publisher.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in ('overview', 'search', '_explorer_payload', '_read_edges', '_legacy_traversal', '_bounded_walk')]
        cls.body = methods
        from backend.depo_platform.graph_access import graph_projection_reader
        scope = {'__package__':'backend.graph_service','__name__':'backend.graph_service.neo4j_publisher','graph_projection_reader':graph_projection_reader,'re': re, 'Any': Any, 'cypher': cypher}
        exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), 'exec'), scope)
        self.publisher = scope['Neo4jPublisher']()
        self.calls = []
        self.canonical = []
        self.legacy = [{'id': 'neo4j-node-1', 'label': 'Product', 'type': 'OntologyClass', 'ontology_id': 'qif', 'score': 5}]
        self.publisher._session_rows = self.query

    def query(self, query, **params):
        self.calls.append((query, params))
        if query == cypher.ONTOLOGY_SEARCH_NODES: return self.canonical
        if query == cypher.LEGACY_SEARCH: return self.legacy
        if params.get('id') == 'record-1': return [{'id':'record-1'}]
        return []

    def test_legacy_only_database_returns_chat_evidence_and_parameterized_scope(self):
        result = self.publisher.search(query='product', ontology_id="customer's-id", ontology_prefix='qif')
        self.assertEqual(result['nodes'][0]['properties']['label'], 'Product')
        self.assertEqual(result['nodes'][0]['properties']['search_score'], 5)
        query, params = self.calls[1]
        self.assertEqual(params['ontology_id'], "customer's-id")
        self.assertEqual(params['ontology_prefix'], 'qif')
        self.assertNotIn("customer's-id", query)
        self.assertIn('NOT n:OntologyResource', query)

    def test_overview_includes_both_published_and_legacy_ontologies(self):
        published = {'id': 'published-1', 'label': 'Part', 'ontology_id': 'ap242'}
        self.publisher._session_rows = lambda query, **params: (
            self.legacy if query == cypher.LEGACY_OVERVIEW else
            [published] if query.startswith('MATCH (n:OntologyResource) RETURN') else [])
        result = self.publisher.overview(limit=10)
        self.assertEqual({n['elementId'] for n in result['nodes']}, {'published-1', 'neo4j-node-1'})
        self.assertEqual(len(self.publisher.overview(limit=1)['nodes']), 1)

    def test_mixed_results_obey_total_limit_and_ranking(self):
        self.canonical = [{'id': 'urn:product', 'label': 'Product annotation', 'type': 'resource', 'score': 1}]
        result = self.publisher.search(query='product', limit=1)
        self.assertEqual(len(result['nodes']), 1)
        self.assertEqual(result['nodes'][0]['elementId'], 'neo4j-node-1')
        self.assertTrue(result['view']['truncated'])
        edge_reads = [(q,p) for q,p in self.calls if 'ids' in p]
        self.assertEqual(len(edge_reads), 1)
        self.assertEqual(edge_reads[0][1]['ids'], ['neo4j-node-1'])

    def test_search_keeps_publication_barrier_across_all_queries(self):
        from contextlib import contextmanager
        from unittest.mock import patch
        active=[]
        @contextmanager
        def barrier():
            active.append(True)
            try:yield
            finally:active.pop()
        original=self.publisher._session_rows
        def rows(*args,**kwargs):
            self.assertEqual(active,[True])
            return original(*args,**kwargs)
        self.publisher._session_rows=rows
        with patch('backend.depo_platform.graph_access.projection_access',barrier):
            self.publisher.search(query='product')
        self.assertEqual(active,[])
        self.assertGreaterEqual(len(self.calls),3)

    def test_invalid_scope_is_rejected_before_any_graph_reads(self):
        with self.assertRaises(ValueError): self.publisher.search(query='product', ontology_prefix='x'*129)
        self.assertEqual(self.calls, [])

    def test_existing_traversal_excludes_internal_nodes_and_other_ontology_scopes(self):
        self.publisher._legacy_traversal(node_id='record-1', depth=2, limit=50)
        root_query, params = self.calls[0]
        self.assertIn('NOT n:OntologyResource', root_query)
        self.assertIn('n:OntologyClass', root_query)
        self.assertEqual(params['id'], 'record-1')
        query, params = self.calls[1]
        self.assertNotIn('nodes(path)', query)
        self.assertIn('neighbor:OntologyClass', query)
        self.assertIn('coalesce(root.ontology_id,root.source_ontology,root.prefix)', query)
        self.assertEqual(params['root'], 'record-1')
        self.assertEqual(params['frontier'], ['record-1'])
        self.assertEqual(params['limit'], 49)



if __name__ == '__main__': unittest.main()
