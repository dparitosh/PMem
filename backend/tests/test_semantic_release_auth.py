import httpx
import pytest
from backend.depo_platform import semantic_registry


@pytest.mark.asyncio
async def test_release_check_forwards_read_and_gateway_credentials(monkeypatch):
    monkeypatch.setenv('SEMANTIC_REGISTRY_URL','https://example.invalid/depo/ontology/api/v1/metadata-registry')
    monkeypatch.setenv('GRAPH_READ_TOKEN','server-read-key')
    monkeypatch.setenv('DEPO_API_GATEWAY_URL','https://example.invalid/depo')
    monkeypatch.setenv('DEPO_APIM_SUBSCRIPTION_KEY','gateway-key')
    observed={}
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url, headers):
            observed.update(url=url,headers=headers)
            return httpx.Response(200,json={'asset_id':'quality','version':'1.0.0','lifecycle_status':'approved'})
    monkeypatch.setattr(semantic_registry.httpx,'AsyncClient',Client)
    release={'asset_id':'quality','version':'1.0.0','lifecycle_status':'approved'}
    assert await semantic_registry.resolve_approved_release(release) == release
    assert observed['headers']['Authorization'] == 'Bearer server-read-key'
    assert observed['headers']['Ocp-Apim-Subscription-Key'] == 'gateway-key'
    assert observed['url'].endswith('/assets/quality')


@pytest.mark.asyncio
async def test_release_check_rejects_a_different_asset_with_matching_version(monkeypatch):
    monkeypatch.setenv('GRAPH_READ_TOKEN','server-read-key')
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def get(self,*args,**kwargs):
            return httpx.Response(200,json={'asset_id':'other','version':'1.0.0','lifecycle_status':'approved'})
    monkeypatch.setattr(semantic_registry.httpx,'AsyncClient',Client)
    with pytest.raises(ValueError):
        await semantic_registry.resolve_approved_release({'asset_id':'quality','version':'1.0.0','lifecycle_status':'approved'})
