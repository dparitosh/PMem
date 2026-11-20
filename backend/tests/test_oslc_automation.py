from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from rdflib import Graph, URIRef
from rdflib.namespace import RDF
from backend.mesh_store import InMemoryRegistry
from backend.oslc_service import automation as auto
from backend.depo_platform.authorization import graph_read_identity


@pytest.fixture
def setup(monkeypatch):
    definitions=InMemoryRegistry();runs=InMemoryRegistry()
    definitions.put('validate-source:1.0.0',{'job_id':'validate-source','version':'1.0.0','name':'Validate CAD','lifecycle_state':'approved','enabled':True})
    runs.put('original',{'run_id':'original','job_id':'validate-source','job_version':'1.0.0','status':'completed'})
    monkeypatch.setattr(auto,'PostgresRegistry',lambda namespace: definitions if namespace=='data_job_definitions' else runs)
    monkeypatch.setattr(auto.OSLCService,'is_enabled',classmethod(lambda cls:True))
    monkeypatch.setattr(auto.OSLCService,'config',classmethod(lambda cls:SimpleNamespace(base_url='http://local')))
    monkeypatch.setenv('AUTH_MODE','token');monkeypatch.setenv('DATA_PIPELINE_SERVICE_URL','http://127.0.0.1:8019/api/v1')
    app=FastAPI();app.include_router(auto.router);app.dependency_overrides[graph_read_identity]=lambda:'reader'
    return TestClient(app),definitions,runs


def test_discovery_and_plan_are_existing_definition_not_an_approval(setup):
    client,definitions,runs=setup
    discovery=client.get('/oslc/automation').json()
    assert len(discovery['services'][0]['queryCapabilities'])==3
    plan=client.get('/oslc/automation/plans/validate-source:1.0.0').json()
    assert plan['type']=='oslc_auto:AutomationPlan' and plan['execution_enabled'] is True
    assert plan['publication_authorized'] is False
    assert len(definitions.all())==1 and len(runs.all())==1
    assert client.get('/oslc/automation/plans?limit=101').status_code==422


@pytest.mark.parametrize('status,state,verdict',[
    ('queued','queued','unavailable'),('running','inProgress','unavailable'),
    ('completed','complete','passed'),('quality_warning','complete','warning'),
    ('validation_failed','complete','failed'),('failed','complete','error'),
    ('timed_out','complete','error'),('cancelled','canceled','unavailable'),
])
def test_result_states_never_confuse_execution_with_release(status,state,verdict):
    result=auto.project('results',{'run_id':'r','job_id':'j','job_version':'1.0.0','status':status},'http://local/oslc/automation')
    assert result['oslc_auto:state']=='oslc_auto:'+state
    assert result['oslc_auto:verdict']=='oslc_auto:'+verdict
    assert result['publication_authorized'] is False


def test_nonconformance_is_not_a_passed_execution():
    result=auto.project('results',{'run_id':'r','job_id':'j','job_version':'1.0.0','status':'completed','output_manifest':{'validation':{'conforms':False}}},'http://local')
    assert result['oslc_auto:verdict']=='oslc_auto:failed'


def test_rdf_relationships_use_automation_uris(setup):
    client,_,_=setup
    response=client.get('/oslc/automation/results/original',headers={'Accept':'text/turtle'})
    assert response.status_code==200
    graph=Graph().parse(data=response.text,format='turtle')
    subject=URIRef('http://local/oslc/automation/results/original')
    assert (subject,RDF.type,URIRef(auto.AUTO+'AutomationResult')) in graph
    assert (subject,URIRef(auto.AUTO+'producedByAutomationRequest'),URIRef('http://local/oslc/automation/requests/original')) in graph
    assert (subject,URIRef(auto.AUTO+'verdict'),URIRef(auto.AUTO+'passed')) in graph


