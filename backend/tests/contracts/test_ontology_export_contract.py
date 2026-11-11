"""Ontology export serialization contract tests."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from rdflib import Graph
from backend.ingestion_service.api.ontology_browser import router


@pytest.mark.parametrize("format,syntax", [("ttl", "turtle"), ("rdf", "xml"), ("owl", "xml"), ("jsonld", "json-ld")])
def test_exports_preserve_triples(tmp_path, monkeypatch, format, syntax):
    monkeypatch.setenv('AUTH_MODE', 'token')
    monkeypatch.setenv('DEPO_CREDENTIAL_STORE', 'environment')
    monkeypatch.setenv('GRAPH_READ_TOKEN', 'fixture-export-key')
    monkeypatch.delenv('GRAPH_READ_TOKEN_EXPIRES_AT', raising=False)
    monkeypatch.delenv('DEPO_TOKEN_EXPIRES_AT', raising=False)
    path = tmp_path / "ontology.ttl"
    path.write_text('<urn:part> <urn:name> "Part" .', encoding="utf-8")
    monkeypatch.setattr("backend.ingestion_service.api.ontology_browser.OntologyReasoningService.semantic_context", lambda _: {"file_path": path})
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get(f"/ontology/test/export?format={format}", headers={'Authorization':'Bearer fixture-export-key'})
    assert response.status_code == 200
    assert len(Graph().parse(data=response.content, format=syntax)) == 1
