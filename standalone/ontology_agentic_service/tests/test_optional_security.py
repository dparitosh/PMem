from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from ontology_agentic.config import settings


TTL = """@prefix ex: <https://example.test/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
ex:Asset a owl:Class .
ex:code a owl:DatatypeProperty .
"""


def test_api_security_is_disabled_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_security_enabled", False)
    source = tmp_path / "source.ttl"
    source.write_text(TTL, encoding="utf-8")
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agents/ontology_intake_agent/run",
            json={"inputs": {"ontology_path": str(source)}},
        )
    assert response.status_code == 200


def test_enabled_security_requires_token_and_enforces_roots(tmp_path: Path, monkeypatch) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    source = allowed / "source.ttl"
    source.write_text(TTL, encoding="utf-8")
    outside_source = outside / "source.ttl"
    outside_source.write_text(TTL, encoding="utf-8")

    monkeypatch.setattr(settings, "api_security_enabled", True)
    monkeypatch.setattr(settings, "api_security_token", "test-token")
    monkeypatch.setattr(settings, "allowed_input_roots", [allowed.resolve()])
    monkeypatch.setattr(settings, "allowed_output_roots", [(allowed / "output").resolve()])

    with TestClient(app) as client:
        missing_token = client.post(
            "/api/v1/agents/ontology_intake_agent/run",
            json={"inputs": {"ontology_path": str(source)}},
        )
        allowed_response = client.post(
            "/api/v1/agents/ontology_intake_agent/run",
            headers={"Authorization": "Bearer test-token"},
            json={"inputs": {"ontology_path": str(source)}},
        )
        blocked_path = client.post(
            "/api/v1/agents/ontology_intake_agent/run",
            headers={"Authorization": "Bearer test-token"},
            json={"inputs": {"ontology_path": str(outside_source)}},
        )

    assert missing_token.status_code == 401
    assert allowed_response.status_code == 200
    assert blocked_path.status_code == 400
    assert "outside" in blocked_path.json()["detail"].lower()
