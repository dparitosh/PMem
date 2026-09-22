import pytest

from backend.ingestion_service.engineering_workflow import EngineeringWorkflow


class StubConverter:
    def convert(self, *, filename, content):
        return {
            "format": "EXPRESS", "source_kind": "schema", "statistics": {}, "next_action": "register",
            "ontology": {"name": "Demo", "prefix": "exp", "base_uri": "https://example.test/exp#", "turtle": "@prefix ex: <https://example.test/> ."},
        }


@pytest.mark.asyncio
async def test_engineering_workflow_can_return_conversion_without_cross_service_write():
    result = await EngineeringWorkflow(StubConverter()).run(filename="demo.exp", content=b"SCHEMA demo; END_SCHEMA;", register=False)
    assert result["status"] == "converted"
    assert result["conversion"]["format"] == "EXPRESS"


@pytest.mark.asyncio
async def test_engineering_publication_uses_the_private_graph_credential(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): return None
        def json(self): return self.payload

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            if url.endswith("/policies/evaluate"): return Response({"compliant": True})
            if url.endswith("/quality-gate"): return Response({"publish_recommended": True})
            if url.endswith("/register"): return Response({"ontology_id": "demo"})
            return Response({"status": "published"})

    monkeypatch.setenv("GRAPH_PUBLICATION_TOKEN", "private-graph-token")
    monkeypatch.setattr("backend.ingestion_service.engineering_workflow.httpx.AsyncClient", lambda **kwargs: Client())
    workflow = EngineeringWorkflow(StubConverter())
    workflow.ontology_url = "http://ontology/api/v1"
    workflow.graph_url = "http://graph/api/v1"

    result = await workflow.run(filename="demo.exp", content=b"SCHEMA demo; END_SCHEMA;", publish=True)

    assert result["status"] == "published"
    graph_call = next(call for call in calls if call[0].endswith("/graph/ontologies/publish"))
    assert graph_call[1]["headers"] == {"Authorization": "Bearer private-graph-token"}
