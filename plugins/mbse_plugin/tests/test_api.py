import base64
import httpx
import pytest
from fastapi.testclient import TestClient
from mbse_plugin import app as module
from mbse_plugin.registration import register


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('MBSE_PLUGIN_TOKEN', 'test')
    monkeypatch.setenv('DEPO_INGESTION_TOKEN', 'execution-test-key')
    return TestClient(module.app)


@pytest.mark.parametrize('body', [
    {'entities': [{'id': 'a', 'properties': None}]},
    {'entities': [{'id': 'a'}], 'relationships': [{'source_id': [], 'target_id': 'a'}]},
])
def test_invalid_graph(client, body):
    assert client.post('/visualization', headers={'Authorization': 'Bearer test'}, json=body).status_code == 422


@pytest.mark.parametrize('status', [200, 403, 422])
def test_import_preview_and_errors(client, monkeypatch, status):
    monkeypatch.setenv('DEPO_INGESTION_URL', 'http://ingestion/api/v1')
    original = httpx.AsyncClient
    def handler(request):
        assert request.url.path == '/api/v1/governed-import'
        assert request.headers['Authorization'] == 'Bearer execution-test-key'
        return httpx.Response(status, json={'status': 'completed', 'run_manifest': {'run_id': 'run-1'}, 'preview': {'entities': [{'id': 'a'}], 'relationships': []}})
    monkeypatch.setattr(module.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    r = client.post('/imports', headers={'Authorization': 'Bearer test'}, json={'filename': 'a.xmi', 'profile': 'sysml-v1', 'content_base64': base64.b64encode(b'<model/>').decode()})
    assert r.status_code == status
    if status == 200:
        assert client.post('/visualization', headers={'Authorization': 'Bearer test'}, json=r.json()['preview']).status_code == 200


def test_import_without_run_id_is_rejected(client, monkeypatch):
    monkeypatch.setenv('DEPO_INGESTION_URL', 'http://ingestion/api/v1')
    original = httpx.AsyncClient
    monkeypatch.setattr(module.httpx, 'AsyncClient', lambda **kw: original(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'status': 'completed'})), **kw))
    response = client.post('/imports', headers={'Authorization': 'Bearer test'}, json={
        'filename': 'a.xmi', 'profile': 'sysml-v1', 'content_base64': base64.b64encode(b'<model/>').decode()})
    assert response.status_code == 502


@pytest.mark.parametrize('authorized', [True, False])
def test_upstream_check_does_not_execute_jobs(client, monkeypatch, authorized):
    monkeypatch.setenv('DEPO_INGESTION_URL', 'http://ingestion/api/v1')
    original = httpx.AsyncClient
    def handler(request):
        assert request.method == 'GET'
        assert request.url.path == '/auth/credential-check'
        assert request.url.params['profile'] == 'DATA_JOB_EXECUTION_TOKEN'
        return httpx.Response(200, json={'profile': 'DATA_JOB_EXECUTION_TOKEN',
                                        'status': 'authorized' if authorized else 'rejected'})
    monkeypatch.setattr(module.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    response = client.get('/upstream-check', headers={'Authorization': 'Bearer test'})
    assert response.status_code == (200 if authorized else 502)
    if authorized:
        assert response.json()['job_executed'] is False


def test_registration_and_contract(client):
    class Host:
        def __init__(self): self.tools = {}
        def register_tool(self, name, function): self.tools[name] = function
    host = Host()
    register(host)
    assert set(host.tools) == {'mbse.import', 'mbse.visualize', 'smw.template', 'smw.preview', 'cameo.template', 'cameo.validate'}
    assert client.get('/tools').status_code == 401
    assert client.get('/openapi.json').json()['openapi'] == '3.0.3'
