import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from backend.graph_service import query_repository


class GraphTraversalBoundsTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path('backend/graph_service/neo4j_publisher.py').read_text(encoding='utf-8'))
        publisher = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Neo4jPublisher')
        methods = [node for node in publisher.body if isinstance(node, ast.FunctionDef)
                   and node.name in {'traversal', '_legacy_traversal', '_bounded_walk', '_read_edges'}]
        scope = {'Any': Any, 'cypher': query_repository}
        exec(compile(ast.Module(body=methods, type_ignores=[]), 'traversal', 'exec'), scope)
        self.calls = []
        self.publisher = SimpleNamespace(_session_rows=self.rows, _explorer_payload=lambda **kwargs: kwargs)
        self.publisher._legacy_traversal = lambda **kwargs: scope['_legacy_traversal'](self.publisher, **kwargs)
        self.publisher._bounded_walk = lambda *args, **kwargs: scope['_bounded_walk'](self.publisher, *args, **kwargs)
        self.publisher._read_edges = lambda *args, **kwargs: scope['_read_edges'](self.publisher, *args, **kwargs)
        self.traversal = lambda **kwargs: scope['traversal'](self.publisher, **kwargs)

    def rows(self, query, **params):
        self.calls.append((query, params))
        if 'identity' in params or 'id' in params:
            return [{'id': 'root'}]
        if 'frontier' in params:
            current = params['frontier'][0]
            following = 'n1' if current == 'root' else 'n' + str(int(current[1:]) + 1)
            return [{'id': following}]
        return []

    def test_one_hop_query_does_not_enumerate_five_hop_paths(self):
        result = self.traversal(iri='root', depth=1, limit=1)
        self.assertFalse(any('frontier' in params for _, params in self.calls))
        self.assertFalse(any('*0..' in query for query, _ in self.calls))
        self.assertEqual(result['view']['depth'], 1)
        self.assertEqual([node['id'] for node in result['nodes']], ['root'])

    def test_depth_is_clamped_before_query_interpolation(self):
        result = self.traversal(iri='root', depth=100, limit=10000)
        self.assertEqual(result['view']['depth'], 5)
        self.assertEqual(result['view']['limit'], 1000)
        self.assertEqual(sum('frontier' in params for _, params in self.calls), 5)
        self.assertEqual(len(result['nodes']), 6)

    def test_legacy_root_is_retained_and_depth_bounded(self):
        result = self.publisher._legacy_traversal(node_id='root', depth=1, limit=1)
        self.assertEqual([node['id'] for node in result['nodes']], ['root'])
        self.assertFalse(any('frontier' in params for _, params in self.calls))

    def test_canonical_paths_stay_inside_ontology(self):
        self.traversal(iri='root', depth=2)
        expansions = [query for query, params in self.calls if 'frontier' in params]
        self.assertEqual(len(expansions), 2)
        self.assertTrue(all('neighbor.ontology_id = root.ontology_id' in query for query in expansions))
        self.assertFalse(any('nodes(path)' in query for query in expansions))


if __name__ == '__main__':
    unittest.main()
