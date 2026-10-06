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
                   and node.name in {'traversal', '_legacy_traversal'}]
        scope = {'Any': Any, 'cypher': query_repository}
        exec(compile(ast.Module(body=methods, type_ignores=[]), 'traversal', 'exec'), scope)
        self.calls = []
        self.publisher = SimpleNamespace(_session_rows=self.rows, _explorer_payload=lambda **kwargs: kwargs)
        self.publisher._legacy_traversal = lambda **kwargs: scope['_legacy_traversal'](self.publisher, **kwargs)
        self.traversal = lambda **kwargs: scope['traversal'](self.publisher, **kwargs)

    def rows(self, query, **params):
        self.calls.append((query, params))
        return [{'id': 'root'}] if len(self.calls) == 1 else []

    def test_one_hop_query_does_not_enumerate_five_hop_paths(self):
        result = self.traversal(iri='root', depth=1, limit=1)
        self.assertIn('*0..1', self.calls[0][0])
        self.assertNotIn('*0..5', self.calls[0][0])
        self.assertEqual(result['view']['depth'], 1)
        self.assertEqual(self.calls[0][1]['limit'], 1)
        self.assertIn('[root] +', self.calls[0][0])

    def test_depth_is_clamped_before_query_interpolation(self):
        self.traversal(iri='root', depth=100, limit=10000)
        self.assertIn('*0..5', self.calls[0][0])
        self.assertEqual(self.calls[0][1]['limit'], 1000)

    def test_legacy_root_is_retained_and_depth_bounded(self):
        self.publisher._legacy_traversal(node_id='root', depth=1, limit=1)
        self.assertIn('*0..1', self.calls[0][0])
        self.assertIn('[root] +', self.calls[0][0])

    def test_canonical_paths_stay_inside_ontology(self):
        self.traversal(iri='root', depth=2)
        self.assertIn('all(n IN nodes(path)', self.calls[0][0])
        self.assertIn('n.ontology_id = root.ontology_id', self.calls[0][0])


if __name__ == '__main__':
    unittest.main()
