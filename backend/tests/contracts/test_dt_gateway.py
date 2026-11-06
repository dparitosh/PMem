import asyncio
import httpx
import pytest
from backend.agentic_service.dt_gateway import execute_current_plan


def test_gateway_dispatch(monkeypatch):
    monkeypatch.setenv("DT_AGENT_GATEWAY_URL", "https://gateway.example/dt/api/v1")
    monkeypatch.setenv("DT_AGENT_GATEWAY_TOKEN", "test-token")
    original = httpx.AsyncClient
    def handler(request):
        assert str(request.url) == "https://gateway.example/dt/api/v1/workflow/run/"
        assert request.headers["X-Correlation-ID"] == "run-1"
        return httpx.Response(200, json={"clarification_needed": True})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    assert asyncio.run(execute_current_plan("inspect", "test@example.com", "run-1"))["clarification_needed"]


def test_gateway_refuses_unconfigured_or_insecure_target(monkeypatch):
    monkeypatch.setenv("DT_AGENT_GATEWAY_URL", "http://localhost:8000")
    with pytest.raises(ValueError):
        asyncio.run(execute_current_plan("inspect", "test@example.com", "run-1"))
