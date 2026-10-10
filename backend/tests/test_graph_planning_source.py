"""Isolated source-selection contracts; no live graph or RDF runtime required."""
import ast
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / 'agentic_service' / 'ontology_orchestrator.py'


def functions():
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in {'graph_planning_summary', 'bridge_plan'}]
    namespace = {'Any': object, '_instance_metadata': lambda *args: {}, 'plan_bridge': lambda metadata, ontology_summary: ontology_summary}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace


class GraphPlanningSource(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.mapping_terms.return_value = [{'kind': 'Class', 'iri': 'urn:Part', 'name': 'Part', 'element_id': 'node-1'}]
        module = types.ModuleType('backend.depo_platform.graph_data_client')
        module.graph_data_client = self.client
        self.modules = patch.dict(sys.modules, {'backend.depo_platform.graph_data_client': module})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.code = functions()

    def test_selected_id_uses_graph_without_artifact(self):
        result = self.code['bridge_plan']({'ontology_id': 'assembly'})
        self.client.mapping_terms.assert_called_once_with('assembly')
        self.assertEqual(result['engine'], 'neo4j')
        self.assertEqual(result['term_index'][0]['graph_element_id'], 'node-1')

    def test_unavailable_graph_does_not_fall_back(self):
        self.client.mapping_terms.side_effect = RuntimeError('unavailable')
        with self.assertRaisesRegex(RuntimeError, 'unavailable'):
            self.code['bridge_plan']({'ontology_id': 'assembly'})

    def test_empty_graph_and_stale_digest_rejected(self):
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.code['bridge_plan']({'ontology_id': 'assembly', 'graph_digest': 'stale'})
        self.client.mapping_terms.return_value = []
        with self.assertRaisesRegex(ValueError, 'publish'):
            self.code['bridge_plan']({'ontology_id': 'assembly'})

    def test_graph_digest_is_order_independent(self):
        terms = self.client.mapping_terms.return_value
        terms.append({'kind': 'Class', 'iri': 'urn:Other', 'name': 'Other', 'element_id': 'node-2'})
        first = self.code['graph_planning_summary']('assembly')['graph_digest']
        self.client.mapping_terms.return_value = list(reversed(terms))
        self.assertEqual(first, self.code['graph_planning_summary']('assembly')['graph_digest'])
