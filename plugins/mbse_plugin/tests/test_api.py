import base64
import httpx
import pytest
from fastapi.testclient import TestClient
from mbse_plugin import app as module
from mbse_plugin.registration import register


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('MBSE_PLUGIN_TOKEN', 'test')
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
        return httpx.Response(status, json={'status': 'completed', 'preview': {'entities': [{'id': 'a'}], 'relationships': []}})
    monkeypatch.setattr(module.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    r = client.post('/imports', headers={'Authorization': 'Bearer test'}, json={'filename': 'a.xmi', 'profile': 'sysml-v1', 'content_base64': base64.b64encode(b'<model/>').decode()})
    assert r.status_code == status
    if status == 200:
        assert client.post('/visualization', headers={'Authorization': 'Bearer test'}, json=r.json()['preview']).status_code == 200


def test_registration_and_contract(client):
    class Host:
        def __init__(self): self.tools = {}
        def register_tool(self, name, function): self.tools[name] = function
    host = Host()
    register(host)
    assert set(host.tools) == {'mbse.import', 'mbse.visualize', 'smw.template', 'smw.preview', 'cameo.template', 'cameo.validate'}
    assert client.get('/tools').status_code == 401
    assert client.get('/openapi.json').json()['openapi'] == '3.0.3'
