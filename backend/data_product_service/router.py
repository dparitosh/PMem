from __future__ import annotations
import hashlib, os
from datetime import datetime, timezone
from pathlib import Path
import httpx
from fastapi import APIRouter, HTTPException
from backend.mesh_store import JsonRegistry
router = APIRouter(prefix="/data-products", tags=["data-products"])
root = Path(os.getenv("DATA_PRODUCT_STORAGE", Path(__file__).resolve().parents[2] / "data" / "products")); store = JsonRegistry(root / "products.json")
def _artifact_path(value: str) -> Path:
    path = Path(value).resolve()
    allowed = [Path(item).resolve() for item in os.getenv("DATA_PRODUCT_ALLOWED_ARTIFACT_ROOTS", str(root)).split(os.pathsep) if item]
    if not any(path.is_relative_to(item) for item in allowed): raise ValueError("artifact is outside DATA_PRODUCT_ALLOWED_ARTIFACT_ROOTS")
    return path
def _validate(payload: dict) -> list[str]:
    required = [key for key in ("product_id", "name", "version", "domain", "owner") if not payload.get(key)]
    errors = [f"{key} is required" for key in required]
    for item in payload.get("artifacts", []):
        try: path = _artifact_path(str(item.get("path") or ""))
        except ValueError as exc: errors.append(str(exc)); continue
        if not path.is_file(): errors.append(f"artifact does not exist: {item.get('path')}")
    return errors
@router.post("/preview")
def preview(payload: dict) -> dict:
    errors = _validate(payload); return {"valid": not errors, "errors": errors, "lineage": payload.get("sources", []), "ontologies": payload.get("ontologies", [])}
@router.post("/publish")
async def publish(payload: dict) -> dict:
    errors = _validate(payload)
    if errors: raise HTTPException(422, {"errors": errors})
    if not payload.get("approved_by"): raise HTTPException(409, "approved_by is required")
    artifacts = []
    for item in payload.get("artifacts", []):
        path = _artifact_path(item["path"]); artifacts.append({**item, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size": path.stat().st_size})
    record = {**payload, "artifacts": artifacts, "status": "published", "published_at": datetime.now(timezone.utc).isoformat()}
    stored = store.put(f"{payload['product_id']}:{payload['version']}", record)
    catalog_url = os.getenv("DATA_CATALOG_URL", "").rstrip("/")
    if catalog_url:
        catalog_record = {"name": stored["name"], "domain": stored["domain"], "owner": stored["owner"], "version": stored["version"], "status": stored["status"], "lineage": stored.get("sources", []), "ontologies": stored.get("ontologies", []), "product_url": f"/api/v1/data-products/{payload['product_id']}:{payload['version']}"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.put(f"{catalog_url}/catalog/products/{payload['product_id']}", json=catalog_record); response.raise_for_status()
        except httpx.HTTPError as exc: raise HTTPException(503, f"Catalog registration failed: {exc}") from exc
    return stored
@router.get("")
def list_products() -> dict: return {"products": list(store.all().values())}
@router.get("/{product_version}")
def get_product(product_version: str) -> dict:
    value = store.all().get(product_version)
    if not value: raise HTTPException(404, "Data product not found")
    return value
