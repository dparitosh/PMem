from fastapi.testclient import TestClient

from backend.ontology_service.app import app


def test_standard_service_liveness_and_readiness_contracts():
    client = TestClient(app)
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/readyz").json()["status"] == "ready"


def test_readiness_fails_when_a_configured_dependency_is_unavailable(monkeypatch):
    monkeypatch.setenv("DEPO_DATABASE_URL", "postgresql://127.0.0.1:1/not-running")
    response = TestClient(app).get("/readyz")
    assert response.status_code == 503
    assert response.json()["dependencies"]["postgres"]["status"] == "unavailable"
