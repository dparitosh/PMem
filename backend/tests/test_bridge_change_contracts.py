from unittest.mock import Mock
import httpx
import pytest
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from backend.tests.test_bridge_change_lifecycle import setup
from backend.agentic_service import bridge_router,bridge_change
from backend.oslc_service import change_commands
from backend.depo_platform.authorization import graph_read_identity

@pytest.fixture
def native(setup,monkeypatch):
    jobs,value,ids=setup
    monkeypatch.setattr(bridge_router,'jobs',jobs)
    monkeypatch.setenv('AUTH_MODE','token');monkeypatch.setenv('GRAPH_READ_TOKEN','read-fixture')
    monkeypatch.setenv('AGENTIC_APPROVAL_TOKEN','approval-fixture');monkeypatch.setenv('AGENTIC_APPROVAL_TOKEN_ACTOR','verified-owner')
    app=FastAPI();app.include_router(bridge_router.router)
    return TestClient(app),jobs,value,ids

def body(jobs,value,ids,**extra):
    status=bridge_change.view(jobs,value['job_id'])
    return dict(action='submit',expected_revision=0,expected_plan_digest=status['current_plan_digest'],reason='Review selected source links',candidate_ids=ids,**extra)


def test_native_command_requires_approval_and_uses_verified_actor(native):
    client,jobs,value,ids=native;path=f"/api/v1/workflows/bridge/previews/{value['job_id']}/change"
    payload=body(jobs,value,ids)
    assert client.post(path,json=payload,headers={'Authorization':'Bearer read-fixture'}).status_code==403
    result=client.post(path,json=payload,headers={'Authorization':'Bearer approval-fixture'})
    assert result.status_code==200 and result.json()['change_request']['requested_by']=='verified-owner'
    assert result.json()['change_request']['state']=='submitted' and jobs.graph.calls==[]


@pytest.mark.parametrize('extra',[{'approved_by':'forged'},{'approval_token':'forged'},{'publish':True},{'expected_revision':True},{'candidate_ids':[17]}])
def test_native_command_rejects_authority_and_malformed_selection(native,extra):
    client,jobs,value,ids=native;payload=body(jobs,value,ids);payload.update(extra)
    response=client.post(f"/api/v1/workflows/bridge/previews/{value['job_id']}/change",json=payload,headers={'Authorization':'Bearer approval-fixture'})
    assert response.status_code==422 and jobs.store.get(value['publication_job_id']) is None


def test_central_mapping_command_forwards_only_callers_profile(monkeypatch):
    monkeypatch.setenv('AUTH_MODE','token');monkeypatch.setenv('AGENTIC_SERVICE_URL','http://agent.test/api/v1')
    auth=Mock(return_value='owner');monkeypatch.setattr(change_commands,'approval_identity',auth)
    seen=[];real=httpx.Client
    def handler(request):seen.append(request);return httpx.Response(200,json={'preview_id':'p'})
    monkeypatch.setattr(change_commands.httpx,'Client',lambda **kwargs:real(transport=httpx.MockTransport(handler),**kwargs))
    app=FastAPI();app.include_router(change_commands.router)
    response=TestClient(app).post('/api/v1/change-control/bridges/p/request',json={'action':'submit','expected_revision':0,'expected_plan_digest':'a'*64,'reason':'Review','candidate_ids':['one']},headers={'Authorization':'Bearer caller-fixture'})
    assert response.status_code==200 and len(seen)==1
    assert str(seen[0].url)=='http://agent.test/api/v1/workflows/bridge/previews/p/change'
    assert seen[0].headers['authorization']=='Bearer caller-fixture'
    assert auth.call_args.kwargs['token_env']=='AGENTIC_APPROVAL_TOKEN'


def test_openapi_resolves_native_and_central_mapping_profile(native):
    from backend.depo_platform.service_runtime import create_service_app
    app=create_service_app(title='Mapping contracts',version='1',dependencies=())
    app.include_router(bridge_router.router);app.include_router(change_commands.router)
    paths=app.openapi()['paths']
    for path in ['/api/v1/change-control/bridges/{preview_id}/request','/api/v1/workflows/bridge/previews/{preview_id}/change']:
        assert paths[path]['post']['x-depo-authorization']['credential_profiles']==['AGENTIC_APPROVAL_TOKEN']
