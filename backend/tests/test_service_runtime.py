from fastapi.testclient import TestClient

from backend.ontology_service.app import app


def test_standard_service_liveness_and_readiness_contracts():
    client = TestClient(app)
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/readyz").json()["status"] == "ready"
