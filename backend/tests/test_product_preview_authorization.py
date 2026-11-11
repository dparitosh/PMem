from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.data_product_service import router as product


def test_publication_checks_approval_before_reading_or_hashing_artifacts(monkeypatch):
    monkeypatch.setenv('AUTH_MODE','token')
    monkeypatch.setenv('DEPO_CREDENTIAL_STORE','environment')
    monkeypatch.setenv('DATA_PRODUCT_APPROVAL_TOKEN','test-product-token')
    app=FastAPI();app.include_router(product.router)
    with patch.object(product,'_validate') as validate:
        response=TestClient(app).post('/data-products/publish',json={
            'product_id':'fixture','version':'1.0.0','name':'Fixture','domain':'engineering',
            'owner':'owner','steward':'steward','classification':'internal','lifecycle_state':'published'})
    assert response.status_code==403
    validate.assert_not_called()


def test_product_preview_requires_auth_before_artifact_reads(monkeypatch):
    monkeypatch.setenv('AUTH_MODE', 'token')
    monkeypatch.setenv('DEPO_CREDENTIAL_STORE', 'environment')
    monkeypatch.setenv('DATA_PRODUCT_APPROVAL_TOKEN', 'test-product-token')
    app=FastAPI(); app.include_router(product.router)
    with patch.object(product, '_validate') as validate:
        response=TestClient(app).post('/data-products/preview', json={})
    assert response.status_code == 403
    validate.assert_not_called()


def test_preview_does_not_report_nonexistent_release_as_valid(monkeypatch):
    monkeypatch.setenv('AUTH_MODE', 'token')
    monkeypatch.setenv('DEPO_CREDENTIAL_STORE', 'environment')
    monkeypatch.setenv('DATA_PRODUCT_APPROVAL_TOKEN', 'test-product-token')
    app=FastAPI(); app.include_router(product.router)
    async def missing(reference): raise ValueError('Referenced semantic release does not exist')
    with patch.object(product, '_validate', return_value=([], [])), patch.object(product, 'resolve_approved_release', missing):
        response=TestClient(app).post('/data-products/preview', json={
            'product_id':'fixture', 'version':'1.0', 'name':'Fixture', 'domain':'engineering',
            'owner':'fixture-owner', 'steward':'fixture-steward', 'classification':'internal',
            'lifecycle_state':'draft',
            'semantic_releases':[{'asset_id':'missing', 'version':'1.0', 'lifecycle_status':'approved'}],
        }, headers={'Authorization':'Bearer test-product-token'})
    assert response.status_code == 200
    assert response.json()['valid'] is False
