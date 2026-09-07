import asyncio
import httpx
from backend.agentic_service.oslc_graph_rag import oslc_graph_rag


def test_oslc_graph_rag_returns_bounded_context(monkeypatch):
    monkeypatch.setenv('OSLC_REMOTE_BASE_URL', 'https://oslc.example')
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def get(self, endpoint, *, params, headers):
            assert endpoint.endswith('/oslc/query/resources')
            assert params['oslc.searchTerms'] == 'pump'
            return httpx.Response(200, request=httpx.Request('GET', endpoint), json={'results': [{'uri': 'urn:r1', 'title': 'Pump', 'ontology_id': 'ap242', 'revision': 'A', 'validation_status': 'valid'}]})
    monkeypatch.setattr('backend.agentic_service.oslc_graph_rag.httpx.AsyncClient', Client)
    result = asyncio.run(oslc_graph_rag.retrieve('pump'))
    assert result['status'] == 'grounded'
    assert result['resource_ids'] == ['urn:r1']
    assert result['ontology_context'] == ['ap242']
    assert result['validation']['statuses'] == ['valid']


def test_oslc_graph_rag_fails_closed(monkeypatch):
    monkeypatch.delenv('OSLC_REMOTE_BASE_URL', raising=False)
    try:
        asyncio.run(oslc_graph_rag.retrieve('pump'))
    except RuntimeError as exc:
        assert 'not configured' in str(exc)
    else:
        raise AssertionError('Expected missing OSLC configuration to fail closed')
