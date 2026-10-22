from __future__ import annotations

from backend.depo_platform.request_bodies import ApprovalBody, JobPublicationBody, SpeedEventBody, SpeedReconciliationBody, SpeedSourceBody

import json
import os
from backend.depo_platform.service_urls import service_url
from typing import Any
import httpx
from fastapi import APIRouter, HTTPException, Request
from backend.depo_platform.authorization import approval_identity
from backend.depo_platform.network import bounded_timeout_seconds, service_bearer_headers
from backend.artifact_store import ArtifactStore
from . import speed_path
from backend.depo_platform.peer_http import async_peer_response

router = APIRouter(prefix="/pipeline/speed", tags=["speed-path"])

@router.get("/sources")
def list_sources() -> dict[str, Any]: return {"sources": speed_path.list_sources()}

@router.post("/sources", status_code=201)
def create_source(payload: SpeedSourceBody, request: Request) -> dict[str, Any]:
    actor = approval_identity(request, payload, token_env="SPEED_PATH_APPROVAL_TOKEN")
    try: return speed_path.register_source(payload, actor)
    except FileExistsError as exc: raise HTTPException(409, str(exc)) from exc
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.post("/sources/{source_id}/approve")
def approve_source(source_id: str, payload: ApprovalBody, request: Request) -> dict[str, Any]:
    actor = approval_identity(request, payload, token_env="SPEED_PATH_APPROVAL_TOKEN")
    try: return speed_path.approve_source(source_id, actor)
    except LookupError as exc: raise HTTPException(404, str(exc)) from exc

@router.get("/events")
def list_events(limit: int = 100) -> dict[str, Any]: return {"events": speed_path.list_events(limit)}

@router.post("/events", status_code=202)
def capture_event(payload: SpeedEventBody, request: Request) -> dict[str, Any]:
    actor = approval_identity(request, payload, token_env="SPEED_EVENT_TOKEN")
    try: return speed_path.capture_event(payload, actor)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.post("/reconciliations", status_code=202)
def reconcile(payload: SpeedReconciliationBody, request: Request) -> dict[str, Any]:
    actor = approval_identity(request, payload, token_env="SPEED_EVENT_TOKEN")
    try: return speed_path.reconcile(list(payload.get("event_ids") or []), actor)
    except LookupError as exc: raise HTTPException(404, str(exc)) from exc
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.post("/reconciliations/{reconciliation_id}/publish")
async def publish(reconciliation_id: str, payload: JobPublicationBody, request: Request) -> dict[str, Any]:
    """Publish a validated speed partition only through the CEIM boundary."""
    actor = approval_identity(request, payload, token_env="CEIM_PUBLISH_APPROVAL_TOKEN")
    record = speed_path.reconciliations.get(reconciliation_id)
    if not record: raise HTTPException(404, "Speed reconciliation was not found")
    if record.get("status") == "published": return record
    if record.get("status") != "ready_for_approved_publication": raise HTTPException(409, "Only a validated speed reconciliation can be published")
    try:
        _, path = ArtifactStore().resolve(record["partition_artifact_id"])
        batch = json.loads(path.read_text(encoding="utf-8"))
        root = service_url("CEIM_SERVICE_URL", "http://127.0.0.1:8018/api/v1")
        root = root if root.endswith("/api/v1") else f"{root}/api/v1"
        publication_payload = {**batch, "ontology_id": payload.get("ontology_id"), "prefix": payload.get("prefix", "ceim"), "semantic_release": payload.get("semantic_release"), "approved_by": actor, "approval_token": payload.get("approval_token"), "publication_id": reconciliation_id, "source_system": payload.get("source_system") or batch.get("source_system")}
        publication_timeout = bounded_timeout_seconds("GRAPH_PUBLICATION_TIMEOUT_SECONDS", default=180)
        endpoint = f"{root}/ceim/publications/graph"
        try:
            response = await async_peer_response('POST', endpoint, budget=publication_timeout,
                json=publication_payload, headers=service_bearer_headers("CEIM_PUBLISH_APPROVAL_TOKEN", service_name="CEIM", endpoint=endpoint))
            if response.is_error:
                raise RuntimeError(f"Canonical publication returned HTTP {response.status_code}; verify its receipt before retrying")
            publication = response.json()
            from backend.depo_platform.graph_publication_transport import verified_receipt
            expected_ontology = str(payload.get("ontology_id") or f"ceim-{batch.get('standard', '')}").strip().lower()
            if (not isinstance(publication, dict) or publication.get("status") != "published"
                    or publication.get("ontology_id") != expected_ontology or publication.get("publication_id") != reconciliation_id
                    or not verified_receipt(publication.get("publication"), expected_ontology, reconciliation_id)):
                raise RuntimeError("Canonical publication receipt is unverified; reconciliation remains pending")
        except ValueError as exc:
            raise RuntimeError("Canonical publication response is invalid or exceeds its size limit; verify its receipt") from exc
        published = {**record, "status": "published", "published_at": speed_path._now(), "published_by": actor, "publication": publication}
        return speed_path.reconciliations.put(reconciliation_id, published)
    except (ValueError, json.JSONDecodeError) as exc: raise HTTPException(422, str(exc)) from exc
    except (RuntimeError, httpx.HTTPError, TimeoutError) as exc: raise HTTPException(503, "Canonical publication unavailable; reconciliation is retained. Verify its receipt before retrying.") from exc
