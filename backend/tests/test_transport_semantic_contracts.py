"""Executed transport boundaries and honest semantic capability contracts."""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.depo_platform.service_runtime import create_service_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('ALLOWED_ORIGINS', 'http://localhost:3000,https://customer.example:2200')
    app = create_service_app(title='Transport fixture', version='1', dependencies=())

    @app.get('/registry')
    def registry():
        raise HTTPException(503, 'Registry temporarily unavailable')

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize('origin', ['http://localhost:3000', 'https://customer.example:2200'])
def test_every_configured_origin_supports_authenticated_preflight_and_errors(client, origin):
    response = client.options('/registry', headers={
        'Origin':origin, 'Access-Control-Request-Method':'POST',
        'Access-Control-Request-Headers':'authorization,content-type,x-api-key,x-request-id'})
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == origin
    assert 'access-control-allow-credentials' not in response.headers
    failed = client.get('/registry', headers={'Origin':origin, 'X-Request-ID':'registry-fixture'})
    assert failed.status_code == 503
    assert failed.headers['access-control-allow-origin'] == origin
    assert failed.headers['x-request-id'] == 'registry-fixture'
    assert 'X-Request-ID' in failed.headers['access-control-expose-headers']


@pytest.mark.parametrize('origin', ['https://untrusted.example', 'null', 'http://localhost:3001'])
def test_unlisted_browser_origins_cannot_read_service_responses(client, origin):
    response = client.options('/registry', headers={'Origin':origin, 'Access-Control-Request-Method':'POST'})
    assert response.status_code == 400
    assert 'access-control-allow-origin' not in response.headers


def test_semantic_capabilities_do_not_advertise_dl_consistency():
    from backend.ontology_service.semantica_adapter import SemanticaAdapter
    # Capability inspection must not require constructing a database workspace.
    result = SemanticaAdapter.capabilities(None)
    assert result['rdf_backend'] == 'rdflib'
    assert result['validation_scope'] == 'structural_and_shacl'
    assert result['semantica_builtin_owl_dl_supported'] is False
    assert result['owl_dl_consistency_supported'] is result['external_owl_dl']['available']


def test_structural_validation_does_not_certify_a_logically_inconsistent_abox(tmp_path):
    from backend.Services.ontology_semantic_runtime import OntologySemanticRuntime
    source = tmp_path / 'inconsistent.ttl'
    source.write_text('''@prefix owl:<http://www.w3.org/2002/07/owl#> .
        <urn:Part> a owl:Class ; owl:disjointWith <urn:Process> .
        <urn:Process> a owl:Class . <urn:item> a <urn:Part>, <urn:Process> .''')
    result = OntologySemanticRuntime.inspect_ontology(source)
    assert result['status'] == 'success'
    assert result['structural_validation']['scope'] == 'structure_only'
    assert result['consistency_verified'] is False
    assert result['deductive_reasoner_executed'] is False
