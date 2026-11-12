from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.qif.app import app
from backend.qif import router as routes

@pytest.fixture
def client(monkeypatch,tmp_path):
    monkeypatch.setenv('AUTH_MODE','token');monkeypatch.setenv('DEPO_CREDENTIAL_STORE','environment')
    monkeypatch.setenv('GRAPH_READ_TOKEN','read-fixture');monkeypatch.setenv('GRAPH_READ_TOKEN_ACTOR','fixture-reader')
    monkeypatch.delenv('GRAPH_READ_TOKEN_EXPIRES_AT',raising=False);monkeypatch.delenv('DEPO_TOKEN_EXPIRES_AT',raising=False)
    (tmp_path/'audit.ttl').write_text('fixture artifact',encoding='utf-8')
    def missing(_):raise HTTPException(404,'fixture task not found')
    service=SimpleNamespace(list=Mock(return_value=[]),get=Mock(side_effect=missing),preview=Mock(return_value={'task_id':'a'*32,'status':'awaiting_approval'}),_task_dir=Mock(return_value=tmp_path))
    monkeypatch.setattr(routes,'task_service',service)
    return TestClient(app),service

@pytest.mark.parametrize('path',['/tasks','/tasks/'+'a'*32,'/tasks/'+'a'*32+'/preview','/tasks/'+'a'*32+'/artifacts/audit.ttl'])
@pytest.mark.parametrize('headers',[{}, {'Authorization':'Bearer incorrect'}])
def test_task_reads_reject_unauthorized_requests_before_storage(client,path,headers):
    http,service=client
    assert http.get('/api/v1/qif'+path,headers=headers).status_code in (401,403)
    assert all(not getattr(service,name).called for name in ('list','get','preview','_task_dir'))

def test_read_identity_can_list_preview_and_download(client):
    http,_=client;headers={'Authorization':'Bearer read-fixture'}
    assert http.get('/api/v1/qif/tasks',headers=headers).json()=={'tasks':[]}
    assert http.get('/api/v1/qif/tasks/'+'a'*32+'/preview',headers=headers).status_code==200
    artifact=http.get('/api/v1/qif/tasks/'+'a'*32+'/artifacts/audit.ttl',headers=headers)
    assert artifact.status_code==200 and artifact.text=='fixture artifact'

def test_reference_reads_remain_public_and_task_contract_requires_read_profile(client):
    http,_=client
    assert http.get('/api/v1/qif/health').status_code==200
    operation=app.openapi()['paths']['/api/v1/qif/tasks']['get']
    assert operation['x-depo-authorization']['credential_profiles']==['GRAPH_READ_TOKEN']
    assert operation['security']
    assert 'not XSD validation' in app.openapi()['paths']['/api/v1/qif/instances/check']['post']['summary']
