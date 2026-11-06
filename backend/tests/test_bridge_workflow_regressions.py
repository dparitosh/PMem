import ast
import asyncio
from contextlib import nullcontext, contextmanager
from pathlib import Path
from types import SimpleNamespace, ModuleType
from unittest.mock import Mock, patch
import unittest
import sys
import json


def load(path, name, scope):
    tree=ast.parse(Path(path).read_text(encoding='utf-8'))
    nodes=[node for node in tree.body if getattr(node,'name','')==name]
    for node in nodes:
        if hasattr(node,'decorator_list'): node.decorator_list=[]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),path,'exec'),scope)
    return scope[name]


class BridgeWorkflowRegressionTests(unittest.TestCase):
    def test_bridge_transaction_deadline_is_attached_to_driver_work(self):
        graph=Mock()
        graph.run.return_value.single.return_value={'found':1}
        graph.execute_write.side_effect=lambda work: work._timeout
        @contextmanager
        def session(): yield graph
        neo=ModuleType('neo4j')
        def unit_of_work(*,timeout):
            def decorate(fn):
                def work(*args): return fn(*args)
                work._timeout=timeout
                return work
            return decorate
        neo.unit_of_work=unit_of_work
        scope=dict(digest=lambda _: 'digest',session=session,_publish_transaction=lambda *args:None,_bounded_query=lambda text:text)
        publish=load('backend/graph_service/bridge_publication.py','publish',scope)
        command={'ontology_id':'chosen','request_digest':'digest','rows':[{'candidate_id':'a','import_id':'i','import_row_key':'r','ontology_class_element_id':'t','target_ontology_type':'Class'}]}
        from backend.depo_platform.operations import OperationContext, operation_scope
        from datetime import datetime,timezone,timedelta
        ctx=OperationContext('test',(datetime.now(timezone.utc)+timedelta(seconds=4)).isoformat())
        with patch.dict(sys.modules,{'neo4j':neo}),operation_scope(ctx):
            timeout=publish(command)
        self.assertGreater(timeout,0)
        self.assertLessEqual(timeout,4)

    def test_wrong_ontology_target_aborts_before_link_write(self):
        tx=Mock()
        tx.run.side_effect=[SimpleNamespace(single=lambda:{'receipt':None}),SimpleNamespace(data=lambda:[{'sources':1,'targets':0}])]
        from backend.graph_service.bridge_publication import verify_semantic_projection
        scope=dict(json=json,datetime=None,timezone=None,verify_semantic_projection=verify_semantic_projection)
        publish=load('backend/graph_service/bridge_publication.py','_publish_transaction',scope)
        command={'publication_id':'p','ontology_id':'selected-v2','rows':[{'candidate_id':'c'}]}
        with self.assertRaisesRegex(ValueError,'no links were written'):
            publish(tx,command)
        self.assertEqual(tx.run.call_count,2)
        self.assertEqual(tx.run.call_args.kwargs['ontology_id'],'selected-v2')
        self.assertIn('target.ontology_id=$ontology_id',tx.run.call_args.args[0])

    def test_source_lookup_preserves_selected_version_instead_of_prefix(self):
        service=SimpleNamespace(_resolve_ontology_id=lambda value:value,
            _ontology_metadata=lambda _: {'prefix':'shared'},
            _load_import_task=lambda _: {'parsed_rows':[]},
            _load_ontology_term_lookup=Mock(return_value={'part':[]}),
            _read_ontology_file=lambda _: 'rdf')
        importer=SimpleNamespace(_load_ontology_class_lookup=Mock(return_value={}))
        source_module=ModuleType('backend.Services.semantic_workflow_service')
        source_module.SemanticWorkflowService=service
        import_module=ModuleType('backend.Services.unified_data_import')
        import_module.UnifiedDataImportService=importer
        cls=load('backend/ingestion_service/bridge_source.py','LocalBridgeSource',
                 dict(digest=lambda _: 'hash',canonical_lookup=lambda value:value))
        with patch.dict(sys.modules,{'backend.Services.semantic_workflow_service':source_module,
                                    'backend.Services.unified_data_import':import_module}):
            cls().snapshot('selected-version-2','instance')
        service._load_ontology_term_lookup.assert_called_once_with('selected-version-2')
        importer._load_ontology_class_lookup.assert_called_once_with('selected-version-2')

    def test_engineering_workflow_accepts_durable_job_without_receipt(self):
        class Response:
            def __init__(self,payload,status=200):self.payload=payload;self.status_code=status
            def json(self):return self.payload
            def raise_for_status(self):pass
        calls=[]
        class Client:
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def get(self,*args,**kwargs):return Response({'lifecycle_status':'approved'})
            async def post(self,url,**kwargs):
                calls.append((url,kwargs))
                if url.endswith('/evaluate'):return Response({'compliant':True})
                if url.endswith('/quality-gate'):return Response({'publish_recommended':True})
                if url.endswith('/register'):return Response({'ontology_id':'selected'})
                return Response({'ontology_id':'selected','job_id':'durable','status':'queued'},202)
        async def thread(fn,*args,**kwargs):return fn(*args,**kwargs)
        scope=dict(Any=__import__('typing').Any, EngineeringSchemaConverter=object, ontology_writer=lambda fn:fn, dependency_stage=lambda *args:nullcontext(),run_in_threadpool=thread,
            httpx=SimpleNamespace(AsyncClient=lambda **kwargs:Client()),
            service_bearer_headers=lambda *args,**kwargs:{},json=json,hashlib=__import__('hashlib'),
            PathName=SimpleNamespace(safe_stem=lambda _: 'source'))
        cls=load('backend/ingestion_service/engineering_workflow.py','EngineeringWorkflow',scope)
        workflow=object.__new__(cls)
        workflow._isolated_conversion=False
        workflow.converter=SimpleNamespace(convert=lambda **kwargs:{'ontology':{'name':'N','prefix':'p','turtle':'test'}})
        workflow.ontology_url='http://ontology/api/v1';workflow.timeout=30
        workflow._governance_entities=lambda _:[]
        workflow._require_publishable=lambda _:None
        result=asyncio.run(workflow._run(filename='source.xsd',content=b'x',publish=True))
        self.assertEqual(result['status'],'publication_queued')
        self.assertEqual(result['publication_job']['job_id'],'durable')
        self.assertEqual(calls[-1][1]['params'],{'background':True})
        self.assertNotIn('graph_publication',result)


if __name__=='__main__':unittest.main()
