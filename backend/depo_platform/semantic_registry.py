"""Client-side release gate for the authoritative semantic metadata registry."""
from __future__ import annotations

import os
from backend.depo_platform.service_urls import service_url
import re
from typing import Any

import httpx
from backend.depo_platform.network import service_bearer_headers
from urllib.parse import quote


_ASSET_ID = re.compile(r"^[A-Za-z][A-Za-z0-9._:/#-]{0,255}$")
_SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?")


def release_reference(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("semantic release requires asset_id, version, and lifecycle_status 'approved'")
    asset_id = str(value.get("asset_id") or "").strip()
    version = str(value.get("version") or "").strip()
    status = str(value.get("lifecycle_status") or "").strip().lower()
    if not _ASSET_ID.fullmatch(asset_id) or not _SEMVER.fullmatch(version) or status != "approved":
        raise ValueError("semantic release must contain a safe asset_id, semantic version, and lifecycle_status 'approved'")
    return {"asset_id": asset_id, "version": version, "lifecycle_status": status}


async def resolve_approved_release(value: Any) -> dict[str, str]:
    """Resolve an approved semantic release without coupling consumers to Neo4j."""
    reference = release_reference(value)
    base_url = service_url("SEMANTIC_REGISTRY_URL", "http://127.0.0.1:8011/api/v1/metadata-registry")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{base_url}/assets/{quote(reference['asset_id'], safe='')}",
                headers=service_bearer_headers('GRAPH_READ_TOKEN', service_name='semantic registry release checks', endpoint=base_url))
    except httpx.HTTPError as exc:
        raise RuntimeError("Semantic registry is unavailable; publication was not attempted") from exc
    if response.status_code == 404:
        raise ValueError("Referenced semantic release does not exist in the registry")
    if response.is_error:
        raise RuntimeError("Semantic registry could not resolve the referenced release")
    try:
        asset = response.json()
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Semantic registry returned invalid JSON; publication was not attempted") from exc
    if not isinstance(asset, dict) or not all(isinstance(asset.get(key), str) and asset[key].strip() for key in ("version", "lifecycle_status")):
        raise RuntimeError("Semantic registry returned an invalid release object; publication was not attempted")
    if str(asset.get('asset_id') or '') != reference['asset_id'] or str(asset.get("version") or "") != reference["version"] or str(asset.get("lifecycle_status") or "").lower() != "approved":
        raise ValueError("Referenced semantic release is not the requested approved registry version")
    return reference
