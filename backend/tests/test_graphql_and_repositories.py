from fastapi.testclient import TestClient
import pytest

from backend.graph_service.app import app


@pytest.fixture(autouse=True)
def graph_reader(monkeypatch):
    monkeypatch.setattr("backend.graph_service.router.graph_read_identity", lambda request: "test-reader")
    monkeypatch.setattr("backend.graph_service.graphql_router.graph_read_identity", lambda request: "test-reader")
    monkeypatch.setattr("backend.graph_service.sparql_router.graph_read_identity", lambda request: "test-reader")
    monkeypatch.setattr("backend.graph_service.federation_router.graph_read_identity", lambda request: "test-reader")
    monkeypatch.setattr("backend.graph_service.federation_router.approval_identity", lambda *args, **kwargs: "test-approver")
    from backend.depo_platform.authorization import graph_read_identity
    app.dependency_overrides[graph_read_identity] = lambda: "test-reader"
    yield
    app.dependency_overrides.clear()


def test_graphql_is_read_only_and_uses_bounded_graph_projections(monkeypatch):
    monkeypatch.setattr("backend.graph_service.graphql_schema.publisher.overview", lambda *, limit: {"counts": {"nodes": limit}})
    client = TestClient(app)

    response = client.post("/api/v1/graphql", json={"query": "{ overview(limit: 7) }"})

    assert response.status_code == 200
    assert response.json()["data"]["overview"]["counts"]["nodes"] == 7
    mutation = client.post("/api/v1/graphql", json={"query": "mutation { publish }"})
    assert mutation.status_code == 400


def test_graphql_rejects_alias_fanout_before_resolvers_run(monkeypatch):
    calls = []
    monkeypatch.setattr("backend.graph_service.graphql_schema.publisher.overview", lambda **_: calls.append(1))
    query = "{ " + " ".join(f"n{i}: overview" for i in range(26)) + " }"
    response = TestClient(app).post("/api/v1/graphql", json={"query": query})
    assert response.status_code == 422
    assert not calls


def test_graphql_exposes_control_plane_read_models_without_submitting_spark_work(monkeypatch):
    monkeypatch.setattr(
        "backend.graph_service.graphql_schema.control_plane_client.job_runs",
        lambda limit: {"runs": [{"run_id": "run-1", "status": "completed", "limit": limit}]},
    )
    monkeypatch.setattr(
        "backend.graph_service.graphql_schema.control_plane_client.data_product_manifest",
        lambda product_version: {"product_version": product_version, "validation_status": "accepted"},
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/graphql",
        json={"query": '{ dataJobRuns(limit: 7) dataProductManifest(productVersion: "motor:1.0") }'},
    )

    assert response.status_code == 200
    assert response.json()["data"]["dataJobRuns"]["runs"][0]["limit"] == 7
    assert response.json()["data"]["dataProductManifest"]["validation_status"] == "accepted"


def test_graph_query_repository_is_parameterized():
    from backend.graph_service import query_repository

    assert "$ontology_id" in query_repository.ONTOLOGY_PROJECTION_NODES
    assert "$iri" in query_repository.ONTOLOGY_TRAVERSAL_NODES
    assert "$terms" in query_repository.ONTOLOGY_SEARCH_NODES
    assert "RETURN n.iri" in query_repository.ONTOLOGY_SEARCH_NODES


def test_graph_search_uses_bounded_terms_and_preserves_score(monkeypatch):
    from backend.graph_service.neo4j_publisher import publisher

    calls = []
    def rows(query, **parameters):
        calls.append(parameters)
        if "terms" in parameters:
            return [{"id": "urn:product", "label": "Product", "type": "class", "ontology_id": "skos-engineering", "score": 5}]
        return []
    monkeypatch.setattr(publisher, "_session_rows", rows)
    response = TestClient(app).get("/api/v1/graph/search", params={"query": "Show Product relationships", "limit": 5000})
    assert response.status_code == 200
    assert calls[0]["terms"] == ["product"]
    assert calls[0]["limit"] == 200
    assert response.json()["nodes"][0]["properties"]["search_score"] == 5


def test_sparql_is_bounded_read_only_and_returns_projection_evidence(monkeypatch):
    monkeypatch.setattr("backend.graph_service.sparql_service.publisher.projection", lambda *, ontology_id, limit: {
        "ontology_id": ontology_id, "truncated": False,
        "nodes": [{"id": "urn:product", "label": "Product", "type": "class"}],
        "edges": [],
    })
    client = TestClient(app)
    response = client.post("/api/v1/sparql", json={"ontology_id": "engineering", "query": "SELECT ?s ?label WHERE { ?s <http://www.w3.org/2000/01/rdf-schema#label> ?label }", "limit": 5})
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["results"]["bindings"][0]["s"]["value"] == "urn:product"
    assert response.json()["evidence"]["ontology_id"] == "engineering"
    blocked = client.post("/api/v1/sparql", json={"ontology_id": "engineering", "query": "SELECT * WHERE { SERVICE <https://untrusted.test/sparql> { ?s ?p ?o } }"})
    assert blocked.status_code == 422


def test_federation_requires_approved_https_peer_and_never_forwards_service(monkeypatch):
    from backend.graph_service import federation_service
    from backend.mesh_store import InMemoryRegistry
    import httpx

    monkeypatch.setattr(federation_service, "peers", InMemoryRegistry())
    client = TestClient(app)
    rejected = client.post("/api/v1/sparql/federation/peers", json={"peer_id": "bad-peer", "endpoint": "http://untrusted.example"})
    assert rejected.status_code == 422
    created = client.post("/api/v1/sparql/federation/peers", json={"peer_id": "trusted-peer", "endpoint": "https://peer.example", "ontology_allowlist": ["engineering"]})
    assert created.status_code == 201
    assert client.post("/api/v1/sparql/federation/peers/trusted-peer/approve", json={}).status_code == 200

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs): return httpx.Response(200, request=httpx.Request("POST", url), json={"count": 1})
    monkeypatch.setattr(federation_service.httpx, "AsyncClient", FakeClient)
    response = client.post("/api/v1/sparql/federation/peers/trusted-peer/query", json={"ontology_id": "engineering", "query": "SELECT ?s WHERE { ?s ?p ?o }"})
    assert response.status_code == 200
    blocked = client.post("/api/v1/sparql/federation/peers/trusted-peer/query", json={"ontology_id": "engineering", "query": "SELECT * WHERE { SERVICE <https://bad> { ?s ?p ?o } }"})
    assert blocked.status_code == 422
