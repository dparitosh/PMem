"""Graph REST authorization contract tests."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.graph_service.router import router


def test_rest_graph_reads_require_credentials(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv("GRAPH_READ_TOKEN", "test-read-secret")
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    for path in ["/graph/overview", "/graph/search?query=part", "/graph/ontologies/test/projection", "/graph/traversal/urn:part", "/graph/ontologies/test/analytics", "/graph/ontologies/test/neighborhood?iri=urn:part"]:
        assert client.get(path).status_code == 403


def test_authorized_read_reaches_publisher(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv("GRAPH_READ_TOKEN", "test-read-secret")
    monkeypatch.setattr("backend.graph_service.router.publisher.overview", lambda **kwargs: {"nodes": []})
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get("/graph/overview", headers={"Authorization": "Bearer test-read-secret"})
    assert response.status_code == 200
