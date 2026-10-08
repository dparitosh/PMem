import copy
import ast
import json
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from backend.tests.test_merge_entity_changes import MergeEntityChangesTests


class MergeAutomationTests(unittest.TestCase):
    def service(self, mappings=None):
        service = MergeEntityChangesTests().service()
        values = {}
        service.lock = threading.RLock()
        service._load = lambda: copy.deepcopy(values)
        service._save = lambda records, key=None: values.update(copy.deepcopy(records))
        service.catalog.register = Mock(return_value={'ontology_id':'merged-draft', 'provenance':{'preview_id':'saved'}})
        service.intelligence = SimpleNamespace(create_merge_version=Mock(return_value={'version_id':'version'}))
        preview = service.preview({'source_ontology_ids':['a','b'], 'entity_mappings':mappings or []})
        return service, values, preview

    def test_union_automation_retains_policy_and_creates_one_draft_on_retry(self):
        service, values, preview = self.service()
        decision = service.evaluate_policy(preview['preview_id'])
        self.assertEqual(decision['status'], 'ready')
        result = service.apply_automatic(preview['preview_id'], 'registered-actor')
        self.assertEqual(result['status'], 'merged')
        self.assertEqual(result['approval_policy']['policy'], 'conflict-free-union-v1')
        self.assertEqual(values[preview['preview_id']]['approved_by'], 'registered-actor')
        provenance = service.catalog.register.call_args.kwargs['extra_metadata']['provenance']
        self.assertEqual(provenance['approval_policy'], decision)
        service.apply_automatic(preview['preview_id'], 'registered-actor')
        service.catalog.register.assert_called_once()
        service.intelligence.create_merge_version.assert_called_once()

    def test_entity_consolidation_is_held_without_writes(self):
        service, _, preview = self.service([{'source_iri':'urn:ex:Part','target_iri':'urn:ex:Component'}])
        result = service.apply_automatic(preview['preview_id'], 'registered-actor')
        self.assertEqual(result['status'], 'held')
        self.assertIn('entity_consolidation_requires_review', result['reasons'])
        service.catalog.register.assert_not_called()

    def test_receipt_verifies_saved_artifact_without_repeating_merge(self):
        service, values, preview = self.service()
        result = service.apply_automatic(preview['preview_id'],'actor')
        provenance = service.catalog.register.call_args.kwargs['extra_metadata']['provenance']
        service.catalog.read_artifact = Mock(return_value=({'provenance':provenance},values[preview['preview_id']]['turtle'].encode()))
        self.assertEqual(service.receipt(preview['preview_id']),values[preview['preview_id']]['applied_result'])
        service.catalog.register.assert_called_once()
        service.catalog.read_artifact.return_value = ({'provenance':provenance},b'changed RDF')
        with self.assertRaisesRegex(ValueError,'does not match'): service.receipt(preview['preview_id'])

    def test_policy_rechecks_actual_rdf_instead_of_trusting_preview_flag(self):
        service, values, preview = self.service()
        record = values[preview['preview_id']]
        record['turtle'] += '\n<urn:ex:Part> a <http://www.w3.org/2002/07/owl#Nothing> .'
        record['publish_recommended'] = True
        record['conflicts'] = []
        result = service.apply_automatic(preview['preview_id'], 'registered-actor')
        self.assertEqual(result['status'], 'held')
        service.catalog.register.assert_not_called()

    def test_workflow_wires_saved_preview_to_steward_and_governor(self):
        catalog = json.loads(Path('backend/agentic_service/catalog.json').read_text())
        workflow = next(item for item in catalog['workflows'] if item['id']=='ontology-union-automation')
        self.assertEqual([item['agent_id'] for item in workflow['steps']], ['ontology-governor','ontology-steward','ontology-governor'])
        for step in workflow['steps'][1:]:
            self.assertEqual(step['input_bindings']['preview_id'], '$steps.1.result.preview_id')
        tools = {item['id']:item for item in catalog['tools']}
        self.assertTrue(tools['ontology.merge.apply_automatic']['mutates'])
        self.assertFalse(tools['ontology.merge.evaluate']['mutates'])

    def test_policy_read_and_automatic_write_have_explicit_authorization(self):
        tree = ast.parse(Path('backend/ontology_service/router.py').read_text())
        policy = next(node for node in tree.body if getattr(node, 'name', '') == 'merge_policy')
        self.assertTrue(any(isinstance(node, ast.Name) and node.id == 'graph_read_identity' for node in ast.walk(policy)))
        apply = next(node for node in tree.body if getattr(node, 'name', '') == 'automatic_merge')
        self.assertTrue(any(isinstance(node, ast.Name) and node.id == 'approval_identity' for node in ast.walk(apply)))
        self.assertTrue(any(isinstance(node, ast.Constant) and node.value == 'ONTOLOGY_APPROVAL_TOKEN' for node in ast.walk(apply)))
