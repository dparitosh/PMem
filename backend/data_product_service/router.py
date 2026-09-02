from __future__ import annotations

import os
from datetime import datetime, timezone
from datetime import timedelta
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from backend.artifact_store import ArtifactStore
from backend.mesh_store import PostgresRegistry
from backend.platform.authorization import approval_identity
from .packaging import build_package

router = APIRouter(prefix="/data-products", tags=["data-products"])
root = Path(os.getenv("DATA_PRODUCT_STORAGE", Path(__file__).resolve().parents[2] / "data" / "products"))
store = PostgresRegistry("data_products")
approval_store = PostgresRegistry("data_product_approvals")
artifact_store = ArtifactStore()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key(payload: dict) -> str:
    return f"{payload['product_id']}:{payload['version']}"


def _artifact_records(payload: dict) -> tuple[list[tuple[dict, Path]], list[str]]:
    records, errors = [], []
    for item in payload.get("artifacts", []):
        try:
            metadata, source = artifact_store.resolve(str(item.get("artifact_id") or ""))
            records.append((metadata, source))
        except ValueError as exc:
            errors.append(str(exc))
    if not records:
        errors.append("at least one immutable artifact_id is required")
    return records, errors


def _validate(payload: dict) -> tuple[list[tuple[dict, Path]], list[str]]:
    required = ("product_id", "name", "version", "domain", "owner", "classification", "steward", "lifecycle_state")
    errors = [f"{name} is required" for name in required if not payload.get(name)]
    artifacts, artifact_errors = _artifact_records(payload)
    return artifacts, errors + artifact_errors


def _catalog_payload(record: dict) -> dict:
    fields = ("name", "domain", "owner", "version", "classification", "steward", "sla", "quality_status", "lifecycle_state", "sources", "ontologies", "manifest")
    return {field: record.get(field) for field in fields} | {"product_url": f"/api/v1/data-products/{record['product_id']}:{record['version']}"}


async def _register_catalog(record: dict) -> dict:
    catalog_url = os.getenv("DATA_CATALOG_URL", "").rstrip("/")
    catalog_token = os.getenv("CATALOG_SERVICE_TOKEN", "")
    attempts = int(record.get("catalog_attempts", 0)) + 1
    if not catalog_url:
        return {**record, "status": "pending_catalog_registration", "catalog_attempts": attempts, "catalog_error": "DATA_CATALOG_URL is not configured"}
    try:
        if not catalog_token:
            return {**record, "status": "pending_catalog_registration", "catalog_attempts": attempts, "catalog_error": "CATALOG_SERVICE_TOKEN is not configured"}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.put(f"{catalog_url}/catalog/products/{record['product_id']}/versions/{record['version']}", json=_catalog_payload(record), headers={"X-DEPO-Service-Token": catalog_token})
            response.raise_for_status()
    except httpx.HTTPError as exc:
        delay = min(3600, 2 ** min(attempts, 10))
        return {**record, "status": "pending_catalog_registration", "catalog_attempts": attempts, "catalog_error": str(exc), "last_catalog_attempt_at": _now(), "next_catalog_attempt_at": (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()}
    return {**record, "status": "published", "catalog_attempts": attempts, "catalog_error": None, "catalog_registered_at": _now()}


async def reconcile_pending(limit: int = 100) -> dict:
    """Durably retry pending catalog registrations; safe to invoke repeatedly."""
    now = datetime.now(timezone.utc)
    pending = [(key, value) for key, value in store.all().items() if value.get("status") == "pending_catalog_registration" and (not value.get("next_catalog_attempt_at") or datetime.fromisoformat(value["next_catalog_attempt_at"]) <= now)][:limit]
    published = 0
    for key, record in pending:
        updated = await _register_catalog(record)
        store.put(key, updated)
        published += int(updated.get("status") == "published")
    return {"examined": len(pending), "published": published, "pending": len(pending) - published}


@router.post("/preview")
def preview(payload: dict) -> dict:
    _, errors = _validate(payload)
    return {"valid": not errors, "errors": errors, "lineage": payload.get("sources", []), "ontologies": payload.get("ontologies", [])}


@router.post("/publish")
async def publish(payload: dict, request: Request) -> dict:
    artifacts, errors = _validate(payload)
    if errors:
        raise HTTPException(422, {"errors": errors})
    approver = approval_identity(request, payload, token_env="DATA_PRODUCT_APPROVAL_TOKEN")
    key, existing = _key(payload), store.get(_key(payload))
    idempotency_key = str(payload.get("idempotency_key") or "")
    if existing and existing.get("idempotency_key") == idempotency_key and idempotency_key:
        return existing
    if existing and existing.get("status") == "published":
        raise HTTPException(409, "A published product version is immutable; publish a new version")
    package = build_package(output_root=root, payload=payload, artifacts=artifacts)
    record = {**payload, "artifacts": [metadata for metadata, _ in artifacts], "manifest": package["manifest"], "package_storage": {"zip_path": str(package["zip_path"]), "package_dir": str(package["package_dir"])}, "status": "pending_catalog_registration", "catalog_attempts": 0, "published_at": _now()}
    store.put(key, record)
    approval_store.put(f"{key}:{record['published_at']}", {"product": key, "approved_by": approver, "approved_at": _now()})
    return store.put(key, await _register_catalog(record))


@router.post("/{product_version}/retry-catalog")
async def retry_catalog(product_version: str, payload: dict, request: Request) -> dict:
    record = store.get(product_version)
    if not record:
        raise HTTPException(404, "Data product not found")
    approval_identity(request, payload, token_env="DATA_PRODUCT_APPROVAL_TOKEN")
    if record.get("status") == "revoked":
        raise HTTPException(409, "A revoked product cannot be published")
    return store.put(product_version, await _register_catalog(record))


@router.post("/reconcile")
async def reconcile(payload: dict, request: Request) -> dict:
    approval_identity(request, payload, token_env="DATA_PRODUCT_APPROVAL_TOKEN")
    return await reconcile_pending(max(1, min(int(payload.get("limit", 100)), 1000)))


@router.post("/{product_version}/revoke")
async def revoke(product_version: str, payload: dict, request: Request) -> dict:
    record = store.get(product_version)
    if not record:
        raise HTTPException(404, "Data product not found")
    approver = approval_identity(request, payload, token_env="DATA_PRODUCT_APPROVAL_TOKEN")
    revoked = {**record, "status": "revoked", "lifecycle_state": "revoked", "revoked_by": approver, "revoked_at": _now()}
    return store.put(product_version, await _register_catalog(revoked))


@router.get("")
def list_products() -> dict:
    return {"products": [{key: value for key, value in record.items() if key != "package_storage"} for record in store.all().values()]}


@router.get("/{product_version}/manifest")
def manifest(product_version: str) -> dict:
    record = store.get(product_version)
    if not record:
        raise HTTPException(404, "Data product not found")
    return record.get("manifest", {})


@router.get("/{product_version}/download")
def download(product_version: str) -> FileResponse:
    record = store.get(product_version)
    if not record:
        raise HTTPException(404, "Data product not found")
    path = Path(record.get("package_storage", {}).get("zip_path", ""))
    if not path.is_file():
        raise HTTPException(404, "Immutable product package is unavailable")
    return FileResponse(path, filename=path.name, media_type="application/zip")


@router.get("/{product_version}")
def get_product(product_version: str) -> dict:
    record = store.get(product_version)
    if not record:
        raise HTTPException(404, "Data product not found")
    return {key: value for key, value in record.items() if key != "package_storage"}
