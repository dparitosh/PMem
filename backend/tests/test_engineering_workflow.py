import pytest

from backend.ingestion_service.engineering_workflow import EngineeringWorkflow, EngineeringDependencyFailure
import httpx


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
async def test_engineering_workflow_passes_xsd_dependencies_to_existing_converter():
    seen = {}
    class Converter:
        def convert(self, **kwargs):
            seen.update(kwargs)
            return {'ontology': {'turtle': ''}}
    dependencies = {'types/part.xsd': b'part'}
    result = await EngineeringWorkflow(Converter()).run(filename='main.xsd', content=b'root',
        schema_files=dependencies, register=False)
    assert result['status'] == 'converted'
    assert seen['schema_files'] == dependencies


@pytest.mark.asyncio
async def test_downstream_timeout_retains_stage_without_credentials(caplog):
    class Client:
        async def post(self, url, **kwargs):
            raise httpx.ReadTimeout('upstream body and credential must not be logged')
    with pytest.raises(EngineeringDependencyFailure) as failure:
        await EngineeringWorkflow._request(Client(), 'quality_gate', 'test-request', 'http://ontology/quality')
    assert failure.value.stage == 'quality_gate'
    assert failure.value.failure_kind == 'upstream_timeout'
    assert 'stage=quality_gate' in caplog.text
    assert 'upstream body and credential' not in caplog.text


@pytest.mark.asyncio
async def test_downstream_http_failure_retains_status():
    class Client:
        async def post(self, url, **kwargs):
            return httpx.Response(403, request=httpx.Request('POST', url))
    with pytest.raises(EngineeringDependencyFailure) as failure:
        await EngineeringWorkflow._request(Client(), 'ontology_registration', None, 'http://ontology/register')
    assert failure.value.stage == 'ontology_registration'
    assert failure.value.upstream_status == 403


@pytest.mark.asyncio
async def test_engineering_publication_delegates_to_locked_ontology_service(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload, status_code=200): self.payload = payload; self.status_code = status_code
        def raise_for_status(self): return None
        def json(self): return self.payload

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def get(self, url, **kwargs):
            assert kwargs["headers"]["Authorization"] == "Bearer private-read-token"
            return Response({"lifecycle_status": "approved", "status": "registered"})
        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            if url.endswith("/policies/evaluate"): return Response({"compliant": True})
            if url.endswith("/quality-gate"): return Response({"publish_recommended": True})
            if url.endswith("/register"): return Response({"ontology_id": "demo"})
            return Response({"status": "queued", "ontology_id": "demo", "job_id": "durable-job"}, 202)

    monkeypatch.setenv("GRAPH_READ_TOKEN", "private-read-token")
    monkeypatch.setenv("ONTOLOGY_APPROVAL_TOKEN", "private-ontology-token")
    monkeypatch.setattr("backend.ingestion_service.engineering_workflow.httpx.AsyncClient", lambda **kwargs: Client())
    workflow = EngineeringWorkflow(StubConverter())
    workflow.ontology_url = "http://ontology/api/v1"
    workflow.graph_url = "http://graph/api/v1"

    result = await workflow.run(filename="demo.exp", content=b"SCHEMA demo; END_SCHEMA;", publish=True)

    assert result["status"] == "publication_queued"
    assert result["publication_job"]["job_id"] == "durable-job"
    publication_call = next(call for call in calls if call[0].endswith("/ontologies/demo/publish"))
    assert publication_call[1]["json"] == {"approved_by": "engineering-ingestion"}
    assert publication_call[1]["params"] == {"background": True}
    assert all(not url.startswith("http://graph/") for url, _ in calls)


@pytest.mark.parametrize("state", ["draft", "in_review", "retired", "deprecated"])
def test_publication_requires_approved_lifecycle(state):
    with pytest.raises(ValueError):
        EngineeringWorkflow._require_publishable({"lifecycle_status": state})
