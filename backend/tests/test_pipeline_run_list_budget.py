from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import asyncio
import httpx
import pytest
from fastapi import FastAPI
from psycopg.errors import LockNotAvailable, QueryCanceled
from backend.data_pipeline_service import router as module
from backend.depo_platform.authorization import graph_read_identity
from backend.depo_platform.operations import OperationContext, current_operation, operation_scope
from backend.depo_platform.service_runtime import RequestIdMiddleware


@pytest.mark.parametrize('seconds', [1, 60])
def test_run_list_preserves_identity_and_never_extends_parent_deadline(monkeypatch, seconds):
    parent = OperationContext('request-budget', (datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat())
    def page(**kwargs):
        child = current_operation()
        assert child.operation_id == parent.operation_id
        remaining = child.timeout(60)
        assert 0 < remaining <= min(seconds, 5)
        return 1, [{'run_id':'retained'}]
    monkeypatch.setattr(module.run_records, 'store', SimpleNamespace(page=page))
    with operation_scope(parent):
        assert module.list_job_runs()['runs'] == [{'run_id':'retained'}]
        assert current_operation() is parent


@pytest.mark.parametrize('failure', [LockNotAvailable, QueryCanceled])
def test_contention_is_retryable_read_failure_with_correlation_and_no_query_leak(monkeypatch, failure):
    def page(**kwargs):
        raise failure('private SQL and parameters')
    monkeypatch.setattr(module.run_records, 'store', SimpleNamespace(page=page))
    app = FastAPI()
    app.include_router(module.router, prefix='/api/v1')
    app.dependency_overrides[graph_read_identity] = lambda: 'test-reader'
    app.add_middleware(RequestIdMiddleware)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            response = await client.get('/api/v1/pipeline/jobs/runs',headers={'X-Request-ID':'bounded-read'})
            assert response.status_code == 503
            assert response.headers['Retry-After'] == '2'
            assert response.headers['X-Request-ID'] == 'bounded-read'
            assert 'private' not in response.text
            assert 'no job was replayed' in response.text
    asyncio.run(scenario())
