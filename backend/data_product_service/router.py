from __future__ import annotations

import os
from datetime import datetime, timezone
from datetime import timedelta
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from backend.artifact_store import ArtifactStore
from backend.mesh_store import PostgresRegistry
from backend.depo_platform.authorization import approval_identity, graph_read_identity
from backend.depo_platform.semantic_registry import release_reference, resolve_approved_release
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
    items = payload.get("artifacts", [])
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        return [], ["artifacts must be a list of objects"]
    for item in items:
        try:
            metadata, source = artifact_store.resolve(str(item.get("artifact_id") or ""))
            records.append((metadata, source))
        except ValueError as exc:
            errors.append(str(exc))
    if not records:
        errors.append("at least one immutable artifact_id is required")
    return records, errors


def _semantic_release_errors(payload: dict) -> list[str]:
    releases = payload.get("semantic_releases")
    if not isinstance(releases, list) or not releases:
        return ["at least one approved semantic_releases entry is required"]
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    for index, release in enumerate(releases):
        if not isinstance(release, dict):
            errors.append(f"semantic_releases[{index}] must be an object")
            continue
        try:
            reference = release_reference(release)
        except ValueError as exc:
            errors.append(f"semantic_releases[{index}] {exc}")
            continue
        asset_id, version = reference["asset_id"], reference["version"]
        if (asset_id, version) in seen:
            errors.append(f"semantic_releases[{index}] duplicates {asset_id}@{version}")
        else:
            seen.add((asset_id, version))
    return errors


def _validate(payload: dict) -> tuple[list[tuple[dict, Path]], list[str]]:
    required = ("product_id", "name", "version", "domain", "owner", "classification", "steward", "lifecycle_state")
    errors = [f"{name} is required" for name in required if not payload.get(name)]
    artifacts, artifact_errors = _artifact_records(payload)
    return artifacts, errors + artifact_errors + _semantic_release_errors(payload)


def _catalog_payload(record: dict) -> dict:
    fields = ("name", "domain", "owner", "version", "classification", "steward", "sla", "quality_status", "lifecycle_state", "sources", "ontologies", "semantic_releases", "manifest")
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
            from backend.depo_platform.network import gateway_subscription_headers
            response = await client.put(f"{catalog_url}/catalog/products/{record['product_id']}/versions/{record['version']}", json=_catalog_payload(record), headers={**gateway_subscription_headers(catalog_url), "X-DEPO-Service-Token": catalog_token})
            response.raise_for_status()
    except httpx.HTTPError as exc:
        delay = min(3600, 2 ** min(attempts, 10))
        return {**record, "status": "pending_catalog_registration", "catalog_attempts": attempts, "catalog_error": str(exc), "last_catalog_attempt_at": _now(), "next_catalog_attempt_at": (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()}
    return {**record, "status": "revoked" if record.get("lifecycle_state") == "revoked" else "published", "catalog_attempts": attempts, "catalog_error": None, "catalog_registered_at": _now()}


async def reconcile_pending(limit: int = 100) -> dict:
    """Durably retry pending catalog registrations; safe to invoke repeatedly."""
    pending = store.due_pending(limit)
    published = 0
    examined = 0
    for key, record in pending:
        with store.advisory_lock(key) as acquired:
            if not acquired: continue
            current = store.get(key)
            if current != record: continue
            updated = await _register_catalog(current)
            examined += 1
            if store.compare_and_put(key, current, updated):
                published += int(updated.get("status") == "published")
    return {"examined": examined, "published": published, "pending": examined - published}



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
    key = _key(payload)
    with store.advisory_lock(key) as acquired:
        if not acquired: raise HTTPException(409, "Product operation is in progress; retry after it completes")
        existing = store.get(key)
        idempotency_key = str(payload.get("idempotency_key") or "")
        if existing and existing.get("idempotency_key") == idempotency_key and idempotency_key:
            return existing
        if existing and existing.get("status") == "published":
            raise HTTPException(409, "A published product version is immutable; publish a new version")
        try:
            semantic_releases = [await resolve_approved_release(release) for release in payload["semantic_releases"]]
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, detail=str(exc)) from exc
        try:
            package = build_package(output_root=root, payload=payload, artifacts=artifacts)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        safe_payload = {key: value for key, value in payload.items() if key not in {"approval_token", "authorization", "api_key"}}
        record = {**safe_payload, "semantic_releases": semantic_releases, "artifacts": [metadata for metadata, _ in artifacts], "manifest": package["manifest"], "package_storage": {"zip_path": str(package["zip_path"]), "package_dir": str(package["package_dir"])}, "status": "pending_catalog_registration", "catalog_attempts": 0, "published_at": _now()}
        store.put(key, record)
        approval_store.put(f"{key}:{record['published_at']}", {"product": key, "approved_by": approver, "approved_at": _now()})
        return store.put(key, await _register_catalog(record))


@router.post("/{product_version}/retry-catalog")
async def retry_catalog(product_version: str, payload: dict, request: Request) -> dict:
    approval_identity(request, payload, token_env="DATA_PRODUCT_APPROVAL_TOKEN")
    with store.advisory_lock(product_version) as acquired:
        if not acquired: raise HTTPException(409, "Product operation is in progress; retry after it completes")
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
    approval_identity(request, payload, token_env="DATA_PRODUCT_APPROVAL_TOKEN")
    with store.advisory_lock(product_version) as acquired:
        if not acquired: raise HTTPException(409, "Product operation is in progress; retry after it completes")
        record = store.get(product_version)
        if not record:
            raise HTTPException(404, "Data product not found")
        approver = approval_identity(request, payload, token_env="DATA_PRODUCT_APPROVAL_TOKEN")
        revoked = {**record, "status": "revoked", "lifecycle_state": "revoked", "revoked_by": approver, "revoked_at": _now()}
        return store.put(product_version, await _register_catalog(revoked))


@router.get("", dependencies=[Depends(graph_read_identity)])
def list_products(limit: int = 100) -> dict:
    safe_limit = max(1, min(int(limit), 500))
    records = sorted(
        store.all().values(),
        key=lambda record: str(record.get("published_at") or record.get("created_at") or ""),
        reverse=True,
    )[:safe_limit]
    return {"products": [{key: value for key, value in record.items() if key not in {"package_storage", "approval_token", "authorization", "api_key"}} for record in records], "limit": safe_limit}


@router.get("/{product_version}/manifest", dependencies=[Depends(graph_read_identity)])
def manifest(product_version: str) -> dict:
    record = store.get(product_version)
    if not record:
        raise HTTPException(404, "Data product not found")
    return record.get("manifest", {})


@router.get("/{product_version}/download", dependencies=[Depends(graph_read_identity)])
def download(product_version: str) -> FileResponse:
    record = store.get(product_version)
    if not record:
        raise HTTPException(404, "Data product not found")
    path = Path(record.get("package_storage", {}).get("zip_path", ""))
    if not path.is_file():
        raise HTTPException(404, "Immutable product package is unavailable")
    return FileResponse(path, filename=path.name, media_type="application/zip")


@router.get("/{product_version}", dependencies=[Depends(graph_read_identity)])
def get_product(product_version: str) -> dict:
    record = store.get(product_version)
    if not record:
        raise HTTPException(404, "Data product not found")
    return {key: value for key, value in record.items() if key not in {"package_storage", "approval_token", "authorization", "api_key"}}
