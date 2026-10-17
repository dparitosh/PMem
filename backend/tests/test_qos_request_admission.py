"""Request deadlines and reserved control capacity without customer dependencies."""
import asyncio
from datetime import datetime, timedelta, timezone
import httpx
import pytest
from fastapi import FastAPI
from backend.depo_platform.qos import QoSMiddleware, QoSState
from backend.depo_platform.postgres_pool import PoolBusy


def test_saturation_reserves_control_capacity_and_records_metrics(monkeypatch):
    monkeypatch.setenv('DEPO_MAX_INFLIGHT_REQUESTS', '1')
    monkeypatch.setenv('DEPO_MAX_INFLIGHT_CONTROL_REQUESTS', '1')
    async def scenario():
        app = FastAPI()
        state = QoSState()
        app.add_middleware(QoSMiddleware, state=state)
        entered, release = asyncio.Event(), asyncio.Event()
        @app.get('/work')
        async def work():
            entered.set()
            await release.wait()
            return {'ok': True}
        @app.get('/auth/access')
        async def access():
            return {'ok': True}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            first = asyncio.create_task(client.get('/work'))
            await entered.wait()
            overloaded = await client.get('/work')
            assert overloaded.status_code == 503
            assert overloaded.headers['Retry-After'] == '5'
            assert (await client.get('/auth/access')).status_code == 200
            release.set()
            assert (await first).status_code == 200
        snapshot = state.snapshot()
        assert snapshot['rejected']['work'] == 1
        assert snapshot['inflight']['work'] == 0
        assert snapshot['routes']['GET /work']['count'] == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('busy', [False, True])
def test_deadline_and_pool_saturation_have_distinct_http_status(monkeypatch, busy):
    from backend.depo_platform import qos
    monkeypatch.setattr(qos, 'request_budget', lambda path: .03)
    app = FastAPI()
    app.add_middleware(QoSMiddleware, state=QoSState())
    @app.get('/work')
    async def work():
        if busy: raise PoolBusy('capacity exhausted')
        await asyncio.sleep(1)
        return {}
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            response = await client.get('/work')
            assert response.status_code == (503 if busy else 504)
            if busy:
                assert response.headers['Retry-After']
    asyncio.run(scenario())


def test_expired_inherited_deadline_prevents_dispatch():
    app = FastAPI()
    app.add_middleware(QoSMiddleware, state=QoSState())
    calls = []
    @app.get('/work')
    def work():
        calls.append(True)
        return {}
    async def scenario():
        expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            response = await client.get('/work', headers={'X-DEPO-Deadline': expired})
            assert response.status_code == 504
    asyncio.run(scenario())
    assert not calls
