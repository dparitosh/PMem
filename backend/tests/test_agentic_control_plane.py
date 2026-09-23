from fastapi.testclient import TestClient
from backend.agentic_service.app import app
from backend.agentic_service.router import _multipart
import base64
from pathlib import Path

def test_catalogue_is_manifest_driven_and_mutations_require_approval():
    client = TestClient(app)
    agents, tools, mcp = client.get("/api/v1/agents"), client.get("/api/v1/tools"), client.get("/api/v1/mcp-servers")
    assert any(item["id"] == "context-analyst" for item in agents.json()["agents"])
    assert any(item["id"] == "engineering.inspect" for item in tools.json()["tools"])
    assert mcp.json()["mcp_servers"][0]["id"] == "semantica"
    plan = client.post("/api/v1/plans", json={"agent_id": "ontology-governor", "tool_id": "ontology.merge.apply"})
    assert plan.status_code == 200 and plan.json()["requires_approval"] is True
    blocked = client.post("/api/v1/runs", json={"agent_id": "ontology-governor", "tool_id": "ontology.merge.apply", "inputs": {"preview_id": "x"}})
    assert blocked.status_code == 403

def test_workflow_manifest_validates_steps_and_multipart_is_bounded():
    client = TestClient(app)
    workflow = client.post("/api/v1/workflow-plans", json={"workflow_id": "engineering-governed-publish"})
    assert workflow.status_code == 200
    assert workflow.json()["steps"][1]["requires_approval"] is True
    form, files = _multipart({"file": {"filename": "part.step", "content_base64": base64.b64encode(b"ISO-10303-21;").decode("ascii")}, "form": {"publish": "false"}})
    assert form["publish"] == "false" and files["file"][0] == "part.step"

def test_tool_is_rejected_when_not_allowlisted_for_agent():
    client = TestClient(app)
    response = client.post("/api/v1/plans", json={"agent_id": "ontology-intake", "tool_id": "context.upsert"})
    assert response.status_code == 422


def test_ontology_agent_orchestrator_returns_reviewable_bridge_plan(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv("GRAPH_READ_TOKEN", "read-test")
    ontology = tmp_path / "sample.ttl"
    ontology.write_text(
        "@prefix ex: <https://example.test/> .\n"
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "ex:Motor a owl:Class .\n"
        "ex:hasPart a owl:ObjectProperty ; rdfs:domain ex:Motor ; rdfs:range ex:Motor .\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ONTOLOGY_AGENT_ALLOWED_ROOTS", str(tmp_path))
    response = TestClient(app).post(
        "/api/v1/ontology-agents/orchestrate",
        headers={"Authorization": "Bearer read-test"},
        json={
            "workflow_id": "ontology_review",
            "ontology_path": str(ontology),
            "instance_metadata": {"entities": ["Motor"], "relationships": ["hasPart"]},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["publication"] == "requires_human_approval"
    assert body["steps"][0]["result"]["classes"] == 1
    assert body["steps"][2]["result"]["alignment_plan"]["relationship_to_objectproperty"] == 1


def test_companion_returns_bounded_graph_evidence(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv("GRAPH_READ_TOKEN", "read-test")
    async def grounded(message, **kwargs):
        return {"status": "grounded", "answerable": True, "response": "Grounded graph matches: Product.", "evidence": [{"evidence_type": "graph_resource", "resource_id": "urn:product", "label": "Product", "source": "graph"}], "sources": ["graph"], "retrieval": {"nodes_examined": 1, "relationships_examined": 0, "truncated": False}}
    monkeypatch.setattr("backend.agentic_service.router.companion.ask", grounded)
    response = TestClient(app).post("/api/v1/chat", json={"message": "Show product"}, headers={"Authorization": "Bearer read-test"})
    assert response.status_code == 200
    assert response.json()["answerable"] is True
    assert response.json()["evidence"][0]["resource_id"] == "urn:product"


def test_companion_fails_closed_when_graph_is_unavailable(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "token")
    monkeypatch.setenv("GRAPH_READ_TOKEN", "read-test")
    async def unavailable(message, **kwargs):
        raise RuntimeError("Knowledge graph retrieval is unavailable; no answer was generated")
    monkeypatch.setattr("backend.agentic_service.router.companion.ask", unavailable)
    response = TestClient(app).post("/api/v1/chat", json={"message": "Invent an answer"}, headers={"Authorization": "Bearer read-test"})
    assert response.status_code == 503
    assert "no answer was generated" in response.json()["detail"]
