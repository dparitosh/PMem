from __future__ import annotations

import json
import os
from typing import Any
import httpx
from fastapi import APIRouter, HTTPException, Request
from backend.platform.authorization import approval_identity
from backend.artifact_store import ArtifactStore
from . import speed_path

router = APIRouter(prefix="/pipeline/speed", tags=["speed-path"])

@router.get("/sources")
def list_sources() -> dict[str, Any]: return {"sources": speed_path.list_sources()}

@router.post("/sources", status_code=201)
def create_source(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    actor = approval_identity(request, payload, token_env="SPEED_PATH_APPROVAL_TOKEN")
    try: return speed_path.register_source(payload, actor)
    except FileExistsError as exc: raise HTTPException(409, str(exc)) from exc
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.post("/sources/{source_id}/approve")
def approve_source(source_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    actor = approval_identity(request, payload, token_env="SPEED_PATH_APPROVAL_TOKEN")
    try: return speed_path.approve_source(source_id, actor)
    except LookupError as exc: raise HTTPException(404, str(exc)) from exc

@router.get("/events")
def list_events(limit: int = 100) -> dict[str, Any]: return {"events": speed_path.list_events(limit)}

@router.post("/events", status_code=202)
def capture_event(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    actor = approval_identity(request, payload, token_env="SPEED_EVENT_TOKEN")
    try: return speed_path.capture_event(payload, actor)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.post("/reconciliations", status_code=202)
def reconcile(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    actor = approval_identity(request, payload, token_env="SPEED_EVENT_TOKEN")
    try: return speed_path.reconcile(list(payload.get("event_ids") or []), actor)
    except LookupError as exc: raise HTTPException(404, str(exc)) from exc
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.post("/reconciliations/{reconciliation_id}/publish")
async def publish(reconciliation_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Publish a validated speed partition only through the CEIM boundary."""
    actor = approval_identity(request, payload, token_env="CEIM_PUBLISH_APPROVAL_TOKEN")
    record = speed_path.reconciliations.get(reconciliation_id)
    if not record: raise HTTPException(404, "Speed reconciliation was not found")
    if record.get("status") == "published": return record
    if record.get("status") != "ready_for_approved_publication": raise HTTPException(409, "Only a validated speed reconciliation can be published")
    try:
        _, path = ArtifactStore().resolve(record["partition_artifact_id"])
        batch = json.loads(path.read_text(encoding="utf-8"))
        root = os.getenv("CEIM_SERVICE_URL", "http://127.0.0.1:8018/api/v1").rstrip("/")
        root = root if root.endswith("/api/v1") else f"{root}/api/v1"
        publication_payload = {**batch, "ontology_id": payload.get("ontology_id"), "prefix": payload.get("prefix", "ceim"), "semantic_release": payload.get("semantic_release"), "approved_by": actor, "approval_token": payload.get("approval_token")}
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(f"{root}/ceim/publications/graph", json=publication_payload)
        if response.is_error: raise RuntimeError(f"Canonical publication returned HTTP {response.status_code}: {response.text[:500]}")
        published = {**record, "status": "published", "published_at": speed_path._now(), "published_by": actor, "publication": dict(response.json())}
        return speed_path.reconciliations.put(reconciliation_id, published)
    except (ValueError, json.JSONDecodeError) as exc: raise HTTPException(422, str(exc)) from exc
    except (RuntimeError, httpx.HTTPError) as exc: raise HTTPException(503, str(exc)) from exc
