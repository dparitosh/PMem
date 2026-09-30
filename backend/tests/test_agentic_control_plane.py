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
    candidates = body["steps"][2]["result"]["alignment_candidates"]
    assert any(row["source"] == "Motor" and row["target_iri"] == "https://example.test/Motor"
               and row["status"] == "review_required" for row in candidates)
    assert any(row["source"] == "hasPart" and row["target_type"] == "ObjectProperty" for row in candidates)


def test_ontology_orchestrator_reuses_one_artifact_snapshot(monkeypatch):
    from backend.agentic_service import ontology_orchestrator as agents
    summary = {"classes": 1, "object_properties": 1, "datatype_properties": 0,
               "domain_edges": 1, "range_edges": 1, "individuals": 0}
    calls = []
    monkeypatch.setattr(agents, "_resolve_ontology_path", lambda path, ontology_id: "sample.ttl")
    def inspect(path):
        calls.append(path)
        return summary
    monkeypatch.setattr(agents, "inspect_ontology", inspect)
    result = agents.orchestrate({"ontology_path": "sample.ttl", "instance_metadata": {}})
    assert calls == ["sample.ttl"]
    assert result["steps"][0]["result"] is result["steps"][1]["result"]["summary"]
    assert result["steps"][0]["result"] is result["steps"][2]["result"]["ontology_summary"]


def test_ontology_agent_rejects_invalid_supplied_metadata_even_with_import_task():
    from backend.agentic_service.ontology_orchestrator import _instance_metadata
    import pytest
    with pytest.raises(ValueError, match="instance_metadata must be an object"):
        _instance_metadata("task-1", ["invalid"])
    assert _instance_metadata("task-1", {}) == {}


def test_ontology_agent_uses_generated_rdf_for_non_rdf_upload(monkeypatch):
    from backend.agentic_service import ontology_orchestrator as agents
    from backend.Services.ontology_upload_manager import OntologyUploadManager
    monkeypatch.setattr(OntologyUploadManager, "get_ontology", lambda ontology_id: {
        "status": "success", "metadata": {
            "file_path": "data/schema.xsd", "owl_file_path": "data/schema.generated.ttl"}})
    assert agents._resolve_ontology_path("", "schema") == "data/schema.generated.ttl"


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
