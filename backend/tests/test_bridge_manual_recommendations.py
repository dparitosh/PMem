import sys
import types
import unittest
from unittest.mock import patch
from backend.agentic_service.bridge_jobs import BridgeSource, BridgeJobs
from backend.mesh_store import InMemoryRegistry


class ManualRecommendationTests(unittest.TestCase):
    def test_manual_mapping_resolves_server_owned_rows_and_targets(self):
        source = BridgeSource()
        term = {'class_name': 'Part', 'element_id': 'graph-part', 'target_ontology_type': 'Class', 'graph_linkable': True}
        row = {'id': 'row-part', 'name': 'part'}
        service = types.SimpleNamespace(_load_ontology_term_lookup=lambda _: {},
            _candidate_display_value=lambda r: r['name'], _classify_source_row=lambda _: 'Entity',
            _validate_candidate_pair=lambda *args: {'is_valid': True, 'status': 'needs_review', 'errors': []})
        imports = types.SimpleNamespace(_load_ontology_class_lookup=lambda _: {'part': [term]})
        module = types.ModuleType('backend.Services.unified_data_import')
        module.UnifiedDataImportService = imports
        mapping = {'source_term': 'part', 'source_type': 'Entity', 'target_term': 'Part', 'target_ontology_type': 'Class',
                   'ontology_class_element_id': 'untrusted', 'import_row_key': 'untrusted'}
        with patch.object(source, '_read', return_value=(service, {'parsed_rows': [row]}, 'parts', {})), patch.dict(sys.modules, {'backend.Services.unified_data_import': module}):
            result = source.manual_candidates('ontology', 'import', [mapping])
            self.assertEqual(result[0]['ontology_class_element_id'], 'graph-part')
            self.assertEqual(result[0]['import_row_key'], 'row-part')
            mapping['target_term'] = 'unknown'
            with self.assertRaisesRegex(ValueError, 'missing or ambiguous'):
                source.manual_candidates('ontology', 'import', [mapping])

    def test_saved_recommendations_are_unselected_and_bound_to_preview(self):
        candidate = {'import_id':'import', 'import_row_key':'row', 'ontology_class_element_id':'target', 'target_ontology_type':'Class', 'selected_for_apply':True}
        source = types.SimpleNamespace(preview=lambda *args: ({'version':1}, []),
            manual_candidates=lambda *args: [candidate], snapshot=lambda *args: {'version':1})
        jobs = BridgeJobs(InMemoryRegistry(), source, object())
        result = jobs.preview('ontology', 'import', 'reviewer', [{'source_term':'part'}])
        self.assertEqual(result['recommendation_summary']['eligible'], 1)
        self.assertTrue(result['recommendation_summary']['requires_review'])
        self.assertNotIn('selected_for_apply', result['candidates'][0])
        self.assertEqual(jobs.get(result['job_id']), result)


if __name__ == '__main__': unittest.main()
