from __future__ import annotations

import os
import hmac
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi import Header

from backend.mesh_store import SqliteRegistry

router = APIRouter(prefix="/catalog", tags=["data-catalog"])
store = SqliteRegistry(Path(os.getenv("DATA_CATALOG_STORAGE", Path(__file__).resolve().parents[2] / "data" / "catalog")) / "products")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _semver(value: str) -> tuple[int, int, int, str]:
    match = re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?", value)
    if not match: raise ValueError("version must use semantic versioning, e.g. 1.2.3")
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), match.group(4) or "~"


def _internal(token: str | None) -> None:
    expected = os.getenv("CATALOG_SERVICE_TOKEN", "")
    if not expected or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(403, "A valid internal catalog service token is required")


@router.get("/products")
def products(domain: str = "") -> dict:
    values = [value for key, value in store.all().items() if not key.endswith(":latest")]
    values = [value for value in values if not domain or value.get("domain") == domain]
    return {"products": sorted(values, key=lambda value: value["updated_at"], reverse=True), "count": len(values)}


@router.get("/products/{product_id}")
def product(product_id: str) -> dict:
    values = store.all()
    versions = [value for key, value in values.items() if key.startswith(f"{product_id}:") and not key.endswith(":latest")]
    if not versions:
        raise HTTPException(404, "Data product not found")
    latest = values.get(f"{product_id}:latest", {}).get("latest_version")
    return {"product_id": product_id, "latest_version": latest, "versions": sorted(versions, key=lambda value: value["updated_at"], reverse=True)}


@router.put("/products/{product_id}/versions/{version}")
def register(product_id: str, version: str, payload: dict, x_depo_service_token: str | None = Header(default=None)) -> dict:
    _internal(x_depo_service_token)
    required = ("name", "domain", "owner", "lifecycle_state", "classification", "steward")
    missing = [name for name in required if not payload.get(name)]
    try: _semver(version)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    if not product_id or not re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]{0,127}", product_id) or missing:
        raise HTTPException(422, f"product_id, version and {', '.join(missing)} are required")
    key = f"{product_id}:{version}"
    existing = store.get(key)
    immutable = ("name", "domain", "owner")
    if existing and {name: existing.get(name) for name in immutable} != {name: payload.get(name) for name in immutable}:
        raise HTTPException(409, "A cataloged product version is immutable")
    record = {**payload, "product_id": product_id, "version": version, "updated_at": _now()}
    candidates = [value for item_key, value in store.all().items() if item_key.startswith(f"{product_id}:") and not item_key.endswith(":latest") and item_key != key and value.get("lifecycle_state") != "revoked"]
    if record.get("lifecycle_state") != "revoked":
        candidates.append(record)
    latest_version = max(candidates, key=lambda value: _semver(value["version"]))["version"] if candidates else None
    store.put_many({key: record, f"{product_id}:latest": {"product_id": product_id, "latest_version": latest_version, "updated_at": record["updated_at"]}})
    return record
