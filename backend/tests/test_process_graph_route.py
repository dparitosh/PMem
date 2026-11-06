"""Exercise the deployed graph route, including errors and authorization."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.graph_service.router import router, graph_read_identity
from backend.Services.graph_view_service import GraphViewService


def client():
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    app.dependency_overrides[graph_read_identity] = lambda: 'fixture-reader'
    return TestClient(app)


def test_process_route_returns_imported_instances_without_ontology_registration(monkeypatch):
    calls = []
    def rows(query, params):
        calls.append(params)
        return [{'n':{'elementId':'process-1', 'labels':['BusinessProcess'],
                      'properties':{'name':'Manufacture', 'source_format':'archimate', 'ontology_prefix':'archimate'}},
                 'r':None, 'm':None}]
    monkeypatch.setattr(GraphViewService, '_run', staticmethod(rows))
    response = client().get('/api/v1/graph/view/architecture/archimate?limit=30')
    assert response.status_code == 200
    assert response.json()['nodes'][0]['properties']['name'] == 'Manufacture'
    assert response.json()['view']['type'] == 'architecture-process'
    assert calls[0]['prefix'] == 'archimate' and calls[0]['limit'] == 30


def test_process_query_failure_is_not_a_successful_empty_graph(monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError('private database details')
    monkeypatch.setattr(GraphViewService, 'get_architecture_process_view', unavailable)
    response = client().get('/api/v1/graph/view/architecture/archimate')
    assert response.status_code == 503
    assert 'private database details' not in response.text


def test_process_route_requires_read_identity():
    route = next(route for route in router.routes if route.path == '/graph/view/architecture/{prefix}')
    assert any(dependency.call is graph_read_identity for dependency in route.dependant.dependencies)
