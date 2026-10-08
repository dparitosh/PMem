from __future__ import annotations

import os
import asyncio
import logging
from contextlib import asynccontextmanager
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
from .packaging import build_package, publication_digest, verify_package

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data-products", tags=["data-products"])
root = Path(os.getenv("DATA_PRODUCT_STORAGE", Path(__file__).resolve().parents[2] / "data" / "products"))
store = PostgresRegistry("data_products")
approval_store = PostgresRegistry("data_product_approvals")
artifact_store = ArtifactStore()


async def _product_io(callback, *args, **kwargs):
    # Keep the operation lock until blocking work has actually stopped.
    task = asyncio.create_task(asyncio.to_thread(callback, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await task
        except Exception:
            pass
        raise


@asynccontextmanager
async def _product_lock(key):
    lock = store.advisory_lock(key)
    entering = asyncio.create_task(_product_io(lock.__enter__))
    try:
        acquired = await asyncio.shield(entering)
    except asyncio.CancelledError:
        await entering
        await _product_io(lock.__exit__, None, None, None)
        raise
    try:
        yield acquired
    finally:
        await _product_io(lock.__exit__, None, None, None)


def _reject_secrets(value, root=True):
    if isinstance(value, dict):
        for key, item in value.items():
            name = key.lower()
            if root and name in {'approval_token', 'approved_by'}:
                continue
            if name in {'headers', 'credentials', 'authorization', 'api_key', 'password', 'secret', 'token'} or name.endswith(('_token', '_api_key', '_password', '_secret')):
                raise ValueError('Product content cannot contain credentials or arbitrary headers')
            _reject_secrets(item, False)
    elif isinstance(value, list):
        for item in value: _reject_secrets(item, False)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key(payload: dict) -> str:
    return f"{payload['product_id']}:{payload['version']}"


def _public_product(record: dict) -> dict:
    result = {key: value for key, value in record.items() if key not in {'package_storage', 'approval_token', 'authorization', 'api_key'}}
    if result.get('catalog_error'):
        result['catalog_error'] = 'Catalog delivery is unavailable; check service configuration and logs.'
    return result


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
    for name in required:
        if payload.get(name) and (not isinstance(payload[name], str) or not payload[name].strip()):
            errors.append(f'{name} must be a non-empty string')
    if payload.get('lifecycle_state') != 'published':
        errors.append('lifecycle_state must be published at the publication boundary')
    import re
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9._-]{0,127}', str(payload.get('product_id') or '')):
        errors.append('product_id must be a safe identifier')
    version = str(payload.get('version') or '')
    match = re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?', version)
    if not match or any(part.isdigit() and len(part) > 1 and part.startswith('0') for part in (match.group(4) or '').split('.') if match):
        errors.append('version must use semantic versioning')
    try: _reject_secrets(payload)
    except ValueError as exc: errors.append(str(exc))
    artifacts, artifact_errors = _artifact_records(payload)
    return artifacts, errors + artifact_errors + _semantic_release_errors(payload)


def _catalog_payload(record: dict) -> dict:
    fields = ("name", "domain", "owner", "version", "classification", "steward", "sla", "quality_status", "lifecycle_state", "sources", "ontologies", "semantic_releases", "manifest")
    return {field: record.get(field) for field in fields} | {field: record[field] for field in ("product_kind", "analytics_readiness") if record.get(field) is not None} | {"product_url": f"/api/v1/data-products/{record['product_id']}:{record['version']}"}


async def _register_catalog(record: dict) -> dict:
    catalog_url = os.getenv("DATA_CATALOG_URL", "").rstrip("/")
    catalog_token = os.getenv("CATALOG_SERVICE_TOKEN", "")
    attempts = int(record.get("catalog_attempts", 0)) + 1
    delay = min(3600, 2 ** min(attempts, 10))
    retry_metadata = {"catalog_attempts": attempts, "last_catalog_attempt_at": _now(),
                      "next_catalog_attempt_at": (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()}
    if not catalog_url:
        return {**record, **retry_metadata, "status": "pending_catalog_registration", "catalog_error": "DATA_CATALOG_URL is not configured"}
    # Accept both service origins and roots that already include /api/v1.
    if not catalog_url.endswith('/api/v1'):
        catalog_url += '/api/v1'
    try:
        if not catalog_token:
            return {**record, **retry_metadata, "status": "pending_catalog_registration", "catalog_error": "CATALOG_SERVICE_TOKEN is not configured"}
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            from backend.depo_platform.network import gateway_subscription_headers
            response = await client.put(f"{catalog_url}/catalog/products/{record['product_id']}/versions/{record['version']}", json=_catalog_payload(record), headers={**gateway_subscription_headers(catalog_url), "X-DEPO-Service-Token": catalog_token})
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.exception('Catalog delivery failed for product %s version %s', record['product_id'], record['version'])
        return {**record, **retry_metadata, "status": "pending_catalog_registration", "catalog_error": "Catalog delivery is unavailable; retry is scheduled. Check service logs."}
    return {**record, "status": "revoked" if record.get("lifecycle_state") == "revoked" else "published", "catalog_attempts": attempts, "catalog_error": None, "next_catalog_attempt_at": None, "catalog_registered_at": _now()}


async def reconcile_pending(limit: int = 100) -> dict:
    """Durably retry pending catalog registrations; safe to invoke repeatedly."""
    pending = await _product_io(store.due_pending, limit)
    published = revoked = 0
    examined = 0
    for key, record in pending:
        async with _product_lock(key) as acquired:
            if not acquired: continue
            current = await _product_io(store.get, key)
            if current != record: continue
            updated = await _register_catalog(current)
            examined += 1
            if await _product_io(store.compare_and_put, key, current, updated):
                published += int(updated.get("status") == "published")
                revoked += int(updated.get("status") == "revoked")
    return {"examined": examined, "published": published, "revoked": revoked, "pending": examined - published - revoked}



@router.post("/preview")
def preview(payload: dict) -> dict:
    _, errors = _validate(payload)
    return {"valid": not errors, "errors": errors, "lineage": payload.get("sources", []), "ontologies": payload.get("ontologies", [])}


@router.post("/publish")
async def publish(payload: dict, request: Request) -> dict:
    artifacts, errors = await _product_io(_validate, payload)
    if errors:
        raise HTTPException(422, {"errors": errors})
    approver = approval_identity(request, payload, token_env="DATA_PRODUCT_APPROVAL_TOKEN")
    key = _key(payload)
    async with _product_lock(key) as acquired:
        if not acquired: raise HTTPException(409, "Product operation is in progress; retry after it completes")
        existing = await _product_io(store.get, key)
        idempotency_key = str(payload.get("idempotency_key") or "")
        if existing and existing.get("idempotency_key") == idempotency_key and idempotency_key:
            if existing.get('publication_digest') != await _product_io(publication_digest, payload, artifacts):
                raise HTTPException(409, 'Idempotency key was already used with different or unverified content')
            try:
                storage = existing.get('package_storage', {})
                await _product_io(verify_package, Path(storage.get('package_dir', '')), Path(storage.get('zip_path', '')), existing.get('manifest'))
            except ValueError as exc:
                raise HTTPException(409, 'Retained product package failed integrity verification; restore it before retrying') from exc
            return _public_product(existing)
        if existing:
            raise HTTPException(409, "A product version is immutable; retry catalog delivery or publish a new version")
        try:
            semantic_releases = [await resolve_approved_release(release) for release in payload["semantic_releases"]]
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, detail=str(exc)) from exc
        try:
            package = await _product_io(build_package, output_root=root, payload=payload, artifacts=artifacts)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        safe_payload = {key: value for key, value in payload.items() if key not in {"approval_token", "authorization", "api_key"}}
        record = {**safe_payload, "semantic_releases": semantic_releases, "artifacts": [metadata for metadata, _ in artifacts], "manifest": package["manifest"], "package_storage": {"zip_path": str(package["zip_path"]), "package_dir": str(package["package_dir"])}, "status": "pending_catalog_registration", "catalog_attempts": 0, "published_at": _now()}
        record['publication_digest'] = package['manifest']['publication_digest']
        await _product_io(store.put_with_related, key, record, related_namespace=approval_store.namespace,
            related_key=f"{key}:{record['published_at']}", related_value={"product": key, "approved_by": approver, "approved_at": _now()})
        return _public_product(await _product_io(store.put, key, await _register_catalog(record)))


@router.post("/{product_version}/retry-catalog")
async def retry_catalog(product_version: str, payload: dict, request: Request) -> dict:
    approval_identity(request, payload, token_env="DATA_PRODUCT_APPROVAL_TOKEN")
    async with _product_lock(product_version) as acquired:
        if not acquired: raise HTTPException(409, "Product operation is in progress; retry after it completes")
        record = await _product_io(store.get, product_version)
        if not record:
            raise HTTPException(404, "Data product not found")
        approval_identity(request, payload, token_env="DATA_PRODUCT_APPROVAL_TOKEN")
        if record.get("status") == "revoked":
            raise HTTPException(409, "A revoked product cannot be published")
        return _public_product(await _product_io(store.put, product_version, await _register_catalog(record)))


@router.post("/reconcile")
async def reconcile(payload: dict, request: Request) -> dict:
    approval_identity(request, payload, token_env="DATA_PRODUCT_APPROVAL_TOKEN")
    limit = payload.get("limit", 100)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise HTTPException(422, 'limit must be an integer between 1 and 1000')
    return await reconcile_pending(limit)


@router.post("/{product_version}/revoke")
async def revoke(product_version: str, payload: dict, request: Request) -> dict:
    approval_identity(request, payload, token_env="DATA_PRODUCT_APPROVAL_TOKEN")
    async with _product_lock(product_version) as acquired:
        if not acquired: raise HTTPException(409, "Product operation is in progress; retry after it completes")
        record = await _product_io(store.get, product_version)
        if not record:
            raise HTTPException(404, "Data product not found")
        approver = approval_identity(request, payload, token_env="DATA_PRODUCT_APPROVAL_TOKEN")
        request_id = str(payload.get('idempotency_key') or '')
        if record.get('lifecycle_state') == 'revoked':
            if request_id and record.get('revocation_request_id') != request_id:
                raise HTTPException(409,'Product was revoked by a different operation')
            return _public_product(record)
        revoked = {**record, "status": "revoked", "lifecycle_state": "revoked", "revoked_by": approver, "revoked_at": _now(),
                   'revocation_request_id':request_id,'revocation_reason':str(payload.get('reason') or '')}
        # Commit the local revocation before a remote request can block, fail,
        # or be interrupted by process shutdown. Reconciliation delivers it.
        revoked = {**revoked, "status": "pending_catalog_registration", "next_catalog_attempt_at": None}
        await _product_io(store.put, product_version, revoked)
        return _public_product(await _product_io(store.put, product_version, await _register_catalog(revoked)))


@router.get("", dependencies=[Depends(graph_read_identity)])
def list_products(limit: int = 100, offset: int = 0) -> dict:
    safe_limit = max(1, min(int(limit), 500))
    if offset < 0:
        raise HTTPException(422, 'offset must be nonnegative')
    total, page = store.page(limit=safe_limit, offset=offset, order_field='published_at')
    return {"products": [_public_product(record) for record in page],
        "limit": safe_limit, 'offset': offset, 'total': total, 'next_offset': offset + safe_limit if offset + safe_limit < total else None}


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
    try:
        verify_package(Path(record.get('package_storage', {}).get('package_dir', '')), path, record.get('manifest'))
    except ValueError as exc:
        raise HTTPException(409, 'Retained product package failed integrity verification; restore it before downloading') from exc
    return FileResponse(path, filename=path.name, media_type="application/zip")


@router.get("/{product_version}", dependencies=[Depends(graph_read_identity)])
def get_product(product_version: str) -> dict:
    record = store.get(product_version)
    if not record:
        raise HTTPException(404, "Data product not found")
    return _public_product(record)
