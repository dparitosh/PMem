import pytest

from backend.ingestion_service.workflow import SemanticIngestionWorkflow


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _Client:
    def __init__(self, *args, **kwargs):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/ontologies/quality-gate"):
            return _Response({"publish_recommended": True, "duplicates": [], "conflicts": []})
        if url.endswith("/ontologies/generate"):
            return _Response({"version_id": "parts:1", "artifacts": {"turtle": "@prefix ex: <urn:ex:> ."}})
        return _Response({"status": "success", "resources": 2})


@pytest.mark.asyncio
async def test_workflow_generates_and_optionally_publishes(monkeypatch):
    client = _Client()
    monkeypatch.setattr("backend.ingestion_service.workflow.httpx.AsyncClient", lambda **kwargs: client)
    runner = SemanticIngestionWorkflow()
    runner.ontology_url, runner.graph_url = "http://ontology/api/v1", "http://graph/api/v1"
    normalized = {"entities": [{"id": "P-1", "type": "Part"}], "relationships": [], "records_processed": 1, "provenance": {"profile_id": "parts"}}

    result = await runner.run(normalized=normalized, name="Parts", prefix="parts", base_uri="urn:parts", publish=True)

    assert result["status"] == "published"
    assert result["graph_publication"]["resources"] == 2
    assert [call[0] for call in client.calls] == ["http://ontology/api/v1/ontologies/quality-gate", "http://ontology/api/v1/ontologies/generate", "http://graph/api/v1/graph/ontologies/publish"]


@pytest.mark.asyncio
async def test_workflow_blocks_unapproved_publication(monkeypatch):
    class _BlockedClient(_Client):
        async def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return _Response({"publish_recommended": False, "duplicates": [{"id": "duplicate"}]})

    client = _BlockedClient()
    monkeypatch.setattr("backend.ingestion_service.workflow.httpx.AsyncClient", lambda **kwargs: client)
    runner = SemanticIngestionWorkflow()
    result = await runner.run(
        normalized={"entities": [{"id": "P-1", "type": "Part"}], "relationships": [], "records_processed": 1, "provenance": {}},
        name="Parts", prefix="parts", base_uri="urn:parts", publish=True,
    )

    assert result["status"] == "quality_blocked"
    assert len(client.calls) == 1
