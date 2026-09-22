import json
import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.agentic_service.app import app
from backend.agentic_service import router
from backend.agentic_service.configuration import SERVICE_KEYS, configuration_status
from backend.mesh_store import InMemoryRegistry


@pytest.fixture(autouse=True)
def isolated_environment():
    with patch.dict(os.environ, {'AUTH_MODE': 'token', 'GRAPH_READ_TOKEN': 'read-test',
                    'AGENTIC_APPROVAL_TOKEN': 'approve-test', 'GRAPH_SERVICE_URL': 'http://graph/api/v1'}, clear=True):
        yield


@pytest.fixture
def client():
    return TestClient(app)


READ = {'Authorization': 'Bearer read-test'}
APPROVAL = {'approved_by': 'reviewer', 'approval_token': 'approve-test'}


@pytest.mark.parametrize('method,path', [('POST', '/chat'), ('POST', '/chat/jobs'),
    ('POST', '/chat-stream'), ('POST', '/oslc/graph-rag'), ('GET', '/chat/jobs/known'),
    ('GET', '/workflow-runs/known'), ('GET', '/code-audit'), ('GET', '/catalog/validate')])
def test_anonymous_evidence_routes_denied(client, method, path):
    assert client.request(method, '/api/v1' + path, json={'message': 'test'}).status_code == 403


def test_sse_frames_and_session_header(client, monkeypatch):
    ask = AsyncMock(return_value={'response': 'hello', 'evidence': [], 'sources': [], 'answerable': True})
    monkeypatch.setattr(router.companion, 'ask', ask)
    response = client.post('/api/v1/chat-stream', json={'message': 'hello'}, headers=READ)
    assert response.status_code == 200
    frames = [json.loads(frame.removeprefix('data: ')) for frame in response.text.strip().split('\n\n')]
    assert frames[0] == {'token': 'hello'} and frames[-1] == {'done': True}
    assert response.headers['x-session-id']
    assert ask.call_args.kwargs['headers'] == READ


