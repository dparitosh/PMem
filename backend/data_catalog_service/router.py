from __future__ import annotations
import os
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException
from backend.mesh_store import JsonRegistry
router = APIRouter(prefix="/catalog", tags=["data-catalog"])
store = JsonRegistry(Path(os.getenv("DATA_CATALOG_STORAGE", Path(__file__).resolve().parents[2] / "data" / "catalog")) / "products.json")
@router.get("/products")
def products(domain: str = "") -> dict:
    values = list(store.all().values()); values = [v for v in values if not domain or v.get("domain") == domain]
    return {"products": sorted(values, key=lambda v: v["updated_at"], reverse=True), "count": len(values)}
@router.get("/products/{product_id}")
def product(product_id: str) -> dict:
    value = store.all().get(product_id)
    if not value: raise HTTPException(404, "Data product not found")
    return value
@router.put("/products/{product_id}")
def register(product_id: str, payload: dict) -> dict:
    if not product_id or not payload.get("name") or not payload.get("domain") or not payload.get("owner"):
        raise HTTPException(422, "product_id, name, domain and owner are required")
    record = {**payload, "product_id": product_id, "updated_at": datetime.now(timezone.utc).isoformat()}
    return store.put(product_id, record)