def test_submission_uses_native_replay_and_keeps_one_idempotency_key(setup,monkeypatch):
    client,_,_=setup
    monkeypatch.setattr(auto,'approval_identity',lambda *args,**kwargs:'operator')
    http=MagicMock();http.__enter__.return_value=http
    http.post.return_value=SimpleNamespace(status_code=200,json=lambda:{'run_manifest':{'run_id':'new','replay_of':'original','executed_by':'operator','job_id':'validate-source','job_version':'1.0.0','status':'queued'}})
    monkeypatch.setattr(auto.httpx,'Client',lambda **kwargs:http)
    response=client.post('/oslc/automation/requests',json={'job_id':'validate-source','version':'1.0.0','replay_run_id':'original','idempotency_key':'same-reference'},headers={'Authorization':'Bearer execution-session'})
    assert response.status_code==202
    assert response.headers['Location']=='http://local/oslc/automation/requests/new'
    assert http.post.call_args.kwargs['json']=={'idempotency_key':'same-reference'}
    assert http.post.call_args.kwargs['headers']['authorization']=='Bearer execution-session'
    assert http.post.call_count==1
    assert response.json()['publication_authorized'] is False


def test_unauthorized_requests_do_not_reach_executor(setup,monkeypatch):
    client,_,_=setup
    def reject(*args,**kwargs):raise HTTPException(403,'Execution credential required')
    monkeypatch.setattr(auto,'approval_identity',reject)
    executor=MagicMock();monkeypatch.setattr(auto.httpx,'Client',executor)
    assert client.post('/oslc/automation/requests',json={'job_id':'validate-source','version':'1.0.0','replay_run_id':'original','idempotency_key':'same'}).status_code==403
    executor.assert_not_called()


def test_plan_mismatch_and_arbitrary_inputs_are_rejected(setup,monkeypatch):
    client,_,_=setup
    monkeypatch.setattr(auto,'approval_identity',lambda *args,**kwargs:'operator')
    body={'job_id':'other-job','version':'1.0.0','replay_run_id':'original','idempotency_key':'same'}
    assert client.post('/oslc/automation/requests',json=body).status_code==409
    assert client.post('/oslc/automation/requests',json={**body,'records':[{'arbitrary':'input'}]}).status_code==422
    assert client.post('/oslc/automation/requests',json=body,headers={'Configuration-Context':'different-baseline'}).status_code==422


def test_unsupported_representation_cannot_enqueue_work(setup,monkeypatch):
    client,_,_=setup
    monkeypatch.setattr(auto,'approval_identity',lambda *args,**kwargs:'operator')
    executor=MagicMock();monkeypatch.setattr(auto.httpx,'Client',executor)
    body={'job_id':'validate-source','version':'1.0.0','replay_run_id':'original','idempotency_key':'same'}
    assert client.post('/oslc/automation/requests',json=body,headers={'Accept':'image/png'}).status_code==406
    executor.assert_not_called()



def test_platform_capabilities_include_tracking_configuration_and_automation(setup,monkeypatch):
    from backend.oslc_service.router import capabilities
    from backend.Services.oslc_trs_service import OSLCTRSService
    import backend.mesh_store as mesh
    _,definitions,runs=setup
    stores={'data_job_definitions':definitions,'data_job_runs':runs,'release_changes':InMemoryRegistry(),'semantic_configurations':InMemoryRegistry()}
    monkeypatch.setattr(mesh,'PostgresRegistry',lambda namespace:stores[namespace])
    monkeypatch.setattr(OSLCTRSService,'is_enabled',classmethod(lambda cls:True))
    monkeypatch.setattr(OSLCTRSService,'_load',classmethod(lambda cls:{'counter':23}))
    value=capabilities();assert value['scope']=='service_wide' and value['ontology_scoped'] is False
    rows={row['id']:row for row in value['capabilities']}
    assert rows['trs']['counts']=={'Tracked change position':23}
    assert rows['configuration']['counts']['Release baselines']==0
    assert rows['automation']['counts']=={'Plan resources':1,'Request resources':1,'Result resources':1}
    assert all(row['status']=='available' for row in rows.values())


def test_capability_storage_failure_is_unavailable_not_zero(setup,monkeypatch):
    from backend.oslc_service.router import capabilities
    from backend.Services.oslc_trs_service import OSLCTRSService
    import backend.mesh_store as mesh
    def unavailable(namespace):raise RuntimeError('storage down')
    monkeypatch.setattr(mesh,'PostgresRegistry',unavailable)
    monkeypatch.setattr(OSLCTRSService,'is_enabled',classmethod(lambda cls:False))
    value=capabilities();rows={row['id']:row for row in value['capabilities']}
    assert rows['trs']['status']=='disabled'
    for kind in ('configuration','automation'):
        assert rows[kind]['status']=='unavailable' and rows[kind]['counts']=={}
