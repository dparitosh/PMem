from fastapi.testclient import TestClient

from app.main import app


def test_owlready2_endpoint_is_registered() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ontology/owlready2",
            json={"path": "D:/missing.owl", "run_reasoner": False},
        )
    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()


def test_owlready2_endpoint_rejects_string_boolean() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ontology/owlready2",
            json={"path": "D:/missing.owl", "run_reasoner": "false"},
        )
    assert response.status_code == 422
