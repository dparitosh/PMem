from pathlib import Path
from fastapi.testclient import TestClient
from backend.data_catalog_service.app import app as catalog_app
from backend.data_catalog_service import router as catalog_router
from backend.data_product_service import router as product_router

def test_catalog_retains_independent_versions(tmp_path: Path, monkeypatch):
    catalog_router.store = catalog_router.JsonRegistry(tmp_path / "catalog.json")
    client = TestClient(catalog_app)
    for version in ("1.0.0", "2.0.0"):
        response = client.put(f"/api/v1/catalog/products/parts/versions/{version}", json={"name": "Parts", "domain": "Engineering", "owner": "data"})
        assert response.status_code == 200
    assert len(client.get("/api/v1/catalog/products/parts").json()["versions"]) == 2

def test_product_preview_rejects_artifact_outside_allowed_root(tmp_path: Path, monkeypatch):
    product_router.root = tmp_path / "products"; product_router.store = product_router.JsonRegistry(product_router.root / "products.json")
    monkeypatch.setenv("DATA_PRODUCT_ALLOWED_ARTIFACT_ROOTS", str(product_router.root))
    response = TestClient(__import__("backend.data_product_service.app", fromlist=["app"]).app).post("/api/v1/data-products/preview", json={"product_id":"p", "name":"P", "version":"1", "domain":"D", "owner":"O", "artifacts":[{"path":str(tmp_path / "outside.ttl")} ]})
    assert response.json()["valid"] is False
