from unittest.mock import Mock
import httpx
import pytest
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from backend.oslc_service import change_commands as module
from backend.depo_platform.authorization import graph_read_identity

@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv('ONTOLOGY_SERVICE_URL','http://native.test/api/v1');monkeypatch.setenv('AUTH_MODE','token')
    app=FastAPI();app.include_router(module.router);app.dependency_overrides[graph_read_identity]=lambda:'reader'
    auth=Mock(return_value='verified-owner');monkeypatch.setattr(module,'approval_identity',auth)
    seen=[];real=httpx.Client
    def handler(request):
        seen.append(request)
        return httpx.Response(200,json={'preview_id':'p','current_plan_digest':'a'*64,'change_request':None})
    monkeypatch.setattr(module.httpx,'Client',lambda **kwargs:real(transport=httpx.MockTransport(handler),**kwargs))
    # TestClient uses the real httpx.Client implementation already bound by Starlette.
    return TestClient(app),auth,seen

def command(**extra):return {'action':'submit','expected_revision':0,'expected_plan_digest':'a'*64,'reason':'Business review',**extra}

def test_central_route_forwards_only_verified_caller_credential_and_native_command(setup):
    client,auth,seen=setup
    response=client.post('/api/v1/change-control/merges/p/request',json=command(),headers={'Authorization':'Bearer private-fixture'})
    assert response.status_code==200 and len(seen)==1
    assert seen[0].url==httpx.URL('http://native.test/api/v1/ontologies/merges/p/change')
    assert seen[0].headers['authorization']=='Bearer private-fixture'
    assert 'private-fixture' not in response.text
    assert auth.call_args.kwargs['token_env']=='ONTOLOGY_APPROVAL_TOKEN'

@pytest.mark.parametrize('extra',[{'approved_by':'spoofed'},{'publish':True},{'expected_revision':True},{'expected_revision':'1'}])
def test_extra_authority_and_malformed_commands_never_reach_native_service(setup,extra):
    client,auth,seen=setup
    assert client.post('/api/v1/change-control/merges/p/request',json=command(**extra)).status_code==422
    assert seen==[]

def test_rejected_credentials_cannot_dispatch_a_native_command(setup):
    client,auth,seen=setup;auth.side_effect=HTTPException(403,'Approval access rejected')
    assert client.post('/api/v1/change-control/merges/p/request',json=command()).status_code==403
    assert seen==[]

def test_read_uses_native_owner_without_creating_or_accepting_a_request(setup):
    client,auth,seen=setup
    response=client.get('/api/v1/change-control/merges/p/request',headers={'Authorization':'Bearer reader-fixture'})
    assert response.status_code==200 and seen[0].method=='GET'
    auth.assert_not_called()

def test_openapi_resolves_central_write_profile_without_duplicate_credentials():
    from backend.depo_platform.service_runtime import create_service_app
    app=create_service_app(title='Contract',version='1',dependencies=());app.include_router(module.router)
    operation=app.openapi()['paths']['/api/v1/change-control/merges/{preview_id}/request']['post']
    assert operation['x-depo-authorization']['credential_profiles']==['ONTOLOGY_APPROVAL_TOKEN']


@pytest.mark.parametrize('status',[401,403,404,409,422,502])
@pytest.mark.parametrize('body',[b'["unavailable"]',b'null',b'"error"',b'42',b'<html>gateway unavailable</html>',b'{"detail":{"unexpected":"object"}}'])
def test_proxy_bounds_malformed_upstream_errors_without_retry(monkeypatch,status,body):
    monkeypatch.setenv('AUTH_MODE','token');monkeypatch.setenv('ONTOLOGY_SERVICE_URL','http://native.test/api/v1')
    real=httpx.Client;seen=[]
    def handler(request):
        seen.append(request);return httpx.Response(status,content=body)
    monkeypatch.setattr(module.httpx,'Client',lambda **kwargs:real(transport=httpx.MockTransport(handler),**kwargs))
    from types import SimpleNamespace
    with pytest.raises(HTTPException) as caught:
        module.native_request(SimpleNamespace(headers={'authorization':'Bearer fixture'}),'p',module.MergeChangeCommand(**command()))
    assert caught.value.status_code==(503 if status>=500 else status)
    assert len(seen)==1 and seen[0].method=='POST'
    assert isinstance(caught.value.detail,str) and len(caught.value.detail)<600


def test_pipeline_command_uses_native_owner_and_publication_credential(setup,monkeypatch):
    client,auth,seen=setup;monkeypatch.setenv('DATA_PIPELINE_SERVICE_URL','http://native.test/api/v1')
    response=client.post('/api/v1/change-control/pipeline/p/request',json=command(action='authorize'),headers={'Authorization':'Bearer publication-fixture'})
    assert response.status_code==200 and len(seen)==1
    assert str(seen[0].url)=='http://native.test/api/v1/pipeline/jobs/runs/p/change'
    assert seen[0].headers['authorization']=='Bearer publication-fixture'
    assert auth.call_args.kwargs['token_env']=='CEIM_PUBLISH_APPROVAL_TOKEN'
    assert client.post('/api/v1/change-control/pipeline/p/request',json=command(action='submit')).status_code==422
    assert len(seen)==1


def test_ontology_publication_review_uses_native_scope_and_credential(setup):
    client,auth,seen=setup
    response=client.post('/api/v1/change-control/publications/p/request',json=command(action='authorize'),headers={'Authorization':'Bearer ontology-fixture'})
    assert response.status_code==200 and len(seen)==1
    assert str(seen[0].url)=='http://native.test/api/v1/ontologies/p/change'
    assert auth.call_args.kwargs['token_env']=='ONTOLOGY_APPROVAL_TOKEN'
