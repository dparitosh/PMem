"""Run actual validation/error functions with dependency boundaries stubbed."""
import ast
import logging
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any
from uuid import uuid4
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(path, name, scope):
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    function.decorator_list = []
    exec(compile(ast.Module(body=[function], type_ignores=[]), path, 'exec'), scope)
    return scope[name]


def node(kind, **attrs):
    return type(kind, (), attrs)()


class Rejected(Exception):
    def __init__(self, status, detail): self.status_code = status


class GraphqlReviewTests(unittest.TestCase):
    def validator(self, selections, fragments=()):
        operation = node('OperationDefinitionNode', selection_set=NS(selections=selections))
        scope = {'Any': Any, 'parse': lambda _: NS(definitions=[operation, *fragments]),
                 'GraphQLError': Rejected, 'HTTPException': Rejected,
                 'MAX_FIELDS': 25, 'MAX_DEPTH': 4, 'MAX_COST': 100,
                 'FIELD_COSTS': {'contextualResult': 35, 'traversal': 30}}
        return load('graph_service/graphql_router.py', '_validate_complexity', scope)

    def test_fragments_do_not_add_field_depth(self):
        leaf = node('FieldNode', name=NS(value='label'), arguments=[], selection_set=None)
        fragment = node('FragmentDefinitionNode', name=NS(value='Leaf'), selection_set=NS(selections=[leaf]))
        selection = node('FragmentSpreadNode', name=NS(value='Leaf'))
        for name in ['properties', 'nodes', 'contextualResult']:
            selection = node('FieldNode', name=NS(value=name), arguments=[], selection_set=NS(selections=[selection]))
        self.validator([selection], [fragment])('query')

    def test_variable_expansion_cost_rejected_before_execution(self):
        argument = NS(name=NS(value='expandNeighbors'), value=node('VariableNode', name=NS(value='expand')))
        field = node('FieldNode', name=NS(value='contextualResult'), arguments=[argument], selection_set=None)
        with self.assertRaises(Rejected) as error:
            self.validator([field, field])('query', {'expand': True})
        self.assertEqual(error.exception.status_code, 422)

    def test_internal_resolver_errors_are_sanitized(self):
        class GraphQLError(Exception): pass
        error = NS(original_error=RuntimeError('secret database URI'), message='secret database URI', extensions={})
        scope = {'Any': Any, 'schema': object(), 'graphql_sync': lambda *a, **k: NS(data=None, errors=[error]),
                 'GraphQLError': GraphQLError, 'logging': logging, 'uuid4': uuid4, '__name__': __name__}
        execute = load('graph_service/graphql_schema.py', 'execute', scope)
        with self.assertLogs(__name__, level='ERROR'):
            result = execute('{ health }')
        self.assertNotIn('secret', str(result))
        self.assertEqual(result['errors'][0]['extensions']['code'], 'SERVICE_UNAVAILABLE')

    def test_oversized_identifiers_rejected(self):
        scope = {'GraphQLError': ValueError}
        validate = load('graph_service/graphql_schema.py', '_bounded_text', scope)
        with self.assertRaises(ValueError): validate('x' * 257, 'importId', 256)

    def test_import_scope_disables_schema_fallback(self):
        scope = {'Dict': dict, 'Any': Any, '_graph_node_limit': lambda: 1000}
        tree = ast.parse((ROOT / 'Services/graph_view_service.py').read_text(encoding='utf-8'))
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'get_contextual_subgraph')
        method.decorator_list = []
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'graph_view', 'exec'), scope)
        class View:
            SCHEMA_NODE_LABELS = INSTANCE_NODE_LABELS = INSTANCE_SEMANTIC_ROLES = RELATIONSHIP_NODE_LABELS = []
            _resolve_ontology_prefix = staticmethod(lambda v: v)
            _normalize_search_term = staticmethod(lambda v: v)
            _run = staticmethod(lambda *a: [])
            rows_to_graph = staticmethod(lambda rows: {'nodes': [], 'relationships': []})
            _filter_graph_nodes = staticmethod(lambda graph, **k: graph)
            @staticmethod
            def _schema_contextual_search_fallback(**kwargs): raise AssertionError('Import scope escaped')
        result = scope['get_contextual_subgraph'](View, search='part', ontology_prefix='plm', import_id='import-1')
        self.assertEqual(result['nodes'], [])
        self.assertEqual(result['view']['import_id'], 'import-1')


if __name__ == '__main__': unittest.main()
