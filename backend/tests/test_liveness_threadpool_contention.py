import asyncio
import threading
import anyio
import httpx
import pytest
from backend.depo_platform.service_runtime import create_service_app

@pytest.mark.asyncio
async def test_liveness_does_not_wait_for_a_saturated_sync_worker_pool():
    app=create_service_app(title='Liveness contention test',version='1')
    entered=threading.Event();release=threading.Event()
    @app.get('/slow-sync')
    def slow():
        entered.set();release.wait(5);return {'done':True}
    limiter=anyio.to_thread.current_default_thread_limiter();previous=limiter.total_tokens
    limiter.total_tokens=1
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        slow_task=asyncio.create_task(client.get('/slow-sync'))
        try:
            for _ in range(100):
                if entered.is_set():break
                await asyncio.sleep(.01)
            assert entered.is_set()
            response=await asyncio.wait_for(client.get('/healthz'),timeout=1)
            assert response.status_code==200 and response.json()['status']=='ok'
        finally:
            release.set();await slow_task;limiter.total_tokens=previous
