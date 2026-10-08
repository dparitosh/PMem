import copy
import unittest
from backend.agentic_service.bridge_jobs import BridgeJobs, BridgeConflict
from backend.mesh_store import InMemoryRegistry
from backend.tests.test_bridge_jobs import Graph


class Source:
    def __init__(self):
        self.revision = 'one'
        self.rows = [dict(import_id='import', import_row_key='row', source_term='part',
                         source_type='Entity', ontology_class_element_id='target', ontology_term='Part',
                         target_ontology_type='Class', validation_status='auto_approved', validation_errors=[],
                         validation_warnings=[], confidence=.98, rank=1, ambiguous=False, generic_match=False)]
    def snapshot(self, *args): return {'source': self.revision, 'ontology':'one'}
    def preview(self, *args): return self.snapshot(), copy.deepcopy(self.rows)


class AutomatedBridgeTests(unittest.TestCase):
    def setUp(self):
        self.source, self.graph = Source(), Graph()
        self.jobs = BridgeJobs(InMemoryRegistry(), self.source, self.graph)
    def preview(self): return self.jobs.preview('ontology', 'import', 'actor')['job_id']

    def test_only_validated_specific_mappings_are_published_with_policy_evidence(self):
        self.source.rows.append({**self.source.rows[0], 'import_row_key':'other', 'ambiguous':True})
        preview = self.preview()
        result = self.jobs.publish_automatic(preview, 'registered-actor')
        self.assertEqual(result['receipt']['applied_links'], 1)
        self.assertEqual(result['approval_policy']['held_count'], 1)
        self.assertEqual(result['approved_by'], 'registered-actor')
        self.assertEqual(self.jobs.publish_automatic(preview, 'registered-actor')['job_id'], result['job_id'])
        self.assertEqual(len(self.graph.calls), 1)

    def test_ambiguous_invalid_and_low_confidence_results_are_held_without_writes(self):
        base = self.source.rows[0]
        for change in ({'confidence':.5}, {'confidence':float('nan')}, {'validation_warnings':['review']},
                       {'ambiguous':True}, {'rank':2}, {'validation_status':'approved'}, {'generic_match':True},
                       {'validation_errors':['invalid']}):
            with self.subTest(change=change):
                self.source.rows = [{**base, **change}]
                result = self.jobs.publish_automatic(self.preview(), 'actor')
                self.assertEqual(result['status'], 'held')
                self.assertEqual(result['applied_links'], 0)
        self.assertEqual(self.graph.calls, [])

    def test_source_changes_and_duplicate_top_targets_block_automation(self):
        preview = self.preview()
        self.source.revision = 'two'
        with self.assertRaises(BridgeConflict): self.jobs.publish_automatic(preview, 'actor')
        self.source.rows.append({**self.source.rows[0], 'ontology_class_element_id':'different'})
        result = self.jobs.publish_automatic(self.preview(), 'actor')
        self.assertEqual(result['status'], 'held')
        self.assertEqual(self.graph.calls, [])
