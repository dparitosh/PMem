import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from FastAPIAdapter import depo_compat_router as adapter


ROOT = Path(__file__).resolve().parents[1]


def client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("DEPO_IIF_RUNTIME_ROOT", str(ROOT))
    monkeypatch.setenv("DEPO_IIF_UPLOAD_DIR", str(tmp_path / "uploads"))
    app = FastAPI()
    app.include_router(adapter.create_depo_compat_router())
    return TestClient(app)


def test_depo_catalog_contract(monkeypatch, tmp_path: Path):
    api = client(monkeypatch, tmp_path)
    health = api.get("/health")
    assert health.status_code == 200
    assert health.json()["agents"] == 4
    agents = api.get("/api/v1/agents").json()["agents"]
    tools = api.get("/api/v1/tools").json()
    assert len(agents) == 4
    assert len(tools["tools"]) == 8
    assert {"name", "category", "side_effect", "requires_approval"} <= tools["tools"][0].keys()


def test_openapi_import_is_inspection_only(monkeypatch, tmp_path: Path):
    api = client(monkeypatch, tmp_path)
    response = api.post(
        "/api/v1/openapi/import",
        json={
            "source_name": "sample.json",
            "document": {
                "openapi": "3.1.0",
                "info": {"title": "Sample", "version": "1"},
                "paths": {"/assets": {"get": {"operationId": "listAssets", "summary": "List assets"}}},
                "components": {"schemas": {"Asset": {"type": "object"}}},
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["summary"] == {"operations": 1, "schemas": 1}
    assert response.json()["dynamic_tools_created"] is False


def test_agent_and_workflow_execution_translate_to_iif(monkeypatch, tmp_path: Path):
    calls = []

    async def fake_execute(query, plan):
        calls.append((query, plan))
        return "done"

    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    (workflow_dir / "review.json").write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "agent": "Ontology Intake Agent",
                        "alias": "intake",
                        "purpose": "Inspect",
                        "inputs": ["User Query"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEPO_IIF_WORKFLOW_DIR", str(workflow_dir))
    monkeypatch.setattr(adapter, "_workflow_execute", fake_execute)
    api = client(monkeypatch, tmp_path)

    agent_response = api.post(
        "/api/v1/agents/Ontology%20Review%20Agent/run", json={"inputs": {"query": "Review", "path": "x.owl"}}
    )
    workflow_response = api.post(
        "/api/v1/workflows/run", json={"workflow_id": "review", "inputs": {"query": "Inspect"}}
    )
    assert agent_response.json()["result"] == "done"
    assert workflow_response.json()["result"] == "done"
    assert calls[0][1][0]["agent"] == "Ontology Review Agent"
    assert calls[1][1][0]["agent"] == "Ontology Intake Agent"


def test_ontology_upload_and_optional_security(monkeypatch, tmp_path: Path):
    api = client(monkeypatch, tmp_path)
    uploaded = api.post("/api/v1/ontology/files", files={"file": ("sample.ttl", b"@prefix ex: <urn:ex:> .", "text/turtle")})
    assert uploaded.status_code == 200
    assert Path(uploaded.json()["path"]).is_file()
    rejected = api.post("/api/v1/ontology/files", files={"file": ("sample.exe", b"bad", "application/octet-stream")})
    assert rejected.status_code == 400

    monkeypatch.setenv("DEPO_IIF_ADAPTER_SECURITY_ENABLED", "true")
    monkeypatch.setenv("DEPO_IIF_ADAPTER_TOKEN", "secret")
    secured = client(monkeypatch, tmp_path)
    assert secured.get("/health").status_code == 401
    assert secured.get("/health", headers={"Authorization": "Bearer secret"}).status_code == 200
