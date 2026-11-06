"""A lost response must never cause a second publication dispatch."""
import asyncio
import httpx
import pytest
from backend.depo_platform import graph_publication_transport as transport


def receipt():
    return dict(status='published', current=True, ontology_id='demo', publication_id='pub',
                resources=2, relationships=1, hierarchy_edges=0)


@pytest.mark.parametrize('failure', ['timeout', 'cancel', 'server', 'invalid'])
def test_response_loss_reconciles_once(monkeypatch, failure):
    calls = []
    monkeypatch.setattr(transport, 'service_bearer_headers', lambda *a, **kw: {})
    async def request(method, endpoint, **kwargs):
        calls.append(method)
        if method == 'POST':
            if failure == 'timeout': raise httpx.ReadTimeout('lost')
            if failure == 'cancel': raise asyncio.CancelledError()
            return httpx.Response(503 if failure == 'server' else 200,
                                  content=b'bad json', request=httpx.Request(method, endpoint))
        return httpx.Response(200, json=receipt(), request=httpx.Request(method, endpoint))
    monkeypatch.setattr(transport, 'async_peer_response', request)
    result = asyncio.run(transport.publish_graph('http://graph/api/v1', content=b'ttl',
                         ontology_id='demo', prefix='d', publication_id='pub'))
    assert result['reconciled'] is True
    assert calls == ['POST', 'GET']


@pytest.mark.parametrize('status', [400, 401, 403, 404, 413, 422])
def test_known_rejection_is_not_response_loss(monkeypatch, status):
    calls = []
    monkeypatch.setattr(transport, 'service_bearer_headers', lambda *a, **kw: {})
    async def request(method, endpoint, **kwargs):
        calls.append(method)
        return httpx.Response(status, request=httpx.Request(method, endpoint))
    monkeypatch.setattr(transport, 'async_peer_response', request)
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(transport.publish_graph('http://graph/api/v1', content=b'ttl',
                    ontology_id='demo', prefix='d', publication_id='pub'))
    assert calls == ['POST']


@pytest.mark.parametrize('status', [404, 409, 503])
def test_unresolved_receipt_preserves_identity_without_replay(monkeypatch, status):
    calls = []
    monkeypatch.setattr(transport, 'service_bearer_headers', lambda *a, **kw: {})
    async def request(method, endpoint, **kwargs):
        calls.append(method)
        if method == 'POST': raise httpx.ReadTimeout('lost')
        return httpx.Response(status, request=httpx.Request(method, endpoint))
    monkeypatch.setattr(transport, 'async_peer_response', request)
    with pytest.raises(transport.PublicationUnverified) as error:
        asyncio.run(transport.publish_graph('http://graph/api/v1', content=b'ttl',
                    ontology_id='demo', prefix='d', publication_id='pub'))
    assert error.value.publication_id == 'pub'
    assert calls == ['POST', 'GET']


def test_receipt_requires_exact_identity_and_counts():
    assert transport.verified_receipt(receipt(), 'demo', 'pub')
    assert not transport.verified_receipt(receipt(), 'other', 'pub')
    assert not transport.verified_receipt({**receipt(), 'resources': True}, 'demo', 'pub')
