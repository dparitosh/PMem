"""Exercise aggregate metrics without installing Neo4j or RDF dependencies."""
import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import unittest
from backend.graph_service import query_repository

ROOT = Path(__file__).resolve().parents[2]


class GraphProfileMetricsTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((ROOT / 'backend/graph_service/neo4j_publisher.py').read_text(encoding='utf-8'))
        publisher = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Neo4jPublisher')
        method = next(node for node in publisher.body if isinstance(node, ast.FunctionDef) and node.name == 'metrics')
        scope = {'Any': Any, 'cypher': query_repository, 'RDF': SimpleNamespace(type='rdf:type'),
            'RDFS': SimpleNamespace(Class='rdfs:Class'), 'OWL': SimpleNamespace(Class='owl:Class', ObjectProperty='owl:ObjectProperty',
                DatatypeProperty='owl:DatatypeProperty', AnnotationProperty='owl:AnnotationProperty', NamedIndividual='owl:NamedIndividual')}
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'metrics', 'exec'), scope)
        self.metrics = scope['metrics']
        self.calls = []
        self.rows = [{'resources': 10001, 'classes': 700, 'relationships': 20001, 'ontology_breakdown': []}]
        self.legacy_rows = [{'resources': 125, 'classes': 75, 'object_properties': 30, 'data_properties': 20}]
        self.publisher = SimpleNamespace(_session_rows=self.query)

    def query(self, query, **params):
        self.calls.append((query, params))
        return self.legacy_rows if query == query_repository.LEGACY_METRICS else self.rows

    def test_complete_aggregate_keeps_existing_records_separate_and_parameterizes_identity(self):
        result = self.metrics(self.publisher, ontology_id="customer's-version")
        query, params = self.calls[0]
        self.assertEqual(len(self.calls), 2)
        self.assertNotIn("customer's-version", query)
        self.assertEqual(params['ontology_id'], "customer's-version")
        self.assertEqual(result['resources'], 10001)
        self.assertFalse(result['scope']['sampled'])
        self.assertFalse(result['scope']['inferred'])
        self.assertIn('count(r) AS relationships', query)
        self.assertIn('a.ontology_id = b.ontology_id', query)
        self.assertIn('owl:NamedIndividual', params.values())
        self.assertEqual(result['existing_ontology']['resources'], 125)

    def test_zero_projection_still_reports_existing_records_with_explicit_prefix_scope(self):
        self.rows[0]['resources'] = 0
        result = self.metrics(self.publisher, ontology_id='uuid-123', ontology_prefix='qif')
        self.assertEqual(result['resources'], 0)
        self.assertEqual(result['existing_ontology']['classes'], 75)
        query, params = self.calls[1]
        self.assertEqual(params, {'ontology_id': 'uuid-123', 'ontology_prefix': 'qif'})
        self.assertIn('NOT n:OntologyResource', query)
        self.assertIn('n.source_ontology = $ontology_prefix', query)

    def test_existing_record_query_failure_is_not_silently_reported_as_zero(self):
        self.legacy_rows = []
        with self.assertRaises(RuntimeError): self.metrics(self.publisher)

    def test_breakdown_limit_does_not_truncate_aggregate_counts(self):
        self.rows[0]['ontology_breakdown'] = [{'ontology': str(i), 'node_count': 1} for i in range(201)]
        result = self.metrics(self.publisher)
        self.assertEqual(len(result['ontology_breakdown']), 200)
        self.assertTrue(result['breakdown_truncated'])
        self.assertEqual(result['resources'], 10001)

    def test_invalid_identity_and_missing_aggregate_fail_instead_of_zero_metrics(self):
        with self.assertRaises(ValueError): self.metrics(self.publisher, ontology_id='x' * 129)
        self.rows = []
        with self.assertRaises(RuntimeError): self.metrics(self.publisher)

    def test_metrics_route_requires_read_authorization(self):
        tree = ast.parse((ROOT / 'backend/graph_service/router.py').read_text(encoding='utf-8'))
        route = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'metrics')
        self.assertIn('Depends(graph_read_identity)', ast.unparse(route.decorator_list[0]))


if __name__ == '__main__': unittest.main()
