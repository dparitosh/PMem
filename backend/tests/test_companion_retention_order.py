from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import pytest
from fastapi import HTTPException
from backend.agentic_service import router as routes
from backend.agentic_service.chat_request import ChatRequest


@pytest.mark.asyncio
@pytest.mark.parametrize('fail_retention', [False, True])
async def test_required_retention_precedes_optional_memory(monkeypatch, fail_retention):
    events = []
    async def io(fn, *args, **kwargs): return fn(*args, **kwargs)
    def retain(*args):
        events.append('postgres')
        if fail_retention: raise RuntimeError('fixture storage unavailable')
    def enrich(**kwargs):
        events.append('graph')
        raise RuntimeError('optional graph unavailable')
    monkeypatch.setenv('COMPANION_LLM_ENABLED', 'false')
    monkeypatch.setattr(routes, '_agent_io', io)
    monkeypatch.setattr(routes, 'run_in_threadpool', io)
    monkeypatch.setattr(routes, 'graph_read_identity', lambda request: 'actor')
    monkeypatch.setattr(routes, 'downstream_headers', lambda *a, **kw: {})
    monkeypatch.setattr(routes, 'sessions', SimpleNamespace(open_session=lambda *a: {'session_id':'s', 'expires_at':'2026-10-25T12:00:00+00:00'}, memory_id=lambda s:'memory', owner=lambda *a:'owner'))
    monkeypatch.setattr(routes, '_session_turns', lambda *a: [])
    monkeypatch.setattr(routes, 'telemetry', SimpleNamespace(start=lambda **kw: ({'run_id':'r'}, 0)))
    monkeypatch.setattr(routes, '_finish_observation', lambda *a, **kw: None)
    monkeypatch.setattr(routes, 'companion_job_store', SimpleNamespace(put=retain))
    monkeypatch.setattr(routes, 'AgentMemoryService', SimpleNamespace(enabled=lambda:True, record_chat_turn=enrich))
    async def ask(*args, **kwargs):
        if kwargs.get('on_token'):await kwargs['on_token']('answer')
        return {'response':'answer', 'evidence':[], 'sources':[], 'answerable':False}
    async def emit(text):events.append('stream')
    monkeypatch.setattr(routes, 'companion', SimpleNamespace(_graph_root=lambda:'http://fixture', ask=ask))
    request=SimpleNamespace(state=SimpleNamespace(request_id='request'))
    if fail_retention:
        with pytest.raises(HTTPException) as failure: await routes._companion_chat(ChatRequest(message='test'), request, on_token=emit)
        assert failure.value.status_code == 503
        assert events == ['postgres']
    else:
        result=await routes._companion_chat(ChatRequest(message='test'), request, on_token=emit)
        assert events == ['postgres','graph','stream']
        assert result['retention']['status'] == 'retained'
        assert result['memory_enrichment'] == {'status':'unavailable', 'required':False}
