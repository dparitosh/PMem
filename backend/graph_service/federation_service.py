"""Allow-listed SPARQL peer registry; no arbitrary federation endpoints."""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from backend.mesh_store import PostgresRegistry

from .sparql_service import _BLOCKED


_ID = re.compile(r"[a-z][a-z0-9-]{2,62}$")
peers = PostgresRegistry("sparql_federation_peers")


def _now() -> str: return datetime.now(timezone.utc).isoformat()


def register(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    peer_id, endpoint = str(payload.get("peer_id") or "").strip().lower(), str(payload.get("endpoint") or "").strip()
    parsed = urlparse(endpoint)
    if not _ID.fullmatch(peer_id) or parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("peer_id must be lowercase kebab-case and endpoint must be an HTTPS URL")
    if peers.get(peer_id): raise FileExistsError("Federation peer already exists")
    return peers.put(peer_id, {"peer_id": peer_id, "endpoint": endpoint.rstrip("/"), "ontology_allowlist": sorted({str(item) for item in payload.get("ontology_allowlist", []) if str(item)}), "timeout_seconds": max(1, min(int(payload.get("timeout_seconds", 10)), 30)), "lifecycle_state": "draft", "created_at": _now(), "created_by": actor})


def approve(peer_id: str, actor: str) -> dict[str, Any]:
    record = peers.get(peer_id)
    if not record: raise LookupError("Federation peer was not found")
    return peers.put(peer_id, {**record, "lifecycle_state": "approved", "approved_at": _now(), "approved_by": actor})


def all_peers() -> list[dict[str, Any]]:
    return sorted(peers.all().values(), key=lambda item: item["peer_id"])


async def query(peer_id: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    peer = peers.get(peer_id)
    if not peer or peer.get("lifecycle_state") != "approved": raise LookupError("Federation peer is not approved")
    ontology_id, document = str(payload.get("ontology_id") or ""), str(payload.get("query") or "")
    if peer["ontology_allowlist"] and ontology_id not in peer["ontology_allowlist"]: raise ValueError("Ontology is not allow-listed for this federation peer")
    # Reuse the local parser/gate before forwarding; SERVICE remains prohibited.
    if _BLOCKED.search(document) or not re.match(r"^(?:PREFIX\s+[^\n]+\s*)*(SELECT|ASK)\b", document, re.IGNORECASE):
        raise ValueError("Only bounded read-only SELECT or ASK queries without SERVICE are allowed")
    token = os.getenv(f"SPARQL_PEER_{peer_id.upper().replace('-', '_')}_TOKEN", "")
    headers = {"x-depo-principal-id": actor}
    if token: headers["authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=float(peer["timeout_seconds"])) as client:
        response = await client.post(f"{peer['endpoint']}/api/v1/sparql", json={"ontology_id": ontology_id, "query": document, "limit": min(int(payload.get("limit") or 200), 200)}, headers=headers)
    if response.is_error: raise RuntimeError(f"Federation peer returned HTTP {response.status_code}")
    return {"peer_id": peer_id, "ontology_id": ontology_id, "executed_by": actor, "result": response.json()}
