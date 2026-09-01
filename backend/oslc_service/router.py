from __future__ import annotations

from fastapi import APIRouter, HTTPException
import httpx

from backend.routes.oslc_routes import router as server_router
from .client import client
from .sync import OSLCSynchronizer

router = APIRouter(prefix="/oslc", tags=["oslc-client"])
synchronizer = OSLCSynchronizer(client)


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "oslc", "server": "enabled", "remote_configured": bool(client.base_url)}


@router.get("/remote/catalog")
def remote_catalog() -> dict:
    try: return client.discover()
    except httpx.HTTPError as exc: raise HTTPException(status_code=503, detail=f"Remote OSLC catalog unavailable: {exc}") from exc
    except RuntimeError as exc: raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/remote/query/{resource_type}")
def remote_query(resource_type: str, parameters: dict) -> dict:
    try: return client.query(resource_type, parameters)
    except httpx.HTTPError as exc: raise HTTPException(status_code=503, detail=f"Remote OSLC query unavailable: {exc}") from exc
    except RuntimeError as exc: raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/remote/sync/{resource_type}", summary="Pull and stage a remote OSLC query snapshot")
def pull_remote_sync(resource_type: str, parameters: dict) -> dict:
    try:
        return synchronizer.pull(resource_type, parameters)
    except httpx.HTTPError as exc: raise HTTPException(status_code=503, detail=f"Remote OSLC sync unavailable: {exc}") from exc
    except RuntimeError as exc: raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/remote/sync", summary="List staged OSLC pull snapshots")
def list_remote_syncs() -> dict:
    return {"syncs": synchronizer.store.list()}


@router.get("/remote/sync/{sync_id}", summary="Read one staged OSLC pull snapshot")
def get_remote_sync(sync_id: str) -> dict:
    snapshot = synchronizer.store.get(sync_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="OSLC sync snapshot not found")
    return snapshot
