"""Real FastAPI routes with controlled registry and downstream dependencies."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from backend.agentic_service.app import app
from backend.agentic_service import router as routes
from backend.agentic_service.recovery import fingerprint
from backend.tests.test_orchestration_completion import Store


@pytest.fixture
def recovery_api(monkeypatch):
    monkeypatch.setenv('AUTH_MODE','token')
    monkeypatch.setenv('DEPO_CREDENTIAL_STORE','environment')
    monkeypatch.setenv('GRAPH_READ_TOKEN','fixture-read')
    monkeypatch.setenv('AGENTIC_APPROVAL_TOKEN','fixture-supervisor')
    # This fixture exercises inline recovery; worker queue recovery has its own tests.
    monkeypatch.setenv('AGENTIC_EXECUTION_MODE','process')
    workflow={'id':'fixture','steps':[{'agent_id':'fixture','tool_id':'first'},{'agent_id':'fixture','tool_id':'second'}]}
    data={'workflows':[workflow], 'agents':[{'id':'fixture','tools':['first','second']}],
          'tools':[{'id':name,'transport':'openapi','service':'graph','method':'GET','path':'/'+name,'mutates':False} for name in ('first','second')]}
    monkeypatch.setattr(routes.catalog,'read',lambda:data)
    store=Store()
    monkeypatch.setattr(routes,'workflow_store',store)
    from backend.mesh_store import InMemoryRegistry
    monkeypatch.setattr(routes,'workflow_controls',InMemoryRegistry())
    monkeypatch.setattr(routes,'workflow_heartbeats',Store())
    monkeypatch.setattr(routes,'_preflight_tools',AsyncMock())
    dispatch=AsyncMock(return_value={'result':{'answer':'second result'}})
    monkeypatch.setattr(routes,'_dispatch',dispatch)
    definition={'workflow':workflow,'steps':routes.workflow_plan({'workflow_id':'fixture'})['steps']}
    record={'run_id':'run-fixture','workflow_id':'fixture','status':'failed','execution_id':'old','owner':'owner',
            'started_at':datetime.now(timezone.utc).isoformat(),'updated_at':datetime.now(timezone.utc).isoformat(),
            'deadline_at':(datetime.now(timezone.utc)+timedelta(seconds=120)).isoformat(),
            'execution_payload':{'workflow_id':'fixture'},'workflow_digest':fingerprint(definition),
            'traces':[{'sequence':1,'tool_id':'first','status':'completed','result':{'answer':'retained'}}]}
    store.put('run-fixture',record)
    return TestClient(app),store,dispatch,data


def test_recovery_requires_supervision_and_skips_completed_step(recovery_api):
    client,store,dispatch,_=recovery_api
    url='/api/v1/workflow-runs/run-fixture/recover'
    headers={'Authorization':'Bearer fixture-read'}
    assert client.post(url,json={},headers=headers).status_code==403
    response=client.post(url,json={'approved_by':'supervisor','approval_token':'fixture-supervisor'},headers=headers)
    assert response.status_code==200,response.text
    assert response.json()['status']=='completed'
    assert 'execution_payload' not in response.json()
    assert dispatch.await_count==1
    assert dispatch.call_args.args[0]['tool_id']=='second'
    assert store.get('run-fixture')['traces'][0]['result']=={'answer':'retained'}
    assert store.get('run-fixture')['owner']=='owner'
    assert store.get('run-fixture')['recovery_history']
    assert client.post(url,json={'approved_by':'supervisor','approval_token':'fixture-supervisor'},headers=headers).status_code==409


def test_changed_tool_contract_blocks_recovery(recovery_api):
    client,_,dispatch,data=recovery_api
    data['tools'][1]['path']='/changed-route'
    response=client.post('/api/v1/workflow-runs/run-fixture/recover',
        json={'approved_by':'supervisor','approval_token':'fixture-supervisor'},headers={'Authorization':'Bearer fixture-read'})
    assert response.status_code==409
    dispatch.assert_not_awaited()


def advisory_review(recovery_api):
    from starlette.requests import Request
    from backend.agentic_service import sessions
    client, store, dispatch, data = recovery_api
    workflow = data['workflows'][0]
    workflow['id'] = 'ontology-review-and-bridge-plan'
    ids = ['ontology.agent.intake', 'ontology.agent.review']
    for step, tool, tool_id in zip(workflow['steps'], data['tools'], ids):
        step['tool_id'] = tool['id'] = tool_id
    data['agents'][0]['tools'] = ids
    definition = {'workflow': workflow, 'steps': routes.workflow_plan({'workflow_id': workflow['id']})['steps']}
    request = Request({'type': 'http', 'headers': [(b'authorization', b'Bearer fixture-read')]})
    record = store.get('run-fixture')
    record.update(workflow_id=workflow['id'], execution_payload={'workflow_id': workflow['id']},
                  workflow_definition=definition, workflow_digest=fingerprint(definition),
                  owner=sessions.owner(request, routes.graph_read_identity(request)))
    record['traces'][0]['tool_id'] = ids[0]
    store.put('run-fixture', record)
    return client, store, dispatch, data


def test_owner_recovers_advisory_review_without_approval(recovery_api):
    client, store, dispatch, _ = advisory_review(recovery_api)
    response = client.post('/api/v1/workflow-runs/run-fixture/recover', json={}, headers={'Authorization': 'Bearer fixture-read'})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'completed'
    assert dispatch.await_count == 1
    assert dispatch.call_args.args[0]['tool_id'] == 'ontology.agent.review'


def test_advisory_review_status_exposes_reader_recovery(recovery_api):
    client, _, _, _ = advisory_review(recovery_api)
    response = client.get('/api/v1/workflow-runs/run-fixture', headers={'Authorization': 'Bearer fixture-read'})
    assert response.status_code == 200
    assert response.json()['recover_allowed'] is True
    assert response.json()['recovery_requires_approval'] is False


def test_owner_recovery_can_enqueue_worker_review_without_approval(recovery_api, monkeypatch):
    from backend.agentic_service import durable_workflows
    client, _, _, _ = advisory_review(recovery_api)
    enqueue = AsyncMock(return_value={'run_id': 'run-fixture', 'status': 'queued'})
    monkeypatch.setattr(durable_workflows, 'execution_mode', lambda: 'worker')
    monkeypatch.setattr(durable_workflows, 'enqueue', enqueue)
    response = client.post('/api/v1/workflow-runs/run-fixture/recover', json={}, headers={'Authorization': 'Bearer fixture-read'})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'queued'
    assert enqueue.await_count == 1


def test_other_reader_cannot_recover_advisory_review(recovery_api):
    client, store, dispatch, _ = advisory_review(recovery_api)
    record = store.get('run-fixture'); record['owner'] = 'another-reader'; store.put('run-fixture', record)
    response = client.post('/api/v1/workflow-runs/run-fixture/recover', json={}, headers={'Authorization': 'Bearer fixture-read'})
    assert response.status_code == 403
    dispatch.assert_not_awaited()


def test_mutating_review_does_not_inherit_reader_recovery(recovery_api):
    client, _, dispatch, data = advisory_review(recovery_api)
    data['tools'][1]['mutates'] = True
    response = client.post('/api/v1/workflow-runs/run-fixture/recover', json={}, headers={'Authorization': 'Bearer fixture-read'})
    assert response.status_code == 403
    dispatch.assert_not_awaited()


@pytest.mark.parametrize('action', ['pause', 'resume', 'cancel'])
def test_owner_controls_advisory_review_without_approval(recovery_api, action):
    client, store, _, _ = advisory_review(recovery_api)
    record = store.get('run-fixture'); record['status'] = 'running'; store.put('run-fixture', record)
    response = client.post('/api/v1/workflow-runs/run-fixture/control', json={'action': action}, headers={'Authorization': 'Bearer fixture-read'})
    assert response.status_code == 200, response.text


def test_reconciliation_is_authorized_and_retains_audit_evidence(recovery_api):
    client,store,_,_=recovery_api
    record=store.get('run-fixture')
    record.update(reconciliation_required=True,pending_step={'sequence':2,'tool_id':'second','mutates':True,'attempt':1})
    store.put('run-fixture',record)
    url='/api/v1/workflow-runs/run-fixture/reconcile'
    body={'outcome':'completed','evidence':'Verified downstream publication receipt 123','result':{'publication_id':'123'}}
    assert client.post(url,json=body,headers={'Authorization':'Bearer fixture-read'}).status_code==403
    response=client.post(url,json={**body,'approved_by':'supervisor'},headers={'Authorization':'Bearer fixture-supervisor'})
    assert response.status_code==200,response.text
    retained=store.get('run-fixture')
    assert retained['traces'][-1]['result']['publication_id']=='123'
    assert retained['reconciliations'][-1]['evidence']==body['evidence']
    assert not retained['reconciliation_required']


def test_recovery_preflight_failure_does_not_strand_a_claim(recovery_api,monkeypatch):
    client,store,_,_=recovery_api
    monkeypatch.setattr(routes,'_preflight_tools',AsyncMock(side_effect=ValueError('Invalid contract input')))
    response=client.post('/api/v1/workflow-runs/run-fixture/recover',
        json={'approved_by':'supervisor','approval_token':'fixture-supervisor'},headers={'Authorization':'Bearer fixture-read'})
    assert response.status_code==422
    assert store.get('run-fixture')['status']=='failed'
    assert store.get('run-fixture')['execution_id']=='old'


def test_rdf_mapping_evidence_and_artifact_change_detection(monkeypatch,tmp_path):
    from backend.agentic_service.ontology_orchestrator import inspect_ontology, plan_bridge, structure_review
    monkeypatch.setenv('ONTOLOGY_AGENT_ALLOWED_ROOTS',str(tmp_path))
    monkeypatch.setenv('ONTOLOGY_AGENT_LLM_ENABLED','false')
    path=tmp_path/'test.ttl'
    path.write_text('@prefix owl: <http://www.w3.org/2002/07/owl#> .\n'
                    '@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n'
                    '<urn:ontology> a owl:Ontology . <urn:Product> a owl:Class .\n'
                    '<urn:serial> a owl:DatatypeProperty ; rdfs:domain <urn:Product> ; rdfs:range <urn:string> .')
    summary=inspect_ontology(str(path))
    result=plan_bridge({'attributes':[{'name':'serial','domain_iri':'urn:Product','range_iri':'urn:string',
                                     'datatype_iri':'urn:string','ontology_iri':'urn:ontology'}]},ontology_summary=summary)
    candidate=result['alignment_candidates'][0]
    assert candidate['validation_checks']['datatype_compatibility']=='passed'
    assert candidate['validation_checks']['domain_range_compatibility']=='passed'
    assert candidate['unresolved_checks']==['human_approval']
    path.write_text('<urn:New> a <http://www.w3.org/2002/07/owl#Class> .')
    with pytest.raises(ValueError,match='changed'):
        structure_review({'ontology_path':str(path),'artifact_digest':summary['artifact_digest']})
