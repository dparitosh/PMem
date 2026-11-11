from backend.data_pipeline_service.ingestor_catalog import capabilities, check_required_adapter
import os
import sys
import pytest


def test_all_requested_types_are_visible_without_claiming_unimplemented_connectors():
    body = capabilities()
    assert body['contract'] == 'ingestor-capabilities-v1'
    assert len(body['ingestors']) == 17
    assert len({r['name'] for r in body['ingestors']}) == 17
    wired = [r for r in body['ingestors'] if r['configurable']]
    assert len(wired)==14
    assert {r['job_type'] for r in wired}=={'rest-source-ingest','registered-source-ingest'}
    rest=next(r for r in wired if r['name']=='RESTIngestor')
    assert rest['postgres_namespace'] == 'rest_sources'
    assert rest['job_type'] == 'rest-source-ingest'
    assert all(r['postgres_namespace'] is None for r in body['ingestors'] if not r['configurable'])
    assert body['runtime_probe'] == 'not_run'


def test_installed_rest_adapter_has_required_lazy_entrypoint():
    assert check_required_adapter()['status'] == 'ok'


def test_inventory_does_not_import_optional_ingestors(monkeypatch):
    import builtins
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        assert not name.startswith('semantica'), 'Inventory must not initialize optional SDKs'
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    assert len(capabilities()['ingestors']) == 17


def test_isolated_acquisition_uses_fixed_existing_semantic_runtime(monkeypatch, tmp_path):
    from backend.data_pipeline_service import rest_sources
    monkeypatch.setenv('DEPO_SERVICE_RUNTIME_MODE', 'isolated')
    monkeypatch.setattr(rest_sources, '__file__', str(tmp_path / 'backend/data_pipeline_service/rest_sources.py'))
    with pytest.raises(ValueError, match='installed ontology service runtime'):
        rest_sources._worker_command()
    binary = tmp_path / 'backend/.dt_venv-ontology' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    binary.parent.mkdir(parents=True); binary.touch()
    assert rest_sources._worker_command() == [str(binary), '-m', 'backend.data_pipeline_service.rest_fetch_worker']
    monkeypatch.setenv('DEPO_SERVICE_RUNTIME_MODE', 'shared')
    assert rest_sources._worker_command()[0] == sys.executable
    monkeypatch.setenv('DEPO_SERVICE_RUNTIME_MODE', 'arbitrary-command')
    with pytest.raises(ValueError, match='shared or isolated'):
        rest_sources._worker_command()


def test_actual_shared_acquisition_child_smoke(monkeypatch):
    from backend.data_pipeline_service.ingestor_catalog import check_acquisition_runtime
    monkeypatch.setenv('DEPO_SERVICE_RUNTIME_MODE', 'shared')
    assert check_acquisition_runtime()['execution'] == 'bounded-child'


def test_capability_route_requires_read_authorization(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.data_pipeline_service.rest_router import router
    monkeypatch.setenv('AUTH_MODE', 'token')
    monkeypatch.setenv('DEPO_CREDENTIAL_STORE', 'environment')
    monkeypatch.setenv('GRAPH_READ_TOKEN', 'inventory-test-only')
    app = FastAPI(); app.include_router(router)
    with TestClient(app) as client:
        assert client.get('/pipeline/rest-sources/capabilities').status_code == 403
        response = client.get('/pipeline/rest-sources/capabilities', headers={'Authorization':'Bearer inventory-test-only'})
        assert response.status_code == 200
        assert len(response.json()['ingestors']) == 17
        assert 'inventory-test-only' not in response.text
