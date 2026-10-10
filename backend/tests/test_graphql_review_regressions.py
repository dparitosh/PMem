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


class GraphResponseSafetyTests(unittest.TestCase):
    def test_scoped_identity_and_orphan_edges(self):
        tree = ast.parse((ROOT / 'graph_service/neo4j_publisher.py').read_text(encoding='utf-8'))
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_explorer_payload')
        method.decorator_list = []
        scope = {'Any': Any}
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'publisher', 'exec'), scope)
        result = scope['_explorer_payload'](nodes=[{'id':'urn:Part','graph_id':'first'}, {'id':'urn:Part','graph_id':'second'}],
            edges=[{'source':'urn:Part','target':'urn:Part','graph_source':'first','graph_target':'second'}, {'source':'missing','target':'urn:Part'}], view={})
        self.assertEqual([n['elementId'] for n in result['nodes']], ['first','second'])
        self.assertEqual(result['nodes'][0]['properties']['iri'], 'urn:Part')
        self.assertEqual(len(result['relationships']), 1)
        self.assertEqual(result['relationships'][0]['start'], 'first')

    def test_json_scalar_dates_and_finite_values(self):
        from datetime import datetime
        scope = {'Any': Any, 'GraphQLError': ValueError}
        serialize = load('graph_service/graphql_schema.py', '_serialize_json', scope)
        self.assertEqual(serialize({'at': datetime(2026,1,1), 'values': (1,2)}), {'at':'2026-01-01T00:00:00','values':[1,2]})
        with self.assertRaisesRegex(ValueError, 'Non-finite'): serialize(float('nan'))
        with self.assertRaisesRegex(ValueError, 'Unsupported'): serialize(object())

    def test_variable_budget_uses_utf8_bytes_and_rejects_nan(self):
        scope = {'Any': Any, 'HTTPException': Rejected, 'MAX_VARIABLE_BYTES':128000, 'MAX_VARIABLE_ITEMS':500}
        validate = load('graph_service/graphql_router.py', '_validate_variables', scope)
        with self.assertRaises(Rejected): validate({'values':['漢'*9000]*5})
        with self.assertRaises(Rejected): validate({'value':float('nan')})
        self.assertEqual(validate({'safe':[1,2]}), {'safe':[1,2]})

    def test_walk_stops_at_node_budget_and_does_not_enumerate_paths(self):
        from backend.graph_service import query_repository
        scope = {'cypher':query_repository}
        tree = ast.parse((ROOT / 'graph_service/neo4j_publisher.py').read_text(encoding='utf-8'))
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_bounded_walk')
        exec(compile(ast.Module(body=[method], type_ignores=[]), 'publisher', 'exec'), scope)
        calls = []
        def rows(query, **params):
            calls.append((query,params))
            return [{'id':'root'}] if 'frontier' not in params else [{'id':'child'}]
        owner = NS(_session_rows=rows)
        result = scope['_bounded_walk'](owner,'root',5,2)
        self.assertEqual(len(result),2)
        self.assertEqual(len(calls),2)
        self.assertNotIn('*',calls[-1][0])
        self.assertEqual(calls[-1][1]['limit'],1)


    def test_read_driver_reused_and_closed(self):
        import sys, threading, types
        from unittest.mock import Mock, patch
        owner = NS(auth_mode='none', database='ontology', _read_driver=None, _driver_lock=threading.Lock())
        from unittest.mock import MagicMock
        driver = MagicMock()
        owner._driver = Mock(return_value=driver)
        scope = {'Any':Any,'Query':lambda query,timeout:query}
        tree = ast.parse((ROOT / 'graph_service/neo4j_publisher.py').read_text(encoding='utf-8'))
        for name in ['_session_rows','close']:
            method = next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name)
            exec(compile(ast.Module(body=[method],type_ignores=[]),'publisher','exec'),scope)
        module = types.ModuleType('backend.depo_platform.network')
        module.bounded_timeout_seconds = lambda *a,**k:30
        with patch.dict(sys.modules, {'backend.depo_platform.network':module}):
            scope['_session_rows'](owner,'RETURN 1')
            scope['_session_rows'](owner,'RETURN 2')
        owner._driver.assert_called_once()
        scope['close'](owner)
        driver.close.assert_called_once()
        self.assertIsNone(owner._read_driver)


    def test_projection_keeps_rdf_iris_and_limits_edges_to_selected_nodes(self):
        from backend.graph_service import query_repository
        scope = {'Any':Any,'cypher':query_repository}
        tree = ast.parse((ROOT / 'graph_service/neo4j_publisher.py').read_text(encoding='utf-8'))
        method = next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='projection')
        exec(compile(ast.Module(body=[method],type_ignores=[]),'publisher','exec'),scope)
        calls = []
        def rows(query,**params):
            calls.append(params)
            return [{'id':'urn:Part','graph_id':'node-1'}] if len(calls)==1 else []
        result = scope['projection'](NS(_session_rows=rows),ontology_id='one',limit=1)
        self.assertEqual(result['nodes'][0]['id'],'urn:Part')
        self.assertEqual(calls[1]['ids'],['urn:Part'])

    def test_ambiguous_input_is_not_reported_as_service_outage(self):
        class GraphQLError(Exception): pass
        error = NS(original_error=ValueError('private details'),message='private details',extensions={})
        scope = {'Any':Any,'schema':object(),'graphql_sync':lambda *a,**k:NS(data=None,errors=[error]),
                 'GraphQLError':GraphQLError,'logging':logging,'uuid4':uuid4,'__name__':__name__}
        result = load('graph_service/graphql_schema.py','execute',scope)('{ traversal }')
        self.assertEqual(result['errors'][0]['extensions']['code'],'BAD_USER_INPUT')
        self.assertNotIn('private details',str(result))


if __name__ == '__main__': unittest.main()
