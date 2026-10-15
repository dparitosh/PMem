"""Audit regressions for schema identity and recovery after an ODS commit."""
import ast
from pathlib import Path
import json
import os
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

from backend.artifact_store import ArtifactStore
from backend.mesh_store import InMemoryRegistry
from backend.data_pipeline_service import analytics_evidence, run_records
from backend.data_pipeline_service.xml_analytics import business_view_plan, prepare_xml_load
from backend.tests import test_xml_analytics_materialization as fixtures


class AnalyticsAuditFixes(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.environment=patch.dict(os.environ,{'ARTIFACT_STORAGE':self.directory.name});self.environment.start();self.addCleanup(self.environment.stop)
        self.registry=InMemoryRegistry('data_job_runs')
        self.persistence=patch.object(run_records,'store',self.registry);self.persistence.start();self.addCleanup(self.persistence.stop)
        self.inputs={'schema_artifact_id':'sha256:xsd','xml_artifact_id':'sha256:xml'}
        self.definition={'job_id':'xml-load','job_type':'xml-analytics-materialize','version':'1.0.0','quality_profile':'schema-analytics-v1','input_contract':'xsd-xml-artifacts-v1','name':'Load','owner':'operator'}
        self.receipt={'status':'completed','schema':'ods_test','schema_digest':'schema-digest','xml_digest':'xml-digest','analytics_readiness':'structural-data-loaded; business-metrics-not-defined','counts':{'entities':3}}

    def record(self):
        return run_records.start(self.definition,self.inputs,correlation_id='correlation')

    def pending(self):
        record=self.record()
        with patch.object(analytics_evidence,'ArtifactStore',side_effect=OSError('disk unavailable')):
            result=analytics_evidence.build_analytics_evidence(self.inputs,self.receipt)
        return run_records.complete(record,result)

    def test_default_xsd_namespace_uses_target_namespace_for_root(self):
        schema='<schema xmlns="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:test"><element name="Root" type="string"/></schema>'
        prepared=fixtures.XMLAnalyticsMaterialization().prepare(b'<Root xmlns="urn:test">valid</Root>',schema)
        self.assertEqual(prepared['model']['roots'][0]['source_qname'],'{urn:test}Root')
        self.assertEqual(prepared['rows'][0][1],['valid'])

    def test_fact_and_dimension_receipts_describe_actual_output_columns(self):
        model={'tables':[{'entity_id':'Part','sql_name':'parts','columns':[{'name':'code','sql_name':'part_code','sql_type':'TEXT'}]}]}
        views=business_view_plan(model,'ods',[
            {'name':'Parts','kind':'dimension','entity_id':'Part','grain':'business-key','keys':['part_code'],'history_policy':'immutable'},
            {'name':'Counts','kind':'fact','entity_id':'Part','grain':'entity-instance','group_by':['part_code'],'measures':[{'name':'count','aggregate':'count'}]}])
        for view in views:
            for column in view['output_columns']:
                self.assertIn('"'+column['name']+'"',view['sql'])
        dimension_key=views[0]['output_columns'][0]
        fact_key=views[1]['output_columns'][0]
        self.assertEqual(dimension_key['source_property'],fact_key['source_property'])
        self.assertNotEqual(dimension_key['name'],fact_key['name'])

    def test_wrong_artifact_binding_fails_before_artifact_access(self):
        with patch('backend.data_pipeline_service.xml_analytics.ArtifactStore') as store,self.assertRaisesRegex(ValueError,'another schema artifact'):
            prepare_xml_load({**self.inputs,'business_schema_artifact_id':'sha256:different'})
        store.assert_not_called()

    def test_receipt_artifact_failure_keeps_committed_load_completed(self):
        pending=self.pending()
        self.assertEqual(pending['status'],'completed')
        self.assertEqual(pending['output_manifest']['evidence_status'],'pending')
        self.assertEqual(pending['output_manifest']['ods_receipt'],self.receipt)
        self.assertNotIn('data_product_draft',pending['output_manifest'])

    def test_final_result_artifact_failure_is_recoverable(self):
        record=self.record()
        result=analytics_evidence.build_analytics_evidence(self.inputs,self.receipt)
        with patch.object(run_records,'ArtifactStore',side_effect=OSError('result unavailable')):
            retained=run_records.complete(record,result)
        exposed=analytics_evidence.run_result(result,retained)
        self.assertEqual(exposed['evidence_status'],'pending')
        self.assertIsNone(exposed['data_product_draft'])
        self.assertEqual(exposed['partition_artifacts'],{})
        self.assertEqual(retained['status'],'completed')

    def test_api_reconciliation_rebuilds_artifacts_without_loading_xml(self):
        from backend.data_pipeline_service import router
        pending=self.pending()
        with patch.object(router,'approval_identity',return_value='verified-recoverer') as authorize,patch('backend.data_pipeline_service.xml_analytics.materialize_xml',side_effect=AssertionError('data load repeated')) as load:
            result=router.reconcile_analytics_evidence(pending['run_id'],SimpleNamespace(),{})
        self.assertEqual(result['run_manifest']['run_id'],pending['run_id'])
        self.assertEqual(result['run_manifest']['output_manifest']['evidence_status'],'available')
        self.assertEqual(result['run_manifest']['evidence_reconciled_by'],'verified-recoverer')
        self.assertTrue(result['run_manifest']['output_manifest']['result_artifact_id'].startswith('sha256:'))
        load.assert_not_called();self.assertEqual(authorize.call_args.kwargs['token_env'],'DATA_JOB_EXECUTION_TOKEN')

    def test_reconciliation_during_artifact_outage_stays_pending(self):
        from backend.data_pipeline_service import router
        pending=self.pending()
        with patch.object(router,'approval_identity',return_value='verified'),patch.object(analytics_evidence,'ArtifactStore',side_effect=OSError('outage')):
            result=router.reconcile_analytics_evidence(pending['run_id'],SimpleNamespace(),{})
        self.assertEqual(result['run_manifest']['status'],'completed')
        self.assertEqual(result['evidence_status'],'pending')
        self.assertIsNone(result['data_product_draft'])

    def test_pipeline_failure_response_retains_run_identity(self):
        from backend.data_pipeline_service import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app=FastAPI();app.include_router(router.router,prefix='/api/v1')
        handler=SimpleNamespace(execute=Mock(side_effect=ValueError('unsupported XML')))
        definition={**self.definition,'lifecycle_state':'approved','enabled':True}
        with patch.object(router,'_authorize_execution',side_effect=lambda request,payload:('verified',payload)),patch.object(router.job_definitions,'get',return_value=definition),patch.object(router,'_worker_execution_enabled',return_value=False),patch.object(router.handler_registry,'get',return_value=handler):
            response=TestClient(app).post('/api/v1/pipeline/jobs/definitions/xml-load/1.0.0/run',json={})
        self.assertEqual(response.status_code,422)
        identity=response.headers['x-depo-run-id']
        self.assertEqual(self.registry.get(identity)['status'],'failed')

    def test_report_returns_immutable_source_binding(self):
        model={'tables':[],'ddl_blockers':[]}
        source=ArtifactStore().ingest_bytes(b'<schema/>',filename='source.xsd',kind='engineering-schema-source',media_type='application/xml')
        structural=ArtifactStore().ingest_bytes(json.dumps(model).encode(),filename='model.json',kind='structural-model',media_type='application/json')
        metadata={'ontology_id':'registered','engineering_artifacts':{'source':source['artifact_id'],'structural_model':structural['artifact_id']}}
        manager=SimpleNamespace(OntologyUploadManager=SimpleNamespace(get_ontology=lambda _: {'status':'not_found'}))
        taxonomy=SimpleNamespace(OntologyTaxonomyService=SimpleNamespace(_resolve_metadata=lambda _:metadata))
        tree=ast.parse(Path('backend/ingestion_service/router.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if getattr(n,'name','')=='xsd_relational_report');node.decorator_list=[]
        scope={'Request':object,'Query':lambda *args,**kwargs:None,'Path':Path}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<report>','exec'),scope)
        with patch.dict(sys.modules,{'backend.Services.ontology_upload_manager':manager,'backend.ontology_service.domain.taxonomy':taxonomy}),patch('backend.depo_platform.authorization.graph_read_identity',return_value='reader'):
            result=scope['xsd_relational_report'](SimpleNamespace(),'registered')
        self.assertEqual(result['schema_artifact_id'],source['artifact_id'])


if __name__=='__main__':unittest.main()