def mock_transport(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


def test_graph_dispatch_authenticates_both_hops(client, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        assert request.headers['authorization'] == 'Bearer read-test'
        return httpx.Response(200, json={'nodes': []})
    mock_transport(monkeypatch, handler)
    payload = {'agent_id': 'graph-analyst', 'tool_id': 'graph.analytics', 'inputs': {'ontology_id': 'one'}}
    assert client.post('/api/v1/runs', json=payload).status_code == 403
    assert not calls
    assert client.post('/api/v1/runs', json=payload, headers=READ).status_code == 200
    assert len(calls) == 1


def test_api_key_header_supports_read_and_approval(client, monkeypatch):
    ask = AsyncMock(return_value={'response': 'hello', 'evidence': [], 'sources': [], 'answerable': True})
    monkeypatch.setattr(router.companion, 'ask', ask)
    assert client.post('/api/v1/chat', json={'message': 'hello'}, headers={'X-API-Key': 'read-test'}).status_code == 200
    assert client.post('/api/v1/chat', json={'message': 'hello'}, headers={'X-API-Key': 'wrong'}).status_code == 403
    monkeypatch.setenv('DATA_PRODUCT_SERVICE_URL', 'http://products/api/v1')
    monkeypatch.setenv('DATA_PRODUCT_APPROVAL_TOKEN', 'product-test')
    def handler(request):
        assert json.loads(request.content)['approval_token'] == 'product-test'
        return httpx.Response(200, json={})
    mock_transport(monkeypatch, handler)
    payload = {'agent_id': 'data-product-governor', 'tool_id': 'data.product.publish', 'approved_by': 'reviewer'}
    assert client.post('/api/v1/runs', json=payload, headers={'X-API-Key': 'approve-test'}).status_code == 200
    assert client.post('/api/v1/runs', json={**payload, 'approval_token': '\u2603'}).status_code == 403


def test_ontology_registration_uses_artifact_upload_field(client, monkeypatch):
    import base64
    monkeypatch.setenv('ONTOLOGY_SERVICE_URL', 'http://ontology/api/v1')
    def handler(request):
        assert b'name="artifact"' in request.content
        assert b'name="file"' not in request.content
        return httpx.Response(200, json={'registered': True})
    mock_transport(monkeypatch, handler)
    payload = {'agent_id': 'ontology-governor', 'tool_id': 'ontology.register', **APPROVAL,
               'inputs': {'file': {'filename': 'test.ttl', 'content_base64': base64.b64encode(b'test').decode()},
                          'form': {'ontology_name': 'Test', 'prefix': 'test'}}}
    assert client.post('/api/v1/runs', json=payload).status_code == 200


def test_api_key_cors_preflight(client):
    response = client.options('/api/v1/chat', headers={'Origin': 'http://localhost:3000',
        'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'x-api-key,x-session-id'})
    assert response.status_code == 200


def test_step_approval_is_checked_before_store_or_dispatch(client, monkeypatch):
    catalog = {'agents': [{'id': 'reader', 'tools': ['read']}], 'tools': [
        {'id': 'read', 'transport': 'openapi', 'service': 'graph', 'method': 'GET', 'path': '/graph/overview'}],
        'workflows': [{'id': 'review-first', 'steps': [{'agent_id': 'reader', 'tool_id': 'read', 'approval_required': True}]}]}
    monkeypatch.setattr(router.catalog, 'read', lambda: catalog)
    store = InMemoryRegistry(); monkeypatch.setattr(router, 'workflow_store', store)
    calls = []
    def handler(request):
        calls.append(request); return httpx.Response(200, json={})
    mock_transport(monkeypatch, handler)
    assert client.post('/api/v1/workflow-runs', json={'workflow_id': 'review-first'}, headers=READ).status_code == 403
    assert not calls and not store.values
    assert client.post('/api/v1/workflow-runs', json={'workflow_id': 'review-first', **APPROVAL}, headers=READ).status_code == 200
    assert len(calls) == 1


def test_approved_dispatch_uses_destination_token_and_verified_actor(client, monkeypatch):
    monkeypatch.setenv('DATA_PRODUCT_SERVICE_URL', 'http://products/api/v1')
    monkeypatch.setenv('DATA_PRODUCT_APPROVAL_TOKEN', 'product-test')
    def handler(request):
        payload = json.loads(request.content)
        assert payload['approval_token'] == 'product-test'
        assert payload['approved_by'] == 'reviewer'
        return httpx.Response(200, json={'published': True})
    mock_transport(monkeypatch, handler)
    response = client.post('/api/v1/runs', json={'agent_id': 'data-product-governor', 'tool_id': 'data.product.publish',
        'inputs': {'approval_token': 'forged', 'approved_by': 'forged'}, **APPROVAL})
    assert response.status_code == 200
    assert 'product-test' not in response.text


def test_entra_revalidates_bearer_at_gateway_without_forwarding_identity_headers(client, monkeypatch):
    monkeypatch.setenv('AUTH_MODE', 'entra'); monkeypatch.setenv('DEPO_TRUSTED_GATEWAY_IPS', 'testclient')
    monkeypatch.setenv('GRAPH_SERVICE_URL', 'https://gateway.example/graph/api/v1')
    headers = {'Authorization': 'Bearer gateway-jwt', 'X-DEPO-Principal-Id': 'reader', 'X-DEPO-Roles': 'Graph.Reader'}
    def handler(request):
        assert request.headers['authorization'] == 'Bearer gateway-jwt'
        assert 'x-depo-principal-id' not in request.headers and 'x-depo-roles' not in request.headers
        return httpx.Response(200, json={})
    mock_transport(monkeypatch, handler)
    payload = {'agent_id': 'graph-analyst', 'tool_id': 'graph.analytics', 'inputs': {'ontology_id': 'one'}}
    assert client.post('/api/v1/runs', json=payload, headers=headers).status_code == 200
    monkeypatch.setenv('DEPO_TRUSTED_GATEWAY_IPS', 'another-host')
    assert client.post('/api/v1/runs', json=payload, headers=headers).status_code == 403
    monkeypatch.setenv('DEPO_TRUSTED_GATEWAY_IPS', 'testclient')
    monkeypatch.setenv('GRAPH_SERVICE_URL', 'http://graph/api/v1')
    assert client.post('/api/v1/runs', json=payload, headers=headers).status_code == 503


def valid_configuration(monkeypatch):
    for key in SERVICE_KEYS:
        monkeypatch.setenv(key, 'http://service/api/v1')
    for key in ('DEPO_DATABASE_URL', 'NEO4J_URI', 'NEO4J_USER', 'NEO4J_PASS', 'NEO4J_DATABASE',
                'ONTOLOGY_APPROVAL_TOKEN', 'DATA_PRODUCT_APPROVAL_TOKEN', 'DATA_JOB_EXECUTION_TOKEN', 'GRAPH_PUBLICATION_TOKEN'):
        monkeypatch.setenv(key, 'test-setting')


def test_missing_configuration_fails_readiness_but_not_liveness(client):
    assert client.get('/healthz').status_code == 200
    response = client.get('/readyz')
    assert response.status_code == 503
    assert 'DEPO_DATABASE_URL' in response.json()['dependencies']['configuration']['invalid_settings']
    assert 'read-test' not in response.text


def test_valid_configuration_and_optional_integrations(monkeypatch):
    valid_configuration(monkeypatch)
    assert configuration_status()['configuration']['status'] == 'ready'
    monkeypatch.setenv('DT_AGENT_ENABLED', 'true')
    assert 'DT_AGENT_GATEWAY_URL' in configuration_status()['configuration']['invalid_settings']
    monkeypatch.setenv('DT_AGENT_GATEWAY_URL', 'https://gateway.example/dt/api/v1')
    monkeypatch.setenv('DT_AGENT_GATEWAY_TOKEN', 'dt-test')
    assert configuration_status()['configuration']['status'] == 'ready'
    monkeypatch.setenv('AGENTIC_TOOL_TIMEOUT_SECONDS', 'nan')
    assert 'AGENTIC_TOOL_TIMEOUT_SECONDS' in configuration_status()['configuration']['invalid_settings']


def test_disabled_optional_integrations_reject_before_work(client, monkeypatch):
    assert client.post('/api/v1/oslc/graph-rag', json={'query': 'test'}, headers=READ).status_code == 503
    assert client.post('/api/v1/integrations/dt-requirements-design/runs', json=APPROVAL).status_code == 503
