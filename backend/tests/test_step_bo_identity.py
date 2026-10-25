import tempfile
import unittest
from pathlib import Path
from backend.Services.step_parser import _iter_part28_entities

class StepBoIdentityTests(unittest.TestCase):
    def test_validation_and_publication_share_the_same_batch_bound(self):
        from backend.ceim.limits import MAX_BATCH_RECORDS
        from backend.ceim_service.router import normalize_batch, MAX_BATCH_RECORDS as publication_limit
        from backend.data_pipeline_service.runner import SparkJobRunner
        from fastapi import HTTPException
        self.assertEqual(publication_limit, SparkJobRunner.max_records)
        self.assertEqual(publication_limit, MAX_BATCH_RECORDS)
        with self.assertRaises(HTTPException) as raised:
            normalize_batch({'standard':'ap242','entities':[{}] * (MAX_BATCH_RECORDS + 1)})
        self.assertEqual(raised.exception.status_code,422)

    def parse(self, text):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.stpx'
            path.write_text(text,encoding='utf-8')
            return list(_iter_part28_entities(path))

    def test_business_ids_can_repeat_but_uid_refs_resolve(self):
        rows=self.parse('<Uos xmlns="http://standards.iso.org/iso/ts/10303/-3001/-ed-1/tech/xml-schema/bo_model"><Id id="part"><Identifier uid="part-id" id="part"/></Id><Part uid="part"/><Link uidRef="part"/></Uos>')
        part=next(row for row in rows if row.entity_type=='PART')
        identifier=next(row for row in rows if row.entity_type=='IDENTIFIER')
        link=next(row for row in rows if row.entity_type=='LINK')
        self.assertEqual(identifier.source_identifier,'part-id')
        self.assertEqual(identifier.source_identifier_kind,'uid')
        self.assertEqual(link.ref_ids,[part.step_id])
        self.assertFalse(link.unresolved_refs)

    def test_duplicate_bo_uid_still_rejected(self):
        with self.assertRaisesRegex(ValueError,'Duplicate Part-28'):
            self.parse('<Uos xmlns="http://standards.iso.org/iso/ts/10303/-3001/-ed-1/tech/xml-schema/bo_model"><Part uid="x"/><Part uid="x"/></Uos>')

    def test_generic_part28_ids_remain_global(self):
        with self.assertRaisesRegex(ValueError,'Duplicate Part-28'):
            self.parse('<uos xmlns="urn:iso:10303:28"><Part id="x"/><Part id="x"/></uos>')


    def test_measure_does_not_collect_other_dimensions_from_context(self):
        from backend.Services.step_parser import StepP21Entity, _measure_unit
        rows={1:StepP21Entity(1,'SHAPE_DIMENSION_REPRESENTATION',"'',(#2),#4",[2,4]),
              2:StepP21Entity(2,'LENGTH_MEASURE_WITH_UNIT','LENGTH_MEASURE(5.),#3',[3]),
              3:StepP21Entity(3,'SI_UNIT','.MILLI.,.METRE.',[]),
              4:StepP21Entity(4,'GLOBAL_UNIT_ASSIGNED_CONTEXT','(#3,#5)',[3,5]),
              5:StepP21Entity(5,'SI_UNIT','$,.RADIAN.',[])}
        self.assertEqual(_measure_unit(rows[1],rows),'mm')

    def test_ap242_repeated_labels_are_not_identity_conflicts(self):
        from backend.ceim.resolution import analyze_entities
        def entity(id,value):
            return {'id':id,'ceim_type':'GeometryBody','properties':{'external_id':'affected area','value':value},'provenance':{'source_standard':'ap242','source_id':id}}
        self.assertFalse(analyze_entities([entity('1',10),entity('2',20)])['blocking'])
        self.assertTrue(analyze_entities([entity('1',10),entity('1',20)])['blocking'])


    def test_ap242_bo_identification_requires_typed_container(self):
        from backend.parsers.ap242_identity import is_ap242
        ns='http://standards.iso.org/iso/ts/10303/-3001/-ed-1/tech/xml-schema/bo_model'
        self.assertFalse(is_ap242('bo_model',ns,b'<Uos><!-- AP242DataContainer --></Uos>'))
        self.assertTrue(is_ap242('bo_model',ns,b'<Uos xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><DataContainer xsi:type="n:AP242DataContainer"/></Uos>'))

    def test_document_identity_is_stable_and_source_references_survive(self):
        from backend.ceim.ap242_adapter import ap242_to_ceim_batch
        content=b"ISO-10303-21;HEADER;FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF'));ENDSEC;DATA;#1=PRODUCT('p','Motor','',());#2=PRODUCT_DEFINITION_FORMATION('v','',#1);ENDSEC;END-ISO-10303-21;"
        first=ap242_to_ceim_batch(content,filename='a.stp')
        again=ap242_to_ceim_batch(content,filename='renamed.stp')
        second=ap242_to_ceim_batch(content.replace(b'Motor',b'Rotor'),filename='b.stp')
        self.assertEqual([e['id'] for e in first['entities']],[e['id'] for e in again['entities']])
        self.assertFalse({e['id'] for e in first['entities']} & {e['id'] for e in second['entities']})
        ids={e['id'] for e in first['entities']}
        self.assertTrue(first['relationships'])
        self.assertTrue(all(e['properties'].get('external_id') for e in first['entities']))
        self.assertTrue(all(r['source_id'] in ids and r['target_id'] in ids for r in first['relationships']))
        self.assertTrue(any(r['relationship']=='TRACE_TO' for r in first['relationships']))


    def test_bounded_semantic_validation_runs_without_spark(self):
        from unittest.mock import patch
        from backend.data_pipeline_service.runner import SparkJobRunner
        runner=SparkJobRunner()
        from backend.ceim.contract import contract
        entity=contract.normalize_entity(standard='ap242',record={'source_type':'product_definition','source_id':'test','attributes':{'name':'Motor'}})
        with patch.object(runner,'_enabled',return_value=False), patch.object(runner,'_spark_session',side_effect=AssertionError('Spark must not start')), patch.object(runner,'_retain_json_artifact',return_value='test-artifact'):
            result=runner.normalize_ceim_batch({'standard':'ap242','ceim_version':contract.version,'representation':'normalized-ceim-v1','entities':[entity],'relationships':[]},correlation_id='test',validate=True)
        self.assertEqual(result['status'],'completed')
        self.assertTrue(result['validation']['conforms'])
        self.assertEqual(result['series'],[{'ceim_type':'Product','count':1}])
        self.assertEqual(result['publication'],'not_attempted; CEIM graph publication requires a separate approved request')


    def test_publication_scopes_isolate_documents_and_keep_retries_pinned(self):
        from backend.data_pipeline_service.publication_scope import publication_scope
        def batch(digest):return {'standard':'ap242','entities':[{'provenance':{'source_document_sha256':digest}}]}
        record={'run_id':'first','source_system':'CAD'}
        a=publication_scope({},record,batch('a'))
        self.assertEqual(a,publication_scope({},dict(record,run_id='retry'),batch('a')))
        self.assertNotEqual(a,publication_scope({},record,batch('b')))
        self.assertNotEqual(a,publication_scope({'source_system':'other'},record,batch('a')))
        pinned=dict(record,output_manifest={'publication_intent':{'ontology_id':'ceim-ap242'}})
        self.assertEqual(publication_scope({},pinned,batch('a')),'ceim-ap242')
        self.assertEqual(publication_scope({'ontology_id':'chosen'},record,batch('a')),'chosen')


    def test_canonical_business_query_uses_exact_types_and_preserves_scope(self):
        from backend.graph_service.business_types import include_canonical_business_types
        query='WHERE any(label IN labels(seed) WHERE label IN $instance_node_labels) AND seed.ontology_id=$scope'
        expanded=include_canonical_business_types(query)
        self.assertIn('seed:OntologyResource',expanded)
        self.assertIn('https://depo.example.org/ceim/0.1/Product',expanded)
        self.assertIn('seed.ontology_id=$scope',expanded)
        self.assertEqual(include_canonical_business_types('RETURN 1'),'RETURN 1')


    def test_canonical_instances_survive_python_graph_filtering(self):
        from backend.Services.graph_view_service import GraphViewService
        node={'elementId':'part','labels':['OntologyResource'],'properties':{'label':'id21','rdf_types':['https://depo.example.org/ceim/0.1/Product']}}
        self.assertTrue(GraphViewService._is_individual_node(node))
        self.assertFalse(GraphViewService._is_metadata_like_node(node))
        graph=GraphViewService._filter_graph_nodes({'nodes':[node],'relationships':[]},only_individual_nodes=True)
        self.assertEqual(len(graph['nodes']),1)
        self.assertFalse(GraphViewService._is_individual_node({'labels':['OntologyResource'],'properties':{'rdf_types':['http://www.w3.org/2002/07/owl#Class']}}))

if __name__=='__main__':unittest.main()
