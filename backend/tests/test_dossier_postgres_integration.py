"""Opt-in actual PostgreSQL + OSLC read + semantic dossier service contract."""
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.mesh_store import PostgresRegistry
from backend.tests.test_postgres_workflow_integration import isolated_postgres

def test_retained_assessment_flows_through_oslc_to_semantic_dossier(isolated_postgres,monkeypatch):
    from backend.ontology_service.intelligence import SemanticIntelligence
    from backend.depo_platform.decision_policy import decision
    from backend.ontology_service import evidence_dossiers as dossiers
    from backend.oslc_service.change_control import router as evidence_router
    monkeypatch.setenv('AUTH_MODE','token');monkeypatch.setenv('DEPO_CREDENTIAL_STORE','environment')
    monkeypatch.setenv('GRAPH_READ_TOKEN','fixture-read');monkeypatch.setenv('OSLC_SERVICE_URL','http://localhost:8015/api/v1')
    engine=SemanticIntelligence(None,registry=PostgresRegistry('test_dossier_policies'))
    report=engine.evaluate_decisions('instance_bridge',[decision(.9,decision_maker='test-reviewer',scenario='Review retained evidence',reasoning='Explicit source evidence',outcome='flagged')])
    assessment_id=report['assessment_id']
    assert PostgresRegistry('semantic_decision_assessments').get(assessment_id)
    evidence_app=FastAPI();evidence_app.include_router(evidence_router)
    async def peer(method,endpoint,*,headers,**kwargs):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(evidence_app),base_url='http://evidence') as client:
            return await client.request(method,httpx.URL(endpoint).raw_path.decode(),headers=headers)
    monkeypatch.setattr(dossiers,'async_peer_response',peer)
    app=FastAPI();app.include_router(dossiers.router)
    response=TestClient(app).get('/api/v1/ontologies/evidence-dossiers/decisions/'+assessment_id,headers={'Authorization':'Bearer fixture-read'})
    assert response.status_code==200,response.text
    result=response.json()
    assert result['record_key']=='decisions:'+assessment_id
    assert result['decisions'][0]['decision_maker']=='test-reviewer'
    assert result['decisions'][0]['confidence'] is None
    assert result['source_snapshot']['review_state']=='Evidence only; not approval'
    assert result['provenance'] and result['provenance_turtle']
    assert PostgresRegistry('semantic_decision_assessments').get(assessment_id)['assessment_id']==assessment_id
