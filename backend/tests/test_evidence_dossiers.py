from unittest.mock import AsyncMock
import httpx
import pytest
from rdflib import Graph
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.oslc_service.change_control import normalize, SUMMARY_PROJECTION, collect
from backend.ontology_service import evidence_dossiers as dossiers

def retained(kind='decisions'):
    raw={'assessment_id':'assessment-1','operation':'instance_bridge','status':'passed',
         'evaluated_at':'2026-10-30T00:00:00+00:00','policy_digest':'policy-digest','decision_digest':'decision-digest',
         'decisions':[{'scenario':'Review retained mapping','reasoning':'Source evidence supports review',
                       'outcome':'flagged','decision_maker':'mapping-reviewer','confidence':0.9,'confidence_basis':'not_established'}]}
    row=normalize(kind,raw)
    row['uri']='http://evidence.example/oslc/change-control/records/decisions/assessment-1'
    return row

def test_projection_uses_real_semantica_and_never_converts_policy_pass_to_approval():
    record=retained();result=dossiers.project(record)
    assert result['components']==['ContextGraph','DecisionRecorder','ProvenanceManager']
    assert any(node['type']=='Decision' for node in result['graph']['nodes'])
    assert record['review_state']=='Evidence only; not approval'
    assert result['decisions'][0]['confidence'] is None
    assert len(Graph().parse(data=result['provenance_turtle'],format='turtle')) > 0
    assert 'http://www.w3.org/ns/prov#' in result['provenance_turtle']
    assert all(row['source_uri']==record['uri'] for row in result['provenance'])

def test_projection_is_scoped_and_digest_changes_with_evidence():
    record=retained();first=dossiers.project(record)
    assert first['snapshot_sha256']==dossiers.project(record)['snapshot_sha256']
    record['evidence']['policy_digest']='changed'
    assert first['snapshot_sha256']!=dossiers.project(record)['snapshot_sha256']
    assert all(node['id'].startswith(record['uri']) for node in first['graph']['nodes'])

def test_missing_decisions_or_timestamp_does_not_invent_a_decision_time():
    record=retained();record['decision_observations'][0]['timestamp']=None
    assert dossiers.project(record)['decisions'][0]['timestamp'] is None
    record['decision_observations']=[]
    assert dossiers.project(record)['decisions']==[]

def test_assessment_observations_and_source_projection_are_bounded():
    raw={'assessment_id':'one','status':'passed','decisions':[{'reasoning':'x'*5000} for _ in range(30)]}
    row=normalize('decisions',raw)
    assert row['decision_count']==30 and row['decisions_truncated']
    assert len(row['decision_observations'])==25
    assert len(row['decision_observations'][0]['reasoning'])==1000
    assert len(SUMMARY_PROJECTION)<=64

@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv('AUTH_MODE','token');monkeypatch.setenv('DEPO_CREDENTIAL_STORE','environment')
    monkeypatch.setenv('GRAPH_READ_TOKEN','fixture-read');monkeypatch.setenv('OSLC_SERVICE_URL','http://localhost:8015/api/v1')
    peer=AsyncMock(return_value=httpx.Response(200,json=retained()))
    monkeypatch.setattr(dossiers,'async_peer_response',peer)
    app=FastAPI();app.include_router(dossiers.router)
    return TestClient(app),peer

def test_api_rechecks_source_access_and_forwards_only_caller_credential(api):
    client,peer=api
    response=client.get('/api/v1/ontologies/evidence-dossiers/decisions/assessment-1',headers={'Authorization':'Bearer fixture-read','X-DEPO-Principal-ID':'spoofed'})
    assert response.status_code==200,response.text
    assert peer.call_args.kwargs['headers']['authorization']=='Bearer fixture-read'
    assert 'x-depo-principal-id' not in peer.call_args.kwargs['headers']

@pytest.mark.parametrize('status',[403,404,503])
def test_peer_denial_or_outage_never_becomes_success(api,status):
    client,peer=api;peer.return_value=httpx.Response(status,json={'detail':'private upstream message'})
    response=client.get('/api/v1/ontologies/evidence-dossiers/decisions/assessment-1',headers={'Authorization':'Bearer fixture-read'})
    assert response.status_code==status
    assert 'private upstream message' not in response.text

def test_api_rejects_different_record_and_unauthenticated_calls(api):
    client,peer=api
    assert client.get('/api/v1/ontologies/evidence-dossiers/decisions/assessment-1').status_code in {401,403}
    peer.assert_not_awaited()
    peer.return_value=httpx.Response(200,json={**retained(),'record_key':'decisions:another'})
    assert client.get('/api/v1/ontologies/evidence-dossiers/decisions/assessment-1',headers={'Authorization':'Bearer fixture-read'}).status_code==503
