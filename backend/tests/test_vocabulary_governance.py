from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.artifact_store import ArtifactStore
from backend.mesh_store import InMemoryRegistry
from backend.ontology_service.app import app
from backend.ontology_service import vocabulary_service


@pytest.fixture(autouse=True)
def steward_identity(monkeypatch):
    monkeypatch.setattr("backend.ontology_service.router.approval_identity", lambda request, payload, token_env: str(payload.get("approved_by") or "test-steward"))


def _payload() -> dict:
    return {
        "approved_by": "vocabulary-steward",
        "scheme": {"scheme_id": "engineering-terms", "pref_label": "Engineering terms", "definition": "Governed engineering terminology", "version": "1.0.0"},
        "base_uri": "https://example.test/vocabulary/engineering/",
        "steward": "engineering-governance",
        "provenance": {"source": "approved-domain-workshop", "rationale": "Establish controlled lifecycle terminology"},
        "concepts": [
            {"concept_id": "product", "pref_label": "Product", "definition": "An engineered deliverable", "narrower": ["part"], "mappings": {"exactMatch": ["https://example.test/ceim/Product"]}},
            {"concept_id": "part", "pref_label": "Part", "alt_labels": ["Component"], "definition": "A constituent product", "broader": ["product"]},
        ],
    }


def test_vocabulary_requires_validation_and_steward_lifecycle(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "disabled")
    monkeypatch.setenv("DEPO_ALLOW_INSECURE_LOCAL_AUTH", "true")
    vocabulary_service.vocabularies.store = InMemoryRegistry()
    vocabulary_service.vocabularies.artifacts = ArtifactStore(tmp_path / "artifacts")
    client = TestClient(app)

    created = client.post("/api/v1/ontologies/vocabularies", json=_payload())
    assert created.status_code == 201
    assert created.json()["validation"]["valid"] is True
    assert created.json()["lifecycle_status"] == "draft"

    reviewed = client.post("/api/v1/ontologies/vocabularies/engineering-terms/1.0.0/transition", json={"approved_by": "reviewer", "target": "in_review", "reason": "Domain review started"})
    assert reviewed.status_code == 200
    approved = client.post("/api/v1/ontologies/vocabularies/engineering-terms/1.0.0/transition", json={"approved_by": "approver", "target": "approved", "reason": "Labels and mappings approved"})
    assert approved.status_code == 200
    assert approved.json()["lifecycle_status"] == "approved"
    assert len(approved.json()["history"]) == 3


def test_vocabulary_rejects_duplicate_labels(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "disabled")
    monkeypatch.setenv("DEPO_ALLOW_INSECURE_LOCAL_AUTH", "true")
    vocabulary_service.vocabularies.store = InMemoryRegistry()
    payload = _payload()
    payload["concepts"][1]["alt_labels"] = ["Product"]
    response = TestClient(app).post("/api/v1/ontologies/vocabularies", json=payload)
    assert response.status_code == 422
    assert "duplicate_label" in response.json()["detail"]


def test_only_approved_vocabulary_publishes_through_graph_boundary(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "disabled")
    monkeypatch.setenv("DEPO_ALLOW_INSECURE_LOCAL_AUTH", "true")
    vocabulary_service.vocabularies.store = InMemoryRegistry()
    vocabulary_service.vocabularies.artifacts = ArtifactStore(tmp_path / "artifacts")
    client = TestClient(app)
    client.post("/api/v1/ontologies/vocabularies", json=_payload())
    blocked = client.post("/api/v1/ontologies/vocabularies/engineering-terms/1.0.0/publish", json={"approved_by": "approver"})
    assert blocked.status_code == 409
    client.post("/api/v1/ontologies/vocabularies/engineering-terms/1.0.0/transition", json={"approved_by": "reviewer", "target": "in_review", "reason": "Reviewed"})
    client.post("/api/v1/ontologies/vocabularies/engineering-terms/1.0.0/transition", json={"approved_by": "approver", "target": "approved", "reason": "Approved"})

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            return httpx.Response(200, request=httpx.Request("POST", url), json={"status": "success", "resources": 3, "relationships": 4})

    monkeypatch.setattr("backend.ontology_service.router.httpx.AsyncClient", FakeClient)
    published = client.post("/api/v1/ontologies/vocabularies/engineering-terms/1.0.0/publish", json={"approved_by": "approver"})
    assert published.status_code == 200
    assert published.json()["publication_status"] == "published"
    assert published.json()["artifact_id"].startswith("sha256:")
