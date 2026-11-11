"""Behavioral checks for mapping governance, batching and receipt recovery."""
import ast
import copy
import unittest
from pathlib import Path
from types import SimpleNamespace, ModuleType
from unittest.mock import patch
from typing import Any, Dict, List

from backend.agentic_service.bridge_jobs import BridgeJobs, BridgeConflict
from backend.mesh_store import InMemoryRegistry
from backend.tests.test_bridge_jobs import Source, Graph


def definition(path, name, scope):
    tree = ast.parse(Path(path).read_text(encoding='utf-8-sig'))
    node = next(node for node in ast.walk(tree) if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name == name)
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, 'exec'), scope)
    return scope[name]


class MappingValidationTests(unittest.TestCase):
    def validate(self, *args):
        method = definition('backend/ontology_service/domain/reasoning.py', 'validate_mapping', dict(Any=Any, Dict=Dict, List=List))
        return method(*args)

    def test_relationships_require_exact_domain_and_range_evidence(self):
        constraints = {'domain':['urn:Aircraft'], 'range':['urn:Engine']}
        for row in ({}, {'domain':'urn:Person','range':'urn:Organization'}):
            self.assertEqual(self.validate('Relationship','ObjectProperty',constraints,row)['status'], 'warning')
        self.assertEqual(self.validate('Relationship','ObjectProperty',constraints,{'domain':'urn:Aircraft','range':'urn:Engine'})['status'], 'valid')

    def test_datatype_missing_mismatch_and_bad_lexical_value_cannot_auto_pass(self):
        target = {'range':['http://www.w3.org/2001/XMLSchema#integer']}
        self.assertEqual(self.validate('Attribute','DatatypeProperty',target,{'value':'abc'})['status'],'warning')
        self.assertEqual(self.validate('Attribute','DatatypeProperty',target,{'datatype':'xsd:string','value':'abc'})['status'],'warning')
        self.assertEqual(self.validate('Attribute','DatatypeProperty',target,{'datatype':'xsd:integer','value':'abc'})['status'],'invalid')
        self.assertEqual(self.validate('Attribute','DatatypeProperty',target,{'datatype':'xsd:integer','value':12})['status'],'valid')

    def test_datatype_substring_does_not_establish_compatibility(self):
        result = self.validate('Attribute','DatatypeProperty',{'range':['xsd:integer']},{'datatype':'int'})
        self.assertEqual(result['status'],'warning')


class PublicationTests(unittest.TestCase):
    def test_ingestion_partitions_before_sending_candidates_to_agentic_service(self):
        from backend.ingestion_service.bridge_source import LocalBridgeSource
        source = LocalBridgeSource()
        base = Source().preview()[1][0]
        candidates = [{**base, 'import_row_key':str(i)} for i in range(2001)]
        with patch.object(source,'preview',return_value=({'source':'s','ontology':'o'},candidates)):
            snapshot, page, partition = source.preview_partition('ontology','import')
        self.assertEqual(len(page),2000)
        self.assertEqual(partition,{'offset':0,'total_candidates':2001,'next_offset':2000})

    def test_agentic_uses_partition_contract_without_refetching_all_candidates(self):
        source = SimpleNamespace(preview_partition=lambda *args: ({'source':'s','ontology':'o'},Source().preview()[1],{'offset':2000,'total_candidates':2001,'next_offset':None}))
        result = BridgeJobs(InMemoryRegistry(),source,Graph()).preview('ontology','import','reader',candidate_offset=2000)
        self.assertEqual(len(result['candidates']),1)
        self.assertEqual(result['partition']['offset'],2000)

    def test_memory_retains_exact_target_and_generic_status(self):
        from backend.Services.agent_memory_service import AgentMemoryService
        with patch.object(AgentMemoryService,'scope',return_value='tenant:project'):
            first = AgentMemoryService._mapping_fact_row('ontology','import',{'source_term':'Part','ontology_term':'Item','target_ontology_iri':'urn:a','generic_match':True},'job')
            second = AgentMemoryService._mapping_fact_row('ontology','import',{'source_term':'Part','ontology_term':'Item','target_ontology_iri':'urn:b'},'job')
        self.assertEqual(first['target_iri'],'urn:a')
        self.assertTrue(first['generic_match'])
        self.assertNotEqual(first['fact_id'],second['fact_id'])

    def test_large_candidate_set_is_partitioned_without_loss_or_overlap(self):
        source = Source()
        base = source.preview()[1][0]
        source.preview = lambda *args: (source.snapshot(), [{**base,'import_row_key':str(i)} for i in range(4001)])
        jobs = BridgeJobs(InMemoryRegistry(),source,Graph())
        batches = [jobs.preview('ontology','import','reader',candidate_offset=offset) for offset in (0,2000,4000)]
        self.assertEqual([len(batch['candidates']) for batch in batches],[2000,2000,1])
        self.assertEqual(len({row['candidate_id'] for batch in batches for row in batch['candidates']}),4001)
        self.assertEqual([batch['partition']['next_offset'] for batch in batches],[2000,4000,None])

    @patch('backend.depo_platform.decision_policy.assess_decisions', return_value={'blocking': False, 'status': 'not_configured', 'checks': []})
    def test_wrong_actor_and_wrong_link_count_receipts_are_rejected(self, policy):
        for changes in ({'applied_links':0},{'applied_links':True},{'approved_by':'another-actor'}):
            graph = Graph(); graph.lose_response = True
            jobs = BridgeJobs(InMemoryRegistry(),Source(),graph)
            preview = jobs.preview('ontology','import','reader')
            ids = [preview['candidates'][0]['candidate_id']]
            with self.assertRaises(TimeoutError): jobs.publish(preview['job_id'],ids,'approver')
            graph.receipts[preview['publication_job_id']].update(changes)
            with self.assertRaises(BridgeConflict): jobs.publish(preview['job_id'],ids,'approver')
            self.assertNotEqual(jobs.get(preview['publication_job_id'])['status'],'published')
            self.assertEqual(len(graph.calls),1)

    def test_lifecycle_change_invalidates_snapshot_and_retired_target_is_rejected(self):
        metadata = {'prefix':'same','lifecycle_status':'approved'}
        service = SimpleNamespace(_resolve_ontology_id=lambda value:value,_ontology_metadata=lambda _:metadata,
            _load_import_task=lambda _: {'parsed_rows':[]},_load_ontology_term_lookup=lambda _:{'part':[]},_read_ontology_file=lambda _:'rdf')
        source_module = ModuleType('backend.Services.semantic_workflow_service'); source_module.SemanticWorkflowService = service
        importer = ModuleType('backend.Services.unified_data_import'); importer.UnifiedDataImportService = SimpleNamespace(_load_ontology_class_lookup=lambda _:{})
        cls = definition('backend/ingestion_service/bridge_source.py','LocalBridgeSource',dict(digest=lambda value:str(value),canonical_lookup=lambda value:value,BridgeConflict=BridgeConflict))
        with patch.dict('sys.modules',{'backend.Services.semantic_workflow_service':source_module,'backend.Services.unified_data_import':importer}):
            source = cls(); before = source.snapshot('ontology','import')
            metadata['status'] = 'changed'
            self.assertNotEqual(before,source.snapshot('ontology','import'))
            metadata['lifecycle_status'] = 'retired'
            with self.assertRaises(BridgeConflict): source.snapshot('ontology','import')


if __name__ == '__main__': unittest.main()
