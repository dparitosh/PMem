"""Memory identity, routing and lifecycle regressions without a live Neo4j."""
import ast
import __future__
import asyncio
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from backend.Services.agent_memory_service import AgentMemoryService as Memory, _stable_id, _legacy_id
from backend.depo_platform import agent_memory_config as config


class MemoryRegressions(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'AGENT_MEMORY_ENABLED': 'true',
            'AGENT_MEMORY_SCOPE': 'tcs:nexus', 'AGENT_MEMORY_QUERY_TIMEOUT': '5',
            'NEO4J_DATABASE': 'graph', 'AGENT_MEMORY_NEO4J_DATABASE': 'conversation'}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.health = patch.object(Memory, '_health', {})
        self.health.start(); self.addCleanup(self.health.stop)
        self.schema = patch.object(Memory, '_schema_attempted', False)
        self.schema.start(); self.addCleanup(self.schema.stop)

    def test_different_field_boundaries_have_different_ids(self):
        self.assertNotEqual(_stable_id('a|b', 'c'), _stable_id('a', 'b|c'))
        first = Memory._mapping_fact_row('ontology', 'import', {'source_term':'a|b', 'target_term':'c'}, '')
        second = Memory._mapping_fact_row('ontology', 'import', {'source_term':'a', 'target_term':'b|c'}, '')
        self.assertNotEqual(first['fact_id'], second['fact_id'])

    def test_long_scopes_are_rejected_instead_of_colliding(self):
        for suffix in ('a', 'b'):
            with patch.dict(os.environ, {'AGENT_MEMORY_SCOPE': 'x' * 256 + suffix}):
                with self.assertRaisesRegex(ValueError, 'AGENT_MEMORY_SCOPE'):
                    Memory.scope()

    def test_requested_settings_and_derived_scope_are_valid(self):
        self.assertEqual(Memory.scope(), 'tcs:nexus')
        self.assertEqual(config.query_timeout(), 5)
        with patch.dict(os.environ, {'AGENT_MEMORY_SCOPE':'', 'DEPO_TENANT_ID':'tcs', 'DEPO_PROJECT_ID':'nexus'}):
            self.assertEqual(Memory.scope(), 'tcs:nexus')
        with patch.dict(os.environ, {'AGENT_MEMORY_SCOPE':'', 'DEPO_TENANT_ID':'a:b', 'DEPO_PROJECT_ID':'c'}):
            with self.assertRaises(ValueError): Memory.scope()

    def test_invalid_timeout_and_boolean_do_not_silently_fall_back(self):
        for value in ('0', '31', '5cls', ''):
            with patch.dict(os.environ, {'AGENT_MEMORY_QUERY_TIMEOUT':value}):
                self.assertEqual(Memory.status()['invalid_setting'], 'AGENT_MEMORY_QUERY_TIMEOUT')
        with patch.dict(os.environ, {'AGENT_MEMORY_ENABLED':'yes'}):
            self.assertEqual(Memory.status()['status'], 'configuration_invalid')

    def test_legacy_chat_reads_are_scoped_and_session_bound(self):
        with patch.object(Memory, '_query', return_value=[{'text':'retained', 'role':'user'}]) as query:
            result = Memory.recent_context('session')
        self.assertEqual(result['messages'][0]['text'], 'retained')
        cypher, params = query.call_args.args
        self.assertEqual(params['legacy_key'], _legacy_id('tcs:nexus', 'session'))
        self.assertIn('scope: $scope', cypher)
        self.assertIn('coalesce(s.session_ref, s.session_id) = $session_id', cypher)

    def test_fact_reads_use_atomic_publication_database(self):
        with patch.object(Memory, '_query', return_value=[]) as query:
            Memory.semantic_bridge_facts('ontology-id')
        self.assertEqual(query.call_args.kwargs['database'], 'graph')
        self.assertEqual(query.call_args.args[1]['ontology_id'], 'ontology-id')

    def test_approved_fact_recording_uses_graph_database_and_valid_merge_order(self):
        with patch.object(Memory, 'ensure_schema', return_value={'ensured':True}) as schema, \
                patch.object(Memory, '_query', return_value=[]) as query:
            Memory.record_semantic_bridge_mappings(ontology_id='ontology', import_task_id='import',
                mappings=[{'source_term':'A','target_term':'B','selected_for_apply':True}])
        self.assertEqual(schema.call_args.kwargs['database'], 'graph')
        self.assertEqual(query.call_args.kwargs['database'], 'graph')
        cypher = query.call_args.args[0]
        self.assertLess(cypher.index('ON CREATE SET'), cypher.index("SET f.kind"))

    def test_failed_schema_does_not_write_unconstrained_memory(self):
        with patch.object(Memory, 'ensure_schema', return_value={'ensured':False}), patch.object(Memory, '_query') as query:
            Memory.record_chat_turn(session_id='session', user_message='hello', assistant_response='answer')
        query.assert_not_called()

    def test_new_sessions_work_with_retained_legacy_uniqueness_constraint(self):
        with patch.object(Memory, 'ensure_schema', return_value={'ensured':True}), patch.object(Memory, '_query', return_value=[]) as query:
            Memory.record_chat_turn(session_id='same-client-id', user_message='hello', assistant_response='answer')
        self.assertIn('s.session_id = $memory_key, s.session_ref = $session_id', query.call_args.args[0])

    def test_identical_turns_in_different_scopes_have_different_message_ids(self):
        ids = []
        with patch.object(Memory, 'ensure_schema', return_value={'ensured':True}), \
                patch.object(Memory, '_query', return_value=[]) as query, \
                patch('backend.Services.agent_memory_service._now_iso', return_value='fixed-time'):
            for scope in ('tcs:nexus', 'another:project'):
                with patch.dict(os.environ, {'AGENT_MEMORY_SCOPE':scope}):
                    Memory.record_chat_turn(session_id='same', user_message='hello', assistant_response='answer')
                    ids.append(query.call_args.args[1]['user_id'])
        self.assertNotEqual(*ids)

    def test_schema_is_non_destructive_and_changes_with_database(self):
        def result(cypher, params=None, **kwargs):
            return [{'name':name, 'type':'UNIQUENESS', 'entityType':'NODE', 'labelsOrTypes':[label], 'properties':[prop]}
                    for name, (label, prop) in Memory.SCHEMA_CONSTRAINTS.items()] if cypher.startswith('SHOW CONSTRAINTS') else []
        with patch.object(Memory, '_query', side_effect=result) as query:
            Memory.ensure_schema()
            self.assertEqual(query.call_count, 7)
            self.assertTrue(Memory.ensure_schema().get('cached'))
            with patch.dict(os.environ, {'AGENT_MEMORY_NEO4J_DATABASE':'other'}):
                Memory.ensure_schema()
            self.assertEqual(query.call_count, 15)
            self.assertTrue(all('DROP ' not in call.args[0] for call in query.call_args_list))

    def test_incompatible_constraint_is_not_claimed_ready(self):
        with patch.object(Memory, '_query', return_value=[]):
            self.assertFalse(Memory.ensure_schema()['ensured'])

    def test_connection_failure_is_reported_without_private_exception_text(self):
        driver = SimpleNamespace(session=Mock(side_effect=RuntimeError('private-password')))
        modules = {'backend.core.db_config': SimpleNamespace(get_driver=lambda:driver),
                   'neo4j': SimpleNamespace(Query=lambda query, **kw:query)}
        with patch.dict(sys.modules, modules), self.assertLogs('backend.Services.agent_memory_service', level='WARNING') as logs:
            self.assertEqual(Memory.status(probe=True)['status'], 'unavailable')
        self.assertNotIn('private-password', str(logs.output))

    def test_unprobed_memory_is_not_claimed_available(self):
        self.assertEqual(Memory.status()['status'], 'not_verified')
        self.assertEqual(Memory.status()['write_status'], 'not_verified')

    def test_status_distinguishes_read_connectivity_from_successful_writes(self):
        targets = []
        class Session:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def run(self, query, params):
                self_test.assertEqual(query.timeout, 5)
                return SimpleNamespace(data=lambda:[{'ok':1}])
        self_test = self
        driver = SimpleNamespace(session=lambda database:targets.append(database) or Session())
        modules = {'backend.core.db_config':SimpleNamespace(get_driver=lambda:driver),
                   'neo4j':SimpleNamespace(Query=lambda query, timeout:SimpleNamespace(text=query, timeout=timeout))}
        with patch.dict(sys.modules, modules):
            status = Memory.status(probe=True)
            self.assertEqual(status['status'], 'available')
            self.assertEqual(status['write_status'], 'not_verified')
            Memory._query('MERGE (n:AgentMemoryMessage {message_id:$id}) RETURN n', {'id':'test'})
            self.assertEqual(Memory.status()['write_status'], 'available')
        self.assertEqual(targets[:2], ['conversation', 'graph'])

    def test_mapping_reuse_uses_selected_ontology_id_even_with_shared_prefix(self):
        tree = ast.parse(Path('backend/Services/semantic_workflow_service.py').read_text(encoding='utf-8'))
        owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'SemanticWorkflowService')
        fn = next(node for node in owner.body if getattr(node, 'name', '') == '_build_link_candidates')
        fn.decorator_list = []
        facts = Mock(return_value=[])
        service = SimpleNamespace(_load_ontology_term_lookup=lambda prefix:{}, _collect_manifest_signals=lambda task:[],
                                  _resolve_ontology_id=lambda _:self.fail('Selected ontology identity was discarded'))
        scope = {'UnifiedDataImportService':SimpleNamespace(_load_ontology_class_lookup=lambda prefix:{}),
                 'AgentMemoryService':SimpleNamespace(semantic_bridge_facts=facts)}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<actual mapping builder>', 'exec',
                     flags=__future__.annotations.compiler_flag), scope)
        self.assertEqual(scope['_build_link_candidates'](service, [], 'shared-prefix', 'import', ontology_id='version-two'), [])
        facts.assert_called_once_with('version-two', limit=1500)

    def test_status_endpoint_authenticates_before_probing(self):
        tree = ast.parse(Path('backend/agentic_service/router.py').read_text(encoding='utf-8'))
        fn = next(node for node in tree.body if getattr(node, 'name', '') == 'memory_status')
        fn.decorator_list = []
        io = Mock()
        def deny(_): raise PermissionError('unauthorized')
        scope = {'Request': object, 'graph_read_identity':deny, '_agent_io':io, 'AgentMemoryService':Memory}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<actual memory status>', 'exec'), scope)
        with self.assertRaises(PermissionError): asyncio.run(scope['memory_status'](object()))
        io.assert_not_called()


if __name__ == '__main__': unittest.main()
