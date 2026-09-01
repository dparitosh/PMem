from pathlib import Path
from fastapi.testclient import TestClient
from backend.artifact_store import ArtifactStore
from backend.data_catalog_service.app import app as catalog_app
from backend.data_catalog_service import router as catalog_router
from backend.data_product_service import router as product_router
from backend.data_product_service.packaging import build_package

def test_catalog_retains_independent_versions(tmp_path: Path, monkeypatch):
    catalog_router.store = catalog_router.SqliteRegistry(tmp_path / "catalog")
    monkeypatch.setenv("CATALOG_SERVICE_TOKEN", "test-catalog-token")
    client = TestClient(catalog_app)
    for version in ("1.0.0", "2.0.0"):
        response = client.put(f"/api/v1/catalog/products/parts/versions/{version}", headers={"X-DEPO-Service-Token": "test-catalog-token"}, json={"name": "Parts", "domain": "Engineering", "owner": "data", "classification": "internal", "steward": "data", "lifecycle_state": "published"})
        assert response.status_code == 200
    product = client.get("/api/v1/catalog/products/parts").json()
    assert len(product["versions"]) == 2
    assert product["latest_version"] == "2.0.0"


def test_catalog_rejects_unsigned_writes(tmp_path: Path, monkeypatch):
    catalog_router.store = catalog_router.SqliteRegistry(tmp_path / "catalog")
    monkeypatch.setenv("CATALOG_SERVICE_TOKEN", "test-catalog-token")
    response = TestClient(catalog_app).put("/api/v1/catalog/products/parts/versions/1.0.0", json={"name": "Parts", "domain": "Engineering", "owner": "data", "classification": "internal", "steward": "data", "lifecycle_state": "published"})
    assert response.status_code == 403

def test_product_preview_rejects_artifact_outside_allowed_root(tmp_path: Path, monkeypatch):
    product_router.root = tmp_path / "products"; product_router.store = product_router.SqliteRegistry(product_router.root / "products")
    product_router.artifact_store = ArtifactStore(tmp_path / "artifacts")
    monkeypatch.setenv("DATA_PRODUCT_ALLOWED_ARTIFACT_ROOTS", str(product_router.root))
    response = TestClient(__import__("backend.data_product_service.app", fromlist=["app"]).app).post("/api/v1/data-products/preview", json={"product_id":"p", "name":"P", "version":"1", "domain":"D", "owner":"O", "artifacts":[{"path":str(tmp_path / "outside.ttl")} ]})
    assert response.json()["valid"] is False


def test_product_preview_accepts_content_addressed_artifact(tmp_path: Path):
    source = tmp_path / "source.ttl"; source.write_text("@prefix x: <urn:x:> .", encoding="utf-8")
    product_router.artifact_store = ArtifactStore(tmp_path / "artifacts")
    artifact = product_router.artifact_store.ingest(source, kind="ontology", media_type="text/turtle")
    response = TestClient(__import__("backend.data_product_service.app", fromlist=["app"]).app).post(
        "/api/v1/data-products/preview",
        json={"product_id":"p", "name":"P", "version":"1", "domain":"D", "owner":"O", "classification":"internal", "steward":"O", "lifecycle_state":"draft", "artifacts":[{"artifact_id": artifact["artifact_id"]}]},
    )
    assert response.json()["valid"] is True


def test_package_recovery_retains_private_storage_paths(tmp_path: Path):
    source = tmp_path / "source.ttl"; source.write_text("@prefix x: <urn:x:> .", encoding="utf-8")
    artifact = ArtifactStore(tmp_path / "artifacts").ingest(source)
    payload = {"product_id": "parts", "name": "Parts", "version": "1.0.0", "domain": "Engineering", "owner": "data", "classification": "internal", "steward": "data", "lifecycle_state": "draft"}
    first = build_package(output_root=tmp_path / "products", payload=payload, artifacts=[(artifact, source)])
    recovered = build_package(output_root=tmp_path / "products", payload=payload, artifacts=[(artifact, source)])
    assert first["zip_path"].is_file() and recovered["zip_path"].is_file()
    assert "zip_path" not in recovered["manifest"]
