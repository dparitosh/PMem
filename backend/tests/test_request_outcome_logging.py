"""Handled failures and durable workers retain correlation without payload logging."""
import asyncio
import json
import logging
import httpx
import pytest
from fastapi import FastAPI, HTTPException
from backend.depo_platform.service_runtime import RequestIdMiddleware
from backend.depo_platform.qos import QoSMiddleware, QoSState


@pytest.mark.parametrize('status', [200, 403, 409, 422, 503])
def test_write_outcome_logs_status_route_id_and_duration_without_secrets(caplog, status):
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    @app.post('/runs/{run_id}/replay')
    async def replay(run_id: str):
        if status != 200:
            raise HTTPException(status, 'private-response-detail')
        return {'ok': True}
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            response = await client.post('/runs/private-source/replay?key=private-query',
                headers={'X-Request-ID':'audit-replay-1','Authorization':'Bearer private-token'},
                json={'approval_token':'private-body'})
            assert response.status_code == status
            assert response.headers['X-Request-ID'] == 'audit-replay-1'
    with caplog.at_level(logging.INFO, logger='backend.depo_platform.service_runtime'):
        asyncio.run(scenario())
    messages = [r.getMessage() for r in caplog.records if r.name == 'backend.depo_platform.service_runtime']
    record = json.loads(messages[-1])
    assert record == {'event':'http_request_outcome','request_id':'audit-replay-1',
        'method':'POST','route':'/runs/{run_id}/replay','status':status,'response_headers_ms':record['response_headers_ms']}
    assert record['response_headers_ms'] >= 0
    assert 'private-' not in ''.join(messages)


def test_timeout_log_and_response_share_correlation_id(monkeypatch, caplog):
    from backend.depo_platform import qos
    monkeypatch.setattr(qos,'request_budget',lambda path:.02)
    app=FastAPI()
    app.add_middleware(QoSMiddleware,state=QoSState())
    app.add_middleware(RequestIdMiddleware)
    @app.get('/slow')
    async def slow():
        await asyncio.sleep(1)
        return {}
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test') as client:
            response=await client.get('/slow',headers={'X-Request-ID':'audit-timeout-1'})
            assert response.status_code==504
            assert response.json()['request_id']=='audit-timeout-1'
    with caplog.at_level(logging.WARNING):
        asyncio.run(scenario())
    entries=[json.loads(r.getMessage()) for r in caplog.records if r.name in
        {'backend.depo_platform.qos','backend.depo_platform.service_runtime'}]
    assert {r['event'] for r in entries}=={'request_admission_failure','http_request_outcome'}
    assert all(r['request_id']=='audit-timeout-1' and r['status']==504 for r in entries)


def test_worker_error_logs_identity_without_exception_payload(caplog):
    from backend.data_pipeline_service.worker import log_run_event
    with caplog.at_level(logging.INFO):
        log_run_event('pipeline_run_execution_failed',{'run_id':'run-one','job_id':'job',
            'correlation_id':'request-one','worker_id':'worker','attempt':2,'payload':'private-source'},
            ValueError('private-token'))
    record=json.loads(caplog.records[-1].getMessage())
    assert record['run_id']=='run-one' and record['correlation_id']=='request-one'
    assert record['error_type']=='ValueError'
    assert 'private-' not in caplog.records[-1].getMessage()
