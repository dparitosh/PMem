from pathlib import Path
from fastapi.testclient import TestClient
from backend.artifact_store import ArtifactStore
from backend.mesh_store import InMemoryRegistry
from backend.data_catalog_service.app import app as catalog_app
from backend.data_catalog_service import router as catalog_router
from backend.data_catalog_service.artifact_retention import retention
from backend.data_product_service import router as product_router
from backend.data_product_service.packaging import build_package

def test_catalog_retains_independent_versions(tmp_path: Path, monkeypatch):
    catalog_router.store = InMemoryRegistry()
    monkeypatch.setenv("CATALOG_SERVICE_TOKEN", "test-catalog-token")
    client = TestClient(catalog_app)
    for version in ("1.0.0", "2.0.0"):
        response = client.put(f"/api/v1/catalog/products/parts/versions/{version}", headers={"X-DEPO-Service-Token": "test-catalog-token"}, json={"name": "Parts", "domain": "Engineering", "owner": "data", "classification": "internal", "steward": "data", "lifecycle_state": "published"})
        assert response.status_code == 200
    product = client.get("/api/v1/catalog/products/parts").json()
    assert len(product["versions"]) == 2
    assert product["latest_version"] == "2.0.0"


def test_catalog_rejects_unsigned_writes(tmp_path: Path, monkeypatch):
    catalog_router.store = InMemoryRegistry()
    monkeypatch.setenv("CATALOG_SERVICE_TOKEN", "test-catalog-token")
    response = TestClient(catalog_app).put("/api/v1/catalog/products/parts/versions/1.0.0", json={"name": "Parts", "domain": "Engineering", "owner": "data", "classification": "internal", "steward": "data", "lifecycle_state": "published"})
    assert response.status_code == 403

def test_product_preview_rejects_artifact_outside_allowed_root(tmp_path: Path, monkeypatch):
    product_router.root = tmp_path / "products"; product_router.store = InMemoryRegistry(); product_router.approval_store = InMemoryRegistry()
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
        json={"product_id":"p", "name":"P", "version":"1", "domain":"D", "owner":"O", "classification":"internal", "steward":"O", "lifecycle_state":"draft", "semantic_releases":[{"asset_id":"ceim-core", "version":"0.1.0", "lifecycle_status":"approved"}], "artifacts":[{"artifact_id": artifact["artifact_id"]}]},
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


def test_artifact_retention_records_tier_hold_and_durable_purge_evidence(tmp_path: Path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    monkeypatch.setattr("backend.data_catalog_service.router.approval_identity", lambda request, payload, token_env: str(payload.get("approved_by") or "retention-steward"))
    retention.store = InMemoryRegistry()
    retention.artifact_store = ArtifactStore(tmp_path / "artifacts")
    source = tmp_path / "source.json"
    source.write_text('{"source":"retention-test"}', encoding="utf-8")
    artifact = retention.artifact_store.ingest(source, kind="raw-source", media_type="application/json")
    client = TestClient(catalog_app)

    registered = client.post(
        f"/api/v1/catalog/artifacts/{artifact['artifact_id']}/retention",
        json={"approved_by": "retention-steward", "retention_days": 1, "tier": "cold", "legal_hold": True, "reason": "Customer source retention contract"},
    )
    assert registered.status_code == 200
    assert registered.json()["tier"] == "cold"
    assert registered.json()["legal_hold"] is True
    blocked = client.post(f"/api/v1/catalog/artifacts/{artifact['artifact_id']}/purge", json={"approved_by": "retention-steward", "reason": "Expired"})
    assert blocked.status_code == 409

    released = client.post(
        f"/api/v1/catalog/artifacts/{artifact['artifact_id']}/retention",
        json={"approved_by": "retention-steward", "retention_days": 1, "tier": "archive", "legal_hold": False, "reason": "Legal hold released"},
    )
    assert released.status_code == 200
    future = datetime.fromisoformat(released.json()["expires_at"]) + timedelta(seconds=1)
    monkeypatch.setattr(retention, "_now", lambda: future)
    assert client.get("/api/v1/catalog/artifacts/retention/due").json()["count"] == 1
    purged = client.post(f"/api/v1/catalog/artifacts/{artifact['artifact_id']}/purge", json={"approved_by": "retention-steward", "reason": "Retention period elapsed"})
    assert purged.status_code == 200
    assert purged.json()["status"] == "purged"
    assert purged.json()["bytes_deleted"] > 0
    history = client.get(f"/api/v1/catalog/artifacts/{artifact['artifact_id']}/retention/history").json()
    assert [event["event_type"] for event in history["events"]] == ["retention_registered", "retention_updated", "artifact_purged"]
