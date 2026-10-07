import ast
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from backend.graph_service import bridge_publication


class DependencyAuditTests(unittest.TestCase):
    def test_graph_lookup_resolves_properties_and_bounds_query(self):
        tree = ast.parse(Path('backend/Services/semantic_workflow_service.py').read_text(encoding='utf-8'))
        owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'SemanticWorkflowService')
        method = next(node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == '_load_graph_term_lookup')
        namespace = {'Dict': dict, 'List': list, 'Any': object, '_tokenize': lambda value: value.split()}
        wrapper = ast.ClassDef(name='Lookup', bases=[], keywords=[], body=[method], decorator_list=[])
        exec(compile(ast.fix_missing_locations(ast.Module(body=[wrapper], type_ignores=[])), '<lookup>', 'exec'), namespace)
        cls = namespace['Lookup']
        cls._normalized_key = staticmethod(lambda value: value.lower())
        cls._is_generic_term = staticmethod(lambda value: False)
        from backend.depo_platform.graph_data_client import graph_data_client
        with patch.object(graph_data_client, 'mapping_terms', return_value=[{'element_id': 'graph-property', 'name': 'Mass', 'iri': 'urn:parts#mass', 'kind': 'DatatypeProperty'}]) as read:
            lookup = cls._load_graph_term_lookup('parts')
            self.assertEqual(lookup['mass'][0]['target_ontology_type'], 'DatatypeProperty')
            self.assertTrue(lookup['mass'][0]['graph_linkable'])
            read.assert_called_once_with('parts')

    def test_graph_data_repository_bounds_scope_and_results(self):
        from backend.graph_service import query_repository
        tree = ast.parse(Path('backend/graph_service/neo4j_publisher.py').read_text(encoding='utf-8'))
        owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Neo4jPublisher')
        method = next(node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == 'mapping_terms')
        namespace = {'Any': object, 'cypher': query_repository}
        wrapper = ast.ClassDef(name='Publisher', bases=[], keywords=[], body=[method], decorator_list=[])
        exec(compile(ast.fix_missing_locations(ast.Module(body=[wrapper], type_ignores=[])), '<publisher>', 'exec'), namespace)
        publisher = namespace['Publisher']()
        publisher._session_rows = MagicMock(return_value=[])
        publisher.mapping_terms('parts')
        query = publisher._session_rows.call_args.args[0]
        self.assertIn('LIMIT 10001', query)
        self.assertEqual(publisher._session_rows.call_args.kwargs['scopes'], ['parts'])
        publisher._session_rows.return_value = [{}] * 10001
        with self.assertRaisesRegex(ValueError, 'exceeds 10000'):
            publisher.mapping_terms('parts')

    def test_peer_data_read_uses_configured_service_and_private_credential(self):
        from backend.depo_platform.graph_data_client import GraphDataClient
        response = MagicMock()
        response.iter_bytes.return_value = [b'{"terms":[{"kind":"Class","element_id":"graph-id","name":"Part"}]}']
        client = MagicMock()
        client.stream.return_value.__enter__.return_value = response
        http = types.ModuleType('httpx')
        http.Client = MagicMock(); http.Client.return_value.__enter__.return_value = client
        for base in ('http://graph:8013', 'http://graph:8013/api/v1'):
            with patch.dict(os.environ, {'GRAPH_SERVICE_URL': base}), patch.dict(sys.modules, {'httpx': http}), patch('backend.depo_platform.graph_data_client.service_bearer_headers', return_value={'Authorization': 'Bearer server-test'}) as auth:
                result = GraphDataClient().mapping_terms('parts')
                self.assertEqual(result[0]['element_id'], 'graph-id')
                self.assertEqual(client.stream.call_args.args, ('GET', 'http://graph:8013/api/v1/graph/mapping-terms'))
                self.assertEqual(auth.call_args.args[0], 'GRAPH_PUBLICATION_TOKEN')
                self.assertFalse(http.Client.call_args.kwargs['trust_env'])
                response.raise_for_status.assert_called()
        response.iter_bytes.return_value = [b'{"terms":null}']
        with patch.dict(sys.modules, {'httpx': http}), patch('backend.depo_platform.graph_data_client.service_bearer_headers', return_value={}):
            with self.assertRaisesRegex(RuntimeError, 'invalid mapping terms'):
                GraphDataClient().mapping_terms('parts')

    def test_malformed_publication_row_is_rejected_before_database_access(self):
        command = {'rows': ['malformed']}
        command['request_digest'] = bridge_publication.digest(command)
        with patch.object(bridge_publication, 'session') as session:
            with self.assertRaisesRegex(ValueError, 'Invalid approved mapping'):
                bridge_publication.publish(command)
            session.assert_not_called()

    def test_publication_memory_uses_same_scope_and_fact_contract_as_reads(self):
        tx = MagicMock()
        state = MagicMock(); state.single.return_value = {'receipt': None}
        counts = MagicMock(); counts.data.return_value = [{'candidate_id': 'candidate', 'sources': 1, 'targets': 1}]
        writes = MagicMock(); writes.single.return_value = {'applied': 1}
        tx.run.side_effect = [state, counts, writes, MagicMock(), MagicMock()]
        command = {'publication_id': 'publication', 'preview_id': 'preview', 'request_digest': 'digest',
            'ontology_id': 'parts', 'approved_by': 'reviewer', 'rows': [{'candidate_id': 'candidate',
                'import_id': 'import', 'source_term': 'part', 'ontology_term': 'Part', 'target_ontology_type': 'Class'}]}
        with patch.dict(os.environ, {'AGENT_MEMORY_ENABLED': 'true', 'AGENT_MEMORY_SCOPE': 'customer:project'}):
            bridge_publication._publish_transaction(tx, command)
        query = tx.run.call_args.args[0]
        fact = tx.run.call_args.kwargs['rows'][0]
        self.assertIn('f.scope=row.scope', query)
        self.assertEqual(fact['scope'], 'customer:project')
        self.assertEqual(fact['target'], 'Part')
        self.assertEqual(fact['import_task_id'], 'import')
