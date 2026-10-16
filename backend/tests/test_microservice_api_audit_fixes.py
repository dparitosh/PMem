"""Regressions for API authorization, browser errors and recovery contracts."""
import ast
import asyncio
import hmac
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from starlette.concurrency import run_in_threadpool

from backend.depo_platform.service_runtime import create_service_app


def admin_guard():
    # Execute the real guard independently of the optional ontology engine.
    tree = ast.parse(Path('backend/routes/admin_routes.py').read_text(encoding='utf-8'))
    nodes = [node for node in tree.body if getattr(node, 'name', '') in
             {'_is_production_environment', 'require_admin_api_key'}]
    scope = dict(os=os, hmac=hmac, Request=Request, HTTPException=HTTPException,
                 run_in_threadpool=run_in_threadpool)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<admin-guard>', 'exec'), scope)
    return scope['require_admin_api_key']


@pytest.mark.parametrize('host,opt_in,environment,allowed', [
    ('10.20.30.40', 'true', {}, False),
    ('127.0.0.1', '', {}, False),
    ('127.0.0.1', 'true', {}, True),
    ('::1', 'true', {}, True),
    ('127.0.0.1', 'true', {'DEPO_ENV': 'production', 'APP_ENV': 'development'}, False),
    ('127.0.0.1', 'true', {'APP_ENV': 'development', 'DEPLOYMENT_ENV': 'staging'}, False),
])
def test_keyless_admin_requires_explicit_loopback_development(host, opt_in, environment, allowed):
    request = Request({'type': 'http', 'headers': [], 'client': (host, 1234)})
    with patch.dict(os.environ, {'DEPO_CREDENTIAL_STORE': 'environment',
                               'DEPO_ALLOW_INSECURE_LOCAL_AUTH': opt_in, **environment}, clear=True):
        if allowed:
            asyncio.run(admin_guard()(request))
        else:
            with pytest.raises(HTTPException) as failure:
                asyncio.run(admin_guard()(request))
            assert failure.value.status_code == 503


def test_valid_admin_key_still_requires_a_match(monkeypatch):
    monkeypatch.setenv('DEPO_CREDENTIAL_STORE', 'environment')
    monkeypatch.setenv('ADMIN_API_KEY', 'correct-admin-key')
    guard = admin_guard()
    for supplied, allowed in [('correct-admin-key', True), ('wrong', False)]:
        request = Request({'type': 'http', 'headers': [(b'x-api-key', supplied.encode())], 'client': ('10.20.30.40', 1)})
        if allowed:
            asyncio.run(guard(request))
        else:
            with pytest.raises(HTTPException):
                asyncio.run(guard(request))


def test_unhandled_error_retains_cors_and_correlation_without_exposing_exception(monkeypatch):
    monkeypatch.setenv('ALLOWED_ORIGINS', 'http://localhost:3000')
    app = create_service_app(title='Audit', version='1', dependencies=())

    @app.get('/failure')
    def failure():
        raise RuntimeError('private storage details')

    client = TestClient(app, raise_server_exceptions=False)
    for origin, permitted in [('http://localhost:3000', True), ('http://untrusted.example', False)]:
        response = client.get('/failure', headers={'Origin': origin, 'X-Request-ID': 'known-request'})
        assert response.status_code == 500
        assert response.headers['x-request-id'] == 'known-request'
        assert response.json()['request_id'] == 'known-request'
        assert 'private storage' not in response.text
        assert (response.headers.get('access-control-allow-origin') == origin) is permitted


def test_credential_discovery_profiles_are_all_supported(monkeypatch):
    app = create_service_app(title='Audit', version='1', dependencies=())
    operation = app.openapi()['paths']['/auth/credential-check']['get']
    profiles = operation['x-depo-credential-check']['supported_profiles']
    assert 'ADMIN_API_KEY' not in profiles
    assert 'GRAPH_READ_TOKEN' not in profiles
    with patch('backend.depo_platform.authorization.service_write_identity', return_value='verified'):
        for profile in profiles:
            response = TestClient(app).get('/auth/credential-check', params={'profile': profile})
            assert response.status_code == 200


@pytest.mark.parametrize('stage', ['lock', 'read'])
def test_analytics_registry_outage_returns_recoverable_response(monkeypatch, stage):
    from backend.data_pipeline_service import router
    from backend.mesh_store import InMemoryRegistry
    registry = InMemoryRegistry()
    monkeypatch.setattr(router.run_records, 'store', registry)
    monkeypatch.setattr(router, 'approval_identity', lambda *a, **kw: 'verified')
    def unavailable(*a, **kw):
        raise RuntimeError('private database detail')
    monkeypatch.setattr(registry, 'advisory_lock' if stage == 'lock' else 'get', unavailable)
    app = create_service_app(title='Audit', version='1', dependencies=())
    app.include_router(router.router, prefix='/api/v1')
    response = TestClient(app).post('/api/v1/pipeline/jobs/runs/retained-run/reconcile-analytics', json={})
    assert response.status_code == 503
    assert response.headers['x-depo-run-id'] == 'retained-run'
    assert response.headers['x-depo-run-kind'] == 'pipeline'
    assert 'private database detail' not in response.text


def test_pipeline_helper_approval_is_documented():
    from backend.data_pipeline_service.app import app
    operation = app.openapi()['paths']['/api/v1/pipeline/jobs/definitions/{job_id}/{version}/run']['post']
    metadata = operation['x-depo-authorization']
    assert metadata['credential_profiles'] == ['DATA_JOB_EXECUTION_TOKEN']
    assert metadata['approval_fields'] == ['approved_by', 'approval_token']
    assert metadata['required_fields_in_token_mode'] == ['approved_by']
    assert {} in operation['security']  # credential can be supplied in the body
