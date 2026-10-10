from __future__ import annotations

from backend.depo_platform.request_bodies import OslcQueryBody

from fastapi import APIRouter, HTTPException, Request, Depends
from backend.depo_platform.authorization import approval_identity, graph_read_identity
import httpx

from backend.routes.oslc_routes import router as server_router
from .client import client
from backend.Services.oslc_service import OSLCService
import os

def remote_enabled():
    return os.getenv("OSLC_REMOTE_ENABLED", "false").lower() == "true"

def require_remote():
    if not remote_enabled():
        raise HTTPException(503, "Remote OSLC is disabled; enable OSLC_REMOTE_ENABLED")
from .access import authorize
from .sync import OSLCSynchronizer, safe_parameters, redact_legacy_snapshots

router = APIRouter(prefix="/oslc", tags=["oslc-client"])
synchronizer = OSLCSynchronizer(client)


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "oslc", "server": "enabled" if OSLCService.is_enabled() else "disabled", "remote_enabled": remote_enabled(), "remote_configured": bool(client.base_url)}


@router.get("/remote/catalog", dependencies=[Depends(graph_read_identity)])
def remote_catalog() -> dict:
    require_remote()
    try: return client.discover()
    except httpx.HTTPError as exc: raise HTTPException(status_code=503, detail=f"Remote OSLC catalog unavailable: {exc}") from exc
    except (RuntimeError, ValueError) as exc: raise HTTPException(status_code=503, detail="Remote OSLC response or configuration is invalid") from exc


@router.post("/remote/query/{resource_type}", dependencies=[Depends(graph_read_identity)])
def remote_query(resource_type: str, parameters: OslcQueryBody) -> dict:
    require_remote()
    try: return client.query(resource_type, parameters)
    except httpx.HTTPError as exc: raise HTTPException(status_code=503, detail=f"Remote OSLC query unavailable: {exc}") from exc
    except RuntimeError as exc: raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/remote/sync/{resource_type}", summary="Pull and stage a remote OSLC query snapshot")
def pull_remote_sync(resource_type: str, parameters: OslcQueryBody, request: Request) -> dict:
    approval_identity(request, parameters, token_env="AGENTIC_APPROVAL_TOKEN")
    require_remote()
    try:
        return synchronizer.pull(resource_type, safe_parameters(parameters))
    except httpx.HTTPError as exc: raise HTTPException(status_code=503, detail=f"Remote OSLC sync unavailable: {exc}") from exc
    except RuntimeError as exc: raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/remote/sync", dependencies=[Depends(graph_read_identity)], summary="List staged OSLC pull snapshots")
def list_remote_syncs(identity: str = Depends(graph_read_identity)) -> dict:
    authorize(identity, "syncs")
    redact_legacy_snapshots(synchronizer.store)
    return {"syncs": synchronizer.store.list()}


@router.get("/remote/sync/{sync_id}", dependencies=[Depends(graph_read_identity)], summary="Read one staged OSLC pull snapshot")
def get_remote_sync(sync_id: str, identity: str = Depends(graph_read_identity)) -> dict:
    authorize(identity, "syncs", sync_id)
    redact_legacy_snapshots(synchronizer.store)
    snapshot = synchronizer.store.get(sync_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="OSLC sync snapshot not found")
    return snapshot
