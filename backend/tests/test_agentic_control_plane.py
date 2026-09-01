from fastapi.testclient import TestClient
from backend.agentic_service.app import app
from backend.agentic_service.router import _multipart
import base64

def test_catalogue_is_manifest_driven_and_mutations_require_approval():
    client = TestClient(app)
    agents, tools, mcp = client.get("/api/v1/agents"), client.get("/api/v1/tools"), client.get("/api/v1/mcp-servers")
    assert any(item["id"] == "context-analyst" for item in agents.json()["agents"])
    assert any(item["id"] == "engineering.inspect" for item in tools.json()["tools"])
    assert mcp.json()["mcp_servers"][0]["id"] == "semantica"
    plan = client.post("/api/v1/plans", json={"agent_id": "ontology-governor", "tool_id": "ontology.merge.apply"})
    assert plan.status_code == 200 and plan.json()["requires_approval"] is True
    blocked = client.post("/api/v1/runs", json={"agent_id": "ontology-governor", "tool_id": "ontology.merge.apply", "inputs": {"preview_id": "x"}})
    assert blocked.status_code == 409

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
