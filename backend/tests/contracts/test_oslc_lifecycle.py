from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.oslc_service import lifecycle
from backend.oslc_service.client import OSLCClient


def test_lifecycle_paging_shape_and_conditional_read(monkeypatch):
    monkeypatch.setenv("OSLC_LIFECYCLE_READ_GRANTS", '{"test":["job-runs:*"]}')
    monkeypatch.setenv("OSLC_ENABLED", "true")
    monkeypatch.setattr(lifecycle.OSLCService, "is_enabled", lambda: True)
    monkeypatch.setattr(lifecycle.PostgresRegistry, "page_keys", lambda self, offset, limit: (2, ["a"]))
    monkeypatch.setattr(lifecycle.PostgresRegistry, "get", lambda self, key: {"status": "accepted"})
    app = FastAPI()
    app.include_router(lifecycle.router)
    app.dependency_overrides[lifecycle.graph_read_identity] = lambda: "test"
    client = TestClient(app)
    result = client.get("/oslc/lifecycle/job-runs?page_size=1")
    assert len(result.json()["members"]) == 1
    assert result.json()["nextPage"]
    assert client.get("/oslc/lifecycle/shapes/job-runs").json()["properties"][0]["readOnly"]
    resource = client.get("/oslc/lifecycle/job-runs/a")
    assert resource.status_code == 200
    assert client.get("/oslc/lifecycle/job-runs/a", headers={"If-None-Match": resource.headers["etag"]}).status_code == 304
    assert client.get("/oslc/lifecycle/job-runs?page_size=1000").status_code == 400
    from rdflib import Graph
    for media, format in [("text/turtle", "turtle"), ("application/rdf+xml", "xml"), ("application/ld+json", "json-ld")]:
        response = client.get("/oslc/lifecycle/job-runs/a", headers={"Accept": media})
        assert response.status_code == 200
        assert len(Graph().parse(data=response.text, format=format)) == 3
    assert client.get("/oslc/lifecycle/job-runs/a", headers={"Accept": "image/png"}).status_code == 406
    assert client.get("/oslc/lifecycle/products").status_code == 403
    monkeypatch.setenv("OSLC_LIFECYCLE_READ_GRANTS", '{"test":["job-runs:a"]}')
    assert client.get("/oslc/lifecycle/job-runs").status_code == 403
    assert client.get("/oslc/lifecycle/job-runs/b").status_code == 403
    assert client.get("/oslc/lifecycle/job-runs/a").status_code == 200


def test_client_accepts_bounded_ontology_resource_type(monkeypatch):
    client = OSLCClient()
    monkeypatch.setattr(client, "_request", lambda path, params: path)
    assert client.query("ontology:ap242-v1", {}) == "oslc/query/ontology:ap242-v1"
