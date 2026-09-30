from fastapi.testclient import TestClient

from backend.depo_platform.service_runtime import create_service_app
from backend.ingestion_service.app import app as ingestion_app
from backend.ontology_service.app import app as ontology_app
from backend.qif.app import app as qif_app


def test_shared_cors_allows_declared_mutation_methods():
    client = TestClient(create_service_app(title="cors-test", version="1"))
    for method in ("PUT", "PATCH", "DELETE"):
        response = client.options(
            "/resource",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": method},
        )
        assert response.status_code == 200
        assert method in response.headers["access-control-allow-methods"]


def test_qif_write_rejects_missing_token(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv("ONTOLOGY_APPROVAL_TOKEN", "ontology-secret")
    response = TestClient(qif_app).post("/api/v1/qif/agents/refresh")
    assert response.status_code == 403


def test_modeling_and_metadata_writes_reject_missing_token(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv("ONTOLOGY_APPROVAL_TOKEN", "ontology-secret")
    client = TestClient(ontology_app)
    assert client.post("/api/v1/modeling/indexes").status_code == 403
    assert client.post("/api/v1/metadata-registry/assets", json={}).status_code == 403


def test_modeling_reads_require_graph_read_token(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv("GRAPH_READ_TOKEN", "graph-read-secret")
    client = TestClient(ontology_app)
    assert client.get("/api/v1/modeling/graph").status_code == 403
    # The metamodel is static and exercises the authenticated GET path without
    # requiring a live graph database.
    assert client.get("/api/v1/modeling/metamodel", headers={"Authorization": "Bearer graph-read-secret"}).status_code == 200


def test_ingestion_write_rejects_missing_token(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv("INGESTION_WRITE_TOKEN", "ingestion-secret")
    response = TestClient(ingestion_app).post("/api/v1/source-profiles", json={})
    assert response.status_code == 403
