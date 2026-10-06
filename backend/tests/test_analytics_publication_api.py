import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.artifact_store import ArtifactStore
from backend.mesh_store import InMemoryRegistry
from backend.data_product_service import router as products
from backend.data_catalog_service import router as catalog


@pytest.fixture
def publication_client(tmp_path, monkeypatch):
    approvals = InMemoryRegistry('data_product_approvals')
    class Store(InMemoryRegistry):
        def put_with_related(self, key, value, *, related_namespace, related_key, related_value):
            assert related_namespace == approvals.namespace
            approvals.put(related_key, related_value)
            return self.put(key, value)
    store = Store('data_products')
    monkeypatch.setattr(products, 'store', store)
    monkeypatch.setattr(products, 'approval_store', approvals)
    monkeypatch.setattr(products, 'root', tmp_path / 'products')
    artifacts = ArtifactStore(tmp_path / 'artifacts')
    monkeypatch.setattr(products, 'artifact_store', artifacts)
    monkeypatch.setenv('AUTH_MODE', 'token')
    monkeypatch.setenv('DEPO_CREDENTIAL_STORE', 'environment')
    monkeypatch.setenv('DATA_PRODUCT_APPROVAL_TOKEN', 'test-product-approval')
    monkeypatch.setenv('GRAPH_READ_TOKEN', 'test-read-key')
    async def resolve(release): return release
    async def pending(record):
        assert approvals.all(), 'Catalog attempt must follow approval persistence'
        return {**record, 'status':'pending_catalog_registration'}
    monkeypatch.setattr(products, 'resolve_approved_release', resolve)
    monkeypatch.setattr(products, '_register_catalog', pending)
    artifact = artifacts.ingest_bytes(b'schema design', filename='plan.json', kind='analytics-schema-plan')
    payload = dict(product_id='schema-evidence', name='Schema evidence', version='1.0.0', domain='engineering',
        owner='owner', steward='steward', classification='internal', lifecycle_state='published',
        approved_by='reviewer', artifacts=[{'artifact_id':artifact['artifact_id']}],
        semantic_releases=[{'asset_id':'schema-release','version':'1.0.0','lifecycle_status':'approved'}],
        product_kind='schema-design-evidence', analytics_readiness='requires_materialization_and_business_definition',
        idempotency_key='same-request')
    app = FastAPI(); app.include_router(products.router, prefix='/api/v1')
    return TestClient(app, headers={'Authorization':'Bearer test-product-approval'}), payload, store


def test_pending_publication_retry_and_changed_payload(publication_client):
    client, payload, store = publication_client
    first = client.post('/api/v1/data-products/publish', json=payload)
    assert first.status_code == 200
    assert first.json()['manifest']['analytics_readiness'] == payload['analytics_readiness']
    assert client.post('/api/v1/data-products/publish', json=payload).json() == first.json()
    changed = client.post('/api/v1/data-products/publish', json={**payload,'name':'Changed'})
    assert changed.status_code == 409
    assert store.get('schema-evidence:1.0.0')['name'] == payload['name']


def test_missing_approval_and_invalid_preview(publication_client):
    client, payload, store = publication_client
    response = client.post('/api/v1/data-products/publish', json=payload, headers={'Authorization':'Bearer wrong'})
    assert response.status_code == 403
    assert not store.all()
    invalid = client.post('/api/v1/data-products/preview', json={**payload,'version':'1.0.0-01'})
    assert not invalid.json()['valid']


def test_catalog_pagination_filters_and_authorizes(monkeypatch):
    store = InMemoryRegistry('catalog_products')
    for i in range(5): store.put(f'p{i}:1.0.0', {'product_id':f'p{i}', 'domain':'engineering', 'updated_at':str(i)})
    store.put('p0:latest', {'latest_version':'1.0.0'})
    monkeypatch.setattr(catalog, 'store', store)
    monkeypatch.setenv('AUTH_MODE','token'); monkeypatch.setenv('DEPO_CREDENTIAL_STORE','environment')
    monkeypatch.setenv('GRAPH_READ_TOKEN','test-read-key')
    app=FastAPI(); app.include_router(catalog.router,prefix='/api/v1')
    client=TestClient(app)
    assert client.get('/api/v1/catalog/products').status_code == 403
    response=client.get('/api/v1/catalog/products?limit=2&offset=2&domain=engineering',headers={'Authorization':'Bearer test-read-key'})
    assert response.status_code == 200
    assert response.json()['total'] == 5
    assert response.json()['next_offset'] == 4
    assert len(response.json()['products']) == 2
