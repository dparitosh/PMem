from __future__ import annotations

from fastapi import APIRouter, HTTPException
import httpx

from backend.routes.oslc_routes import router as server_router
from .client import client

router = APIRouter(prefix="/oslc", tags=["oslc-client"])


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
