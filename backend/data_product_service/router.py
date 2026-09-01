from __future__ import annotations
import hashlib, os
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException
from backend.mesh_store import JsonRegistry
router = APIRouter(prefix="/data-products", tags=["data-products"])
root = Path(os.getenv("DATA_PRODUCT_STORAGE", Path(__file__).resolve().parents[2] / "data" / "products")); store = JsonRegistry(root / "products.json")
def _validate(payload: dict) -> list[str]:
    required = [key for key in ("product_id", "name", "version", "domain", "owner") if not payload.get(key)]
    errors = [f"{key} is required" for key in required]
    for item in payload.get("artifacts", []):
        if not Path(str(item.get("path") or "")).is_file(): errors.append(f"artifact does not exist: {item.get('path')}")
    return errors
@router.post("/preview")
def preview(payload: dict) -> dict:
    errors = _validate(payload); return {"valid": not errors, "errors": errors, "lineage": payload.get("sources", []), "ontologies": payload.get("ontologies", [])}
@router.post("/publish")
def publish(payload: dict) -> dict:
    errors = _validate(payload)
    if errors: raise HTTPException(422, {"errors": errors})
    if not payload.get("approved_by"): raise HTTPException(409, "approved_by is required")
    artifacts = []
    for item in payload.get("artifacts", []):
        path = Path(item["path"]); artifacts.append({**item, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size": path.stat().st_size})
    record = {**payload, "artifacts": artifacts, "status": "published", "published_at": datetime.now(timezone.utc).isoformat()}
    return store.put(f"{payload['product_id']}:{payload['version']}", record)
@router.get("")
def list_products() -> dict: return {"products": list(store.all().values())}
