"""Isolated microservice transport/contract checks. No live writes or credentials."""
import asyncio
import uuid
from types import SimpleNamespace
import httpx
import pytest
from fastapi.testclient import TestClient
from backend.depo_platform.decision_policy import policy_blocks
from backend.depo_platform.service_runtime import create_service_app


@pytest.mark.parametrize('report,blocked', [
    ({'status':'not_configured','compliant':None,'blocking':False,'checks':[]},False),
    ({'status':'passed','compliant':True,'blocking':False,'checks':[{'compliant':True}]},False),
    ({'status':'blocked','compliant':True,'blocking':False,'checks':[]},True),
    ({'status':'unavailable','blocking':True},True),
    ({'status':'not_configured','blocking':False,'compliant':True},True),
    ({'compliant':True},False), ({'compliant':'true'},True), ({},True), (None,True),
])
def test_policy_contract_distinguishes_absence_failure_and_rolling_upgrade(report, blocked):
    assert policy_blocks(report) is blocked


@pytest.mark.parametrize('workflow_kind',['engineering','profile'])
def test_import_no_policy_advances_to_quality_without_fabricating_confidence(monkeypatch, workflow_kind):
    from backend.tests.test_engineering_workflow import StubConverter
    from backend.ingestion_service.engineering_workflow import EngineeringWorkflow
    from backend.ingestion_service.workflow import SemanticIngestionWorkflow
    calls=[]
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def post(self,url,**kwargs):
            calls.append((url,kwargs))
            return httpx.Response(200,request=httpx.Request('POST',url),json=(
                {'status':'not_configured','compliant':None,'blocking':False,'checks':[]} if url.endswith('evaluate')
                else {'publish_recommended':False}))
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:Client())
    for module in ('backend.ingestion_service.engineering_workflow','backend.ingestion_service.workflow'):
        monkeypatch.setattr(module+'.service_bearer_headers',lambda *args,**kwargs:{})
    if workflow_kind=='engineering':
        result=asyncio.run(EngineeringWorkflow(StubConverter())._run(filename='test.exp',content=b'SCHEMA x; END_SCHEMA;',publish=True))
    else:
        result=asyncio.run(SemanticIngestionWorkflow().run(normalized={'entities':[{'id':'x'}],'relationships':[],
            'records_processed':1,'provenance':{}},name='Test',prefix='test',base_uri='urn:test:',publish=True))
    assert result['status']=='quality_blocked' and len(calls)==2
    decision=calls[0][1]['json']['decision']
    assert decision['operation']=='ontology_import' and decision['confidence']==0
    assert decision['outcome']=='flagged' and decision['confidence_basis']=='not_established'


def test_graph_control_plane_uses_shared_budget_and_safe_failures(monkeypatch):
    from backend.graph_service import control_plane_client as module
    captured=[]
    monkeypatch.setattr(module,'service_bearer_headers',lambda *args,**kwargs:{'Authorization':'Bearer test'})
    def peer(method,url,**kwargs):
        captured.append((method,url,kwargs))
        return httpx.Response(200,json={'runs':[]},request=httpx.Request(method,url))
    monkeypatch.setattr(module,'peer_response',peer)
    result=module.ControlPlaneClient(timeout_seconds=3).job_runs(5)
    assert result=={'runs':[]} and captured[0][2]['budget']==3
    assert captured[0][2]['headers']['Authorization']=='Bearer test'
    def fail(*args,**kwargs): raise httpx.ConnectError('private proxy/credential details')
    monkeypatch.setattr(module,'peer_response',fail)
    with pytest.raises(module.ControlPlaneUnavailable) as error: module.ControlPlaneClient().job_runs(5)
    assert 'private' not in str(error.value)


def test_sysml_pagination_has_total_deadline_and_ignores_ambient_proxy(monkeypatch):
    from backend.ingestion_service import sysml_repository as repo
    captured=[]
    async def handler(request):
        await asyncio.sleep(.03)
        return httpx.Response(200,json=[{'@id':'x'}],headers={'Link':'<?page[after]='+str(len(captured)) +'>; rel="next"'})
    native=httpx.AsyncClient
    def client(**kwargs):
        captured.append(kwargs)
        assert kwargs['trust_env'] is False
        return native(transport=httpx.MockTransport(handler),**kwargs)
    monkeypatch.setattr(repo.httpx,'AsyncClient',client)
    monkeypatch.setattr('backend.depo_platform.network.bounded_timeout_seconds',lambda *args,**kwargs:.04)
    cfg=SimpleNamespace(enabled=True,base_url='https://repo.example',project_id='p',commit_id='c',page_size=10,token='test',request_timeout_seconds=5)
    with pytest.raises(TimeoutError): asyncio.run(repo.read_snapshot(cfg))


def test_request_ids_are_bounded_and_cannot_echo_arbitrary_content(monkeypatch):
    monkeypatch.setenv('ALLOWED_ORIGINS','http://localhost:3000')
    app=create_service_app(title='Correlation',version='1',dependencies=())
    client=TestClient(app)
    for bad in ('x'*1000,'private key value'):
        response=client.get('/healthz',headers={'X-Request-ID':bad})
        assert response.status_code==200
        assert str(uuid.UUID(response.headers['X-Request-ID']))==response.headers['X-Request-ID']
    assert client.get('/healthz',headers={'X-Request-ID':'trace-123'}).headers['X-Request-ID']=='trace-123'


