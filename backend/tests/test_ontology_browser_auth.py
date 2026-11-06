"""Real HTTP authorization boundary; synthetic artifacts, no graph or LLM calls."""
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from backend.ingestion_service.app import app
from backend.ingestion_service.api.ontology_browser import router


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('AUTH_MODE', 'token')
    monkeypatch.setenv('GRAPH_READ_TOKEN', 'fixture-read-key')
    monkeypatch.setenv('DEPO_CREDENTIAL_STORE', 'environment')
    monkeypatch.delenv('GRAPH_READ_TOKEN_EXPIRES_AT', raising=False)
    monkeypatch.delenv('DEPO_TOKEN_EXPIRES_AT', raising=False)
    return TestClient(app)


@pytest.mark.parametrize('route', router.routes)
@pytest.mark.parametrize('headers', [{}, {'Authorization': 'Bearer invalid'}])
def test_every_browser_route_requires_read_identity(client, route, headers):
    import re
    path = '/api/v1' + re.sub(r'\{[^}]+\}', 'fixture', route.path)
    method = next(iter(route.methods - {'HEAD', 'OPTIONS'}))
    response = client.request(method, path, headers=headers, json={} if method == 'POST' else None)
    assert response.status_code in (401, 403), response.text


def test_authorized_reasoning_and_inference_execute(client):
    headers = {'Authorization': 'Bearer fixture-read-key'}
    with patch('backend.ingestion_service.api.ontology_browser.OntologyTaxonomyService.get_reasoning', return_value={'status':'success'}) as call:
        assert client.get('/api/v1/ontology/fixture/reason', headers=headers).status_code == 200
        call.assert_called_once_with('fixture')
    with patch('backend.ingestion_service.api.ontology_browser._resolve_ontology_id', return_value='fixture'), patch('backend.ingestion_service.api.ontology_browser.OntologyReasoningService.preview_inferences', return_value={'inferences':[]}) as call:
        assert client.post('/api/v1/ontology/fixture/inference/preview', headers=headers, json={}).status_code == 200
        call.assert_called_once()


def test_export_requires_valid_unexpired_read_identity(client, monkeypatch, tmp_path):
    artifact = tmp_path / 'fixture.ttl'
    artifact.write_text('@prefix ex: <https://example.test/> . ex:Part ex:label "Part" .', encoding='utf-8')
    headers = {'Authorization': 'Bearer fixture-read-key'}
    with patch('backend.ingestion_service.api.ontology_browser.OntologyReasoningService.semantic_context', return_value={'file_path':artifact, 'meta':{}}):
        response = client.get('/api/v1/ontology/fixture/export?format=ttl', headers=headers)
        assert response.status_code == 200 and 'Part' in response.text
        assert 'attachment' in response.headers['content-disposition']
        monkeypatch.setenv('GRAPH_READ_TOKEN_EXPIRES_AT', '2000-01-01T00:00:00Z')
        assert client.get('/api/v1/ontology/fixture/export?format=ttl', headers=headers).status_code == 401
