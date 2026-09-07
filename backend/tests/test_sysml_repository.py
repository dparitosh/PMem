import asyncio
from types import SimpleNamespace
import httpx
import pytest
from backend.ingestion_service import sysml_repository as repo


@pytest.mark.parametrize('foreign', [False, True])
def test_commit_pagination_and_credential_boundary(monkeypatch, foreign):
    calls = []
    def handler(request):
        calls.append(str(request.url))
        assert request.headers['Authorization'] == 'Bearer test'
        if len(calls) == 1:
            next_url = 'https://other.example/elements' if foreign else '?page[after]=a'
            return httpx.Response(200, json=[{'@id': 'a'}], headers={'Link': f'<{next_url}>; rel="next"'})
        return httpx.Response(200, json=[{'@id': 'b'}])
    client_type = httpx.AsyncClient
    monkeypatch.setattr(repo.httpx, 'AsyncClient', lambda **kw: client_type(transport=httpx.MockTransport(handler), **kw))
    cfg = SimpleNamespace(enabled=True, base_url='https://repo.example', project_id='p', commit_id='c', page_size=100, token='test', request_timeout_seconds=10)
    if foreign:
        with pytest.raises(ValueError, match='escaped'):
            asyncio.run(repo.read_snapshot(cfg))
        assert len(calls) == 1
    else:
        assert len(asyncio.run(repo.read_snapshot(cfg))['elements']) == 2