@pytest.mark.parametrize('tamper',[False,True])
def test_policy_peer_response_is_bound_to_requested_decisions(monkeypatch,tamper):
    from backend.depo_platform import decision_policy as adapter
    from backend.depo_platform.bridge_contract import digest
    decisions=[adapter.decision(.95,candidate_id='one')]
    monkeypatch.setattr(adapter,'service_bearer_headers',lambda *a,**kw:{'Authorization':'Bearer test'})
    def peer(method,endpoint,**kwargs):
        assert method=='POST' and kwargs['json']['decisions']==decisions
        return httpx.Response(200,request=httpx.Request(method,endpoint),json={
            'operation':'instance_bridge','decision_digest':'wrong' if tamper else digest(decisions),
            'assessment_id':'decision-policy-'+'a'*64,'status':'not_configured','blocking':False,
            'compliant':None,'checks':[],'blocked_decision_indices':[]})
    monkeypatch.setattr(adapter,'peer_response',peer)
    report=adapter.assess_decisions('instance_bridge',decisions)
    assert report['status']==('unavailable' if tamper else 'not_configured')


def test_windows_artifacts_support_deep_installation_paths(tmp_path):
    import os
    if os.name!='nt': pytest.skip('Windows MAX_PATH regression')
    from backend.artifact_store import ArtifactStore
    store=ArtifactStore(tmp_path/('customer deployment-'*6)/'artifacts')
    saved=store.ingest_bytes(b'customer test data',filename='test.xml',kind='test')
    metadata,content=store.resolve(saved['artifact_id'])
    assert content.read_bytes()==b'customer test data'
    assert len(str(content))>260


@pytest.mark.parametrize('failure',['timeout','invalid_receipt','oversized_response'])
def test_speed_publication_retains_reconciliation_on_peer_failure(monkeypatch,tmp_path,failure):
    from backend.data_pipeline_service.app import app
    from backend.data_pipeline_service import speed_router, speed_path
    from backend.mesh_store import InMemoryRegistry
    registry=InMemoryRegistry()
    registry.put('r1',{'reconciliation_id':'r1','status':'ready_for_approved_publication','partition_artifact_id':'test'})
    monkeypatch.setattr(speed_path,'reconciliations',registry)
    monkeypatch.setattr(speed_router,'approval_identity',lambda *a,**kw:'test-reviewer')
    monkeypatch.setattr(speed_router,'service_bearer_headers',lambda *a,**kw:{})
    source=tmp_path/'partition.json'
    source.write_text('{"standard":"qif","entities":[],"relationships":[]}')
    monkeypatch.setattr(speed_router,'ArtifactStore',lambda: SimpleNamespace(resolve=lambda key:({},source)))
    calls=[]
    async def peer(method,url,**kwargs):
        calls.append(url)
        if failure=='timeout': raise TimeoutError('private peer details')
        if failure=='oversized_response': raise ValueError('private response details')
        return httpx.Response(200,request=httpx.Request(method,url),json={'status':'published','ontology_id':'wrong','publication_id':'r1'})
    monkeypatch.setattr(speed_router,'async_peer_response',peer)
    response=TestClient(app).post('/api/v1/pipeline/speed/reconciliations/r1/publish',json={'ontology_id':'test-ontology'})
    assert response.status_code==503 and 'private' not in response.text
    assert registry.get('r1')['status']=='ready_for_approved_publication' and len(calls)==1


def test_sysml_total_timeout_is_reported_as_dependency_unavailable(monkeypatch):
    from backend.ingestion_service import router as module
    from fastapi import Request, HTTPException
    async def expired(*args,**kwargs): raise TimeoutError('private repository details')
    monkeypatch.setattr('backend.ingestion_service.sysml_repository.read_snapshot',expired)
    monkeypatch.setattr('backend.depo_platform.authorization.approval_identity',lambda *a,**kw:'test-reviewer')
    request=Request({'type':'http','headers':[],'client':('127.0.0.1',1)})
    with pytest.raises(HTTPException) as error: asyncio.run(module.import_sysml_commit(request,{}))
    assert error.value.status_code==503 and 'private' not in str(error.value.detail)


def test_ontology_policy_batch_contract_preserves_evidence_and_rejects_mixed_requests(monkeypatch):
    from backend.ontology_service import router as module
    from backend.tests.test_decision_policy_integration import intelligence
    from backend.depo_platform.decision_policy import decision
    from backend.depo_platform.bridge_contract import digest
    service=intelligence()
    monkeypatch.setattr(module,'intelligence',service)
    app=create_service_app(title='Policy contract',version='1',dependencies=())
    app.add_api_route('/evaluate',module.evaluate_policies,methods=['POST'])
    client=TestClient(app)
    rows=[decision(.95,candidate_id='one')]
    response=client.post('/evaluate',json={'operation':'instance_bridge','decisions':rows})
    assert response.status_code==200 and response.json()['decision_digest']==digest(rows)
    assert response.json()['status']=='not_configured'
    assert response.json()['assessment_id'] in service.evidence
    for payload in ({'operation':'typo','decisions':rows}, {'operation':'instance_bridge','decisions':[]},
                    {'operation':'instance_bridge','decisions':rows,'decision':{}},
                    {'operation':'instance_bridge','decisions':rows,'exception_policy_ids':['skip']}):
        assert client.post('/evaluate',json=payload).status_code==422
